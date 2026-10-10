import { CONTRACT_VERSION, type ProposedJobContract } from "../contract/buildJobContract";

/**
 * Persist-only adapter for Manual UIMidas submit.
 *
 * UIMidas is the interim client-facing source of truth. Equivalence with the
 * published Client Studio page remains unverified.
 *
 * Posts the studio-jobs-v2-draft envelope to POST /api/v1/client-briefs.
 * Does not send ownerIdentity placeholders as production identity. Does not
 * call POST /api/v1/jobs, schedule planning, or generate images.
 *
 * Batch, Projects, saved projects, and catalogue execution are not supported
 * by this adapter even when Manual persistence succeeds.
 */

export const IDENTITY_NOT_CONFIGURED = "IDENTITY_NOT_CONFIGURED";

export const IDENTITY_CONFIGURATION_HELP =
  "Development identity is not configured. Set MIDAS_DEV_OWNER_ID and MIDAS_DEV_CONTRACT_ID on the backend, then retry. Optional MIDAS_DEV_CONTRACT_REVISION defaults to 1. The draft is unchanged.";

export interface PersistBriefResponse {
  briefId: string;
  contractVersion: typeof CONTRACT_VERSION;
  idempotencyKey: string;
  mock: false;
  persisted: true;
  ownerId: string;
  contractId: string;
  revision: number;
  briefHash: string;
  clientBrief: ProposedJobContract;
}

export class PersistSubmitFailure extends Error {
  readonly code: string | undefined;

  constructor(message: string, code?: string) {
    super(message);
    this.name = "PersistSubmitFailure";
    this.code = code;
  }
}

export type EnvReader = {
  VITE_API_BASE_URL?: string;
  VITE_USE_MOCK_SUBMIT?: string;
};

export function readSubmitEnv(): EnvReader {
  const env = (import.meta as ImportMeta & { env?: EnvReader }).env;
  return env ?? {};
}

export function apiBaseUrl(env: EnvReader = readSubmitEnv()): string {
  const raw = env.VITE_API_BASE_URL?.trim();
  if (!raw) return "";
  return raw.replace(/\/$/, "");
}

export function shouldUseMockSubmit(env: EnvReader = readSubmitEnv()): boolean {
  return env.VITE_USE_MOCK_SUBMIT === "true";
}

function clientBriefsUrl(briefId?: string, env: EnvReader = readSubmitEnv()): string {
  const base = apiBaseUrl(env);
  const path = briefId ? `/api/v1/client-briefs/${encodeURIComponent(briefId)}` : "/api/v1/client-briefs";
  return `${base}${path}`;
}


type ClientBriefViewBody = {
  brief_id: string;
  owner_id: string;
  contract_id: string;
  revision: number;
  brief_hash: string;
  client_brief: ProposedJobContract;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseApiError(payload: unknown, fallback: string): PersistSubmitFailure {
  if (!isRecord(payload) || !isRecord(payload.error)) {
    return new PersistSubmitFailure(fallback);
  }
  const code = typeof payload.error.code === "string" ? payload.error.code : undefined;
  const message =
    typeof payload.error.message === "string" && payload.error.message.trim()
      ? payload.error.message
      : fallback;
  if (code === IDENTITY_NOT_CONFIGURED) {
    return new PersistSubmitFailure(IDENTITY_CONFIGURATION_HELP, code);
  }
  return new PersistSubmitFailure(message, code);
}

function parseBriefView(payload: unknown): ClientBriefViewBody {
  if (!isRecord(payload)) throw new PersistSubmitFailure("The saved brief response was not an object.");
  const briefId = payload.brief_id;
  const ownerId = payload.owner_id;
  const contractId = payload.contract_id;
  const revision = payload.revision;
  const briefHash = payload.brief_hash;
  const clientBrief = payload.client_brief;
  if (
    typeof briefId !== "string" ||
    typeof ownerId !== "string" ||
    typeof contractId !== "string" ||
    typeof revision !== "number" ||
    typeof briefHash !== "string" ||
    !isRecord(clientBrief)
  ) {
    throw new PersistSubmitFailure("The saved brief response is missing required fields.");
  }
  return {
    brief_id: briefId,
    owner_id: ownerId,
    contract_id: contractId,
    revision,
    brief_hash: briefHash,
    client_brief: clientBrief as unknown as ProposedJobContract,
  };
}

function toPersistResponse(view: ClientBriefViewBody, contract: ProposedJobContract): PersistBriefResponse {
  return {
    briefId: view.brief_id,
    contractVersion: CONTRACT_VERSION,
    idempotencyKey: contract.idempotencyKey,
    mock: false,
    persisted: true,
    ownerId: view.owner_id,
    contractId: view.contract_id,
    revision: view.revision,
    briefHash: view.brief_hash,
    clientBrief: view.client_brief,
  };
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

export async function retrieveClientBrief(
  briefId: string,
  ownerId?: string,
  env: EnvReader = readSubmitEnv(),
): Promise<PersistBriefResponse> {
  const path = clientBriefsUrl(briefId, env);
  const requestUrl = ownerId
    ? `${path}${path.includes("?") ? "&" : "?"}owner_id=${encodeURIComponent(ownerId)}`
    : path;
  let response: Response;
  try {
    response = await fetch(requestUrl, { method: "GET" });
  } catch {
    throw new PersistSubmitFailure("Could not reach the backend to retrieve the saved brief. Confirm the API is running.");
  }
  const payload = await readJson(response);
  if (!response.ok) {
    throw parseApiError(payload, "The saved brief could not be retrieved.");
  }
  const view = parseBriefView(payload);
  return toPersistResponse(view, view.client_brief);
}

export async function persistClientBrief(
  contract: ProposedJobContract,
  env: EnvReader = readSubmitEnv(),
): Promise<PersistBriefResponse> {
  if (!contract.idempotencyKey) {
    throw new PersistSubmitFailure("The submit is missing an idempotency key.");
  }
  const url = clientBriefsUrl(undefined, env);
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_brief: contract }),
    });
  } catch {
    throw new PersistSubmitFailure(
      "Could not reach the backend. Start the API on http://127.0.0.1:8000, or set VITE_USE_MOCK_SUBMIT=true for the local mock. The draft is unchanged.",
    );
  }
  const payload = await readJson(response);
  if (!response.ok) {
    throw parseApiError(payload, "The brief could not be saved.");
  }
  const created = parseBriefView(payload);
  const retrieved = await retrieveClientBrief(created.brief_id, created.owner_id, env);
  if (retrieved.briefId !== created.brief_id) {
    throw new PersistSubmitFailure("The retrieved brief_id did not match the saved brief.");
  }
  return toPersistResponse(
    {
      brief_id: retrieved.briefId,
      owner_id: retrieved.ownerId,
      contract_id: retrieved.contractId,
      revision: retrieved.revision,
      brief_hash: retrieved.briefHash,
      client_brief: retrieved.clientBrief,
    },
    contract,
  );
}
