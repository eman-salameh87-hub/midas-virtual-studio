import { PersistSubmitFailure, apiBaseUrl, readSubmitEnv, type EnvReader } from "./persistClientBrief";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function jobsUrl(jobId: string, suffix: string, env: EnvReader): string {
  return `${apiBaseUrl(env)}/api/v1/jobs/${encodeURIComponent(jobId)}${suffix}`;
}

function ownerQuery(ownerId: string, revision: number): string {
  return `?owner_id=${encodeURIComponent(ownerId)}&revision=${encodeURIComponent(String(revision))}`;
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new PersistSubmitFailure("The backend returned a non-JSON response.");
  }
}

function apiError(payload: unknown, fallback: string): PersistSubmitFailure {
  if (!isRecord(payload) || !isRecord(payload.error)) return new PersistSubmitFailure(fallback);
  const code = typeof payload.error.code === "string" ? payload.error.code : undefined;
  const message =
    typeof payload.error.message === "string" && payload.error.message.trim()
      ? payload.error.message
      : fallback;
  const details = isRecord(payload.error.details) ? payload.error.details : undefined;
  const reasons = Array.isArray(details?.reasons) ? details.reasons.map(String).join("; ") : "";
  return new PersistSubmitFailure(reasons ? `${message} ${reasons}` : message, code);
}

async function postJob(
  jobId: string,
  suffix: string,
  ownerId: string,
  revision: number,
  env: EnvReader,
  body: object = {},
): Promise<unknown> {
  const response = await fetch(`${jobsUrl(jobId, suffix, env)}${ownerQuery(ownerId, revision)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await readJson(response);
  if (!response.ok) throw apiError(payload, "The job request failed.");
  return payload;
}

export async function fetchJobStatus(
  jobId: string,
  ownerId: string,
  revision: number,
  env: EnvReader = readSubmitEnv(),
): Promise<Record<string, unknown>> {
  const response = await fetch(`${jobsUrl(jobId, "/status", env)}${ownerQuery(ownerId, revision)}`);
  const payload = await readJson(response);
  if (!response.ok || !isRecord(payload)) throw apiError(payload, "Job status could not be loaded.");
  return payload;
}

export async function fetchJob(
  jobId: string,
  ownerId: string,
  revision: number,
  env: EnvReader = readSubmitEnv(),
): Promise<Record<string, unknown>> {
  const response = await fetch(`${jobsUrl(jobId, "", env)}${ownerQuery(ownerId, revision)}`);
  const payload = await readJson(response);
  if (!response.ok || !isRecord(payload)) throw apiError(payload, "Job could not be loaded.");
  return payload;
}

export async function fetchCompile(
  jobId: string,
  ownerId: string,
  revision: number,
  env: EnvReader = readSubmitEnv(),
): Promise<unknown> {
  const response = await fetch(`${jobsUrl(jobId, "/compile", env)}${ownerQuery(ownerId, revision)}`);
  const payload = await readJson(response);
  if (!response.ok) throw apiError(payload, "Compiled plan could not be loaded.");
  return payload;
}

export async function approvePreGeneration(
  jobId: string,
  ownerId: string,
  revision: number,
  env: EnvReader = readSubmitEnv(),
): Promise<Record<string, unknown>> {
  const payload = await postJob(jobId, "/generate/approve", ownerId, revision, env, {});
  if (!isRecord(payload)) throw new PersistSubmitFailure("Pre-generation approval returned an empty body.");
  return payload;
}

export async function startGeneration(
  jobId: string,
  ownerId: string,
  revision: number,
  modelId?: string,
  env: EnvReader = readSubmitEnv(),
): Promise<Record<string, unknown>> {
  const payload = await postJob(
    jobId,
    "/generate",
    ownerId,
    revision,
    env,
    modelId ? { model_id: modelId } : {},
  );
  if (!isRecord(payload)) throw new PersistSubmitFailure("Generation returned an empty body.");
  return payload;
}

export async function runCritique(
  jobId: string,
  ownerId: string,
  revision: number,
  env: EnvReader = readSubmitEnv(),
): Promise<Record<string, unknown>> {
  const payload = await postJob(jobId, "/critique", ownerId, revision, env, {});
  if (!isRecord(payload)) throw new PersistSubmitFailure("Critique returned an empty body.");
  return payload;
}

const critiqueInFlight = new Map<string, Promise<Record<string, unknown>>>();
const autoCritiqueFailed = new Set<string>();
const autoCritiqueCompleted = new Set<string>();

export function critiqueRequestKey(jobId: string, outputId: string): string {
  return `${jobId}:${outputId}`;
}

export function resetCritiqueGuardsForTests(): void {
  critiqueInFlight.clear();
  autoCritiqueFailed.clear();
  autoCritiqueCompleted.clear();
}

export function recordAutoCritiqueFailure(jobId: string, outputId: string): void {
  autoCritiqueFailed.add(critiqueRequestKey(jobId, outputId));
}

export function clearAutoCritiqueFailure(jobId: string, outputId: string): void {
  autoCritiqueFailed.delete(critiqueRequestKey(jobId, outputId));
}

export function autoCritiqueFailedFor(jobId: string, outputId: string): boolean {
  return autoCritiqueFailed.has(critiqueRequestKey(jobId, outputId));
}

export function markAutoCritiqueCompleted(jobId: string, outputId: string): void {
  autoCritiqueCompleted.add(critiqueRequestKey(jobId, outputId));
}

export function shouldAutoCritique(status: Record<string, unknown> | null, jobId: string): boolean {
  if (!status) return false;
  if (status.state === "failed") return false;
  if (status.generation_output_available !== true) return false;
  const outputId = typeof status.generation_output_id === "string" ? status.generation_output_id.trim() : "";
  if (!outputId) return false;
  if (status.critique_matches_generation === true) return false;
  const key = critiqueRequestKey(jobId, outputId);
  if (autoCritiqueFailed.has(key) || autoCritiqueCompleted.has(key)) return false;
  return true;
}

export async function runCritiqueForGeneration(
  jobId: string,
  ownerId: string,
  revision: number,
  outputId: string,
  env: EnvReader = readSubmitEnv(),
): Promise<Record<string, unknown>> {
  const key = critiqueRequestKey(jobId, outputId);
  const existing = critiqueInFlight.get(key);
  if (existing) return existing;
  const request = runCritique(jobId, ownerId, revision, env).finally(() => {
    if (critiqueInFlight.get(key) === request) critiqueInFlight.delete(key);
  });
  critiqueInFlight.set(key, request);
  return request;
}

export async function fetchCritique(
  jobId: string,
  ownerId: string,
  revision: number,
  env: EnvReader = readSubmitEnv(),
): Promise<Record<string, unknown>> {
  const response = await fetch(`${jobsUrl(jobId, "/critique", env)}${ownerQuery(ownerId, revision)}`);
  const payload = await readJson(response);
  if (!response.ok || !isRecord(payload)) throw apiError(payload, "Critique could not be loaded.");
  return payload;
}

export async function startRepair(
  jobId: string,
  ownerId: string,
  revision: number,
  modelId?: string,
  env: EnvReader = readSubmitEnv(),
): Promise<Record<string, unknown>> {
  const payload = await postJob(
    jobId,
    "/repair",
    ownerId,
    revision,
    env,
    modelId ? { model_id: modelId } : {},
  );
  if (!isRecord(payload)) throw new PersistSubmitFailure("Repair returned an empty body.");
  return payload;
}

export async function fetchRepair(
  jobId: string,
  ownerId: string,
  revision: number,
  env: EnvReader = readSubmitEnv(),
): Promise<Record<string, unknown>> {
  const response = await fetch(`${jobsUrl(jobId, "/repair", env)}${ownerQuery(ownerId, revision)}`);
  const payload = await readJson(response);
  if (!response.ok || !isRecord(payload)) throw apiError(payload, "Repair could not be loaded.");
  return payload;
}

export async function approveCandidate(
  jobId: string,
  ownerId: string,
  revision: number,
  env: EnvReader = readSubmitEnv(),
): Promise<Record<string, unknown>> {
  const payload = await postJob(jobId, "/review/approve", ownerId, revision, env, {});
  if (!isRecord(payload)) throw new PersistSubmitFailure("Owner approval returned an empty body.");
  return payload;
}

export async function releaseCandidate(
  jobId: string,
  ownerId: string,
  revision: number,
  env: EnvReader = readSubmitEnv(),
): Promise<Record<string, unknown>> {
  const payload = await postJob(jobId, "/review/release", ownerId, revision, env, {});
  if (!isRecord(payload)) throw new PersistSubmitFailure("Release returned an empty body.");
  return payload;
}

export function generatedImageUrl(
  jobId: string,
  ownerId: string,
  revision: number,
  env: EnvReader = readSubmitEnv(),
): string {
  return `${jobsUrl(jobId, "/generate/image", env)}${ownerQuery(ownerId, revision)}`;
}
