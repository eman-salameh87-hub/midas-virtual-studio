import type { Phase0ExecutionFields } from "../config/phase0Execution";
import { itemsForRequest } from "../lib/requestItems";
import { localFileFor, phase0MediaFromBytes } from "../lib/references";
import type { ClientJobDraft } from "../types/draft";
import {
  apiBaseUrl,
  persistClientBrief,
  PersistSubmitFailure,
  readSubmitEnv,
  retrieveClientBrief,
  type EnvReader,
  type PersistBriefResponse,
} from "./persistClientBrief";

export interface MappingIssue {
  code: string;
  field: string;
  message: string;
}

export interface JobPlanStatus {
  jobId: string;
  stage: string;
  state: string;
  compileAvailable: boolean;
  generationAvailable: boolean;
  critiqueAvailable: boolean;
  eyeAvailable: boolean;
  brainAvailable: boolean;
  stylistAvailable: boolean;
  hold: unknown;
  error: unknown;
  reviewStatus: unknown;
  compile: unknown | null;
}

export interface PreparedExecution {
  jobId: string;
  requestedView: string;
  imageProportions: string;
  resolution: string;
  requestedOutcomes: string[];
}

export interface PersistAndPrepareResult {
  persist: PersistBriefResponse;
  mappingIssues: MappingIssue[];
  job: JobPlanStatus | null;
  executions: PreparedExecution[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

async function encodeFile(file: File): Promise<{ media: string; content_base64: string } | null> {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  const media = phase0MediaFromBytes(bytes);
  if (media !== "JPG" && media !== "PNG" && media !== "WebP" && media !== "PDF") return null;
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return { media, content_base64: btoa(binary) };
}

export async function collectReferenceFiles(
  draft: ClientJobDraft,
  activeItemId?: string,
): Promise<{ reference_id: string; content_base64: string; media_type: string }[]> {
  const files: { reference_id: string; content_base64: string; media_type: string }[] = [];
  for (const item of itemsForRequest(draft, activeItemId)) {
    for (const reference of item.references.items) {
      const file = localFileFor(reference.id);
      if (!file) continue;
      const encoded = await encodeFile(file);
      if (!encoded) continue;
      if (reference.asset?.mediaKind === "image" && encoded.media === "PDF") continue;
      files.push({
        reference_id: reference.id,
        content_base64: encoded.content_base64,
        media_type: encoded.media,
      });
    }
  }
  return files;
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

export function parsePreparedExecutions(payload: Record<string, unknown>): PreparedExecution[] {
  const rows = payload.executions;
  if (Array.isArray(rows) && rows.length > 0) {
    return rows.flatMap((row) => {
      if (!isRecord(row) || typeof row.job_id !== "string" || !row.job_id) return [];
      const outcomes = Array.isArray(row.requested_outcomes)
        ? row.requested_outcomes.filter((item): item is string => typeof item === "string")
        : [];
      return [
        {
          jobId: row.job_id,
          requestedView: typeof row.requested_view === "string" ? row.requested_view : "",
          imageProportions: typeof row.image_proportions === "string" ? row.image_proportions : "",
          resolution: typeof row.resolution === "string" ? row.resolution : "",
          requestedOutcomes: outcomes,
        },
      ];
    });
  }
  const ids = payload.job_ids;
  if (Array.isArray(ids) && ids.length > 0) {
    return ids.flatMap((id) => (typeof id === "string" && id ? [{ jobId: id, requestedView: "", imageProportions: "", resolution: "", requestedOutcomes: [] }] : []));
  }
  if (typeof payload.job_id === "string" && payload.job_id) {
    return [{ jobId: payload.job_id, requestedView: "", imageProportions: "", resolution: "", requestedOutcomes: [] }];
  }
  return [];
}

function parseMappingIssues(payload: unknown): MappingIssue[] {
  if (!isRecord(payload) || !isRecord(payload.error) || !isRecord(payload.error.details)) return [];
  const issues = payload.error.details.issues;
  if (!Array.isArray(issues)) return [];
  return issues.flatMap((issue) => {
    if (!isRecord(issue)) return [];
    if (typeof issue.code !== "string" || typeof issue.field !== "string" || typeof issue.message !== "string") {
      return [];
    }
    return [{ code: issue.code, field: issue.field, message: issue.message }];
  });
}

function jobsUrl(jobId: string, suffix: string, env: EnvReader): string {
  return `${apiBaseUrl(env)}/api/v1/jobs/${encodeURIComponent(jobId)}${suffix}`;
}

export async function pollJobPlanStatus(
  jobId: string,
  ownerId: string,
  env: EnvReader = readSubmitEnv(),
  revision?: number,
): Promise<JobPlanStatus> {
  const query =
    revision === undefined
      ? `?owner_id=${encodeURIComponent(ownerId)}`
      : `?owner_id=${encodeURIComponent(ownerId)}&revision=${encodeURIComponent(String(revision))}`;
  let status: Record<string, unknown> | null = null;
  for (let attempt = 0; attempt < 12; attempt += 1) {
    const response = await fetch(`${jobsUrl(jobId, "/status", env)}${query}`);
    const payload = await readJson(response);
    if (!response.ok || !isRecord(payload)) break;
    status = payload;
    if (payload.compile_available === true || payload.state === "hold" || payload.state === "failed") break;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  let compile: unknown | null = null;
  if (status?.compile_available === true) {
    const compiled = await fetch(`${jobsUrl(jobId, "/compile", env)}${query}`);
    if (compiled.ok) compile = await readJson(compiled);
  }
  return {
    jobId,
    stage: typeof status?.stage === "string" ? status.stage : "intake",
    state: typeof status?.state === "string" ? status.state : "unknown",
    compileAvailable: status?.compile_available === true,
    generationAvailable: status?.generation_available === true,
    critiqueAvailable: status?.critique_available === true,
    eyeAvailable: status?.eye_available === true,
    brainAvailable: status?.brain_available === true,
    stylistAvailable: status?.stylist_available === true,
    hold: status?.hold ?? null,
    error: status?.error ?? null,
    reviewStatus: status?.review_status ?? null,
    compile,
  };
}

export async function persistAndPrepareJob(
  contract: Parameters<typeof persistClientBrief>[0],
  draft: ClientJobDraft,
  activeItemId?: string,
  phase0Fields: Phase0ExecutionFields | null = null,
  env: EnvReader = readSubmitEnv(),
): Promise<PersistAndPrepareResult> {
  const persist = await persistClientBrief(contract, env);
  const retrieved = await retrieveClientBrief(persist.briefId, persist.ownerId, env);
  const referenceFiles = await collectReferenceFiles(draft, activeItemId);
  const url = `${apiBaseUrl(env)}/api/v1/client-briefs/${encodeURIComponent(persist.briefId)}/jobs?owner_id=${encodeURIComponent(persist.ownerId)}&revision=${encodeURIComponent(String(persist.revision))}`;
  const body: Record<string, unknown> = { reference_files: referenceFiles };
  if (phase0Fields) body.phase0_fields_not_in_brief = phase0Fields;
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new PersistSubmitFailure(
      "The brief was saved, but the job could not be started. Confirm the API is running. The draft is unchanged.",
    );
  }
  const payload = await readJson(response);
  if (response.status === 422) {
    return { persist: retrieved, mappingIssues: parseMappingIssues(payload), job: null, executions: [] };
  }
  if (!response.ok || !isRecord(payload)) {
    throw new PersistSubmitFailure("The brief was saved, but creating the job failed. The draft is unchanged.");
  }
  const executions = parsePreparedExecutions(payload);
  const jobId = executions[0]?.jobId;
  if (!jobId) {
    throw new PersistSubmitFailure("The brief was saved, but creating the job failed. The draft is unchanged.");
  }
  const job = await pollJobPlanStatus(jobId, persist.ownerId, env, persist.revision);
  return { persist: retrieved, mappingIssues: [], job, executions };
}
