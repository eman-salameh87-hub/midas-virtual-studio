import { mockSubmitJob, MockSubmitFailure, type MockSubmitResponse } from "../adapters/mockSubmitJob";
import type { JobPlanStatus, MappingIssue, PreparedExecution } from "../adapters/prepareJobFromBrief";
import { PersistSubmitFailure, type PersistBriefResponse } from "../adapters/persistClientBrief";
import { createId } from "../lib/ids";
import type { ClientJobDraft } from "../types/draft";
import { validateDraft, type ValidationIssue } from "../validation/validateDraft";
import { buildJobContract, type ProposedJobContract } from "./buildJobContract";

export type PreparedSubmitResponse = PersistBriefResponse & {
  mappingIssues: MappingIssue[];
  job: JobPlanStatus | null;
  executions?: PreparedExecution[];
};

export type JobSubmitResponse = MockSubmitResponse | PersistBriefResponse | PreparedSubmitResponse;

export function isMockSubmitResponse(response: JobSubmitResponse): response is MockSubmitResponse {
  return response.mock === true;
}

export type SubmitJobAdapter = (contract: ProposedJobContract) => Promise<JobSubmitResponse>;

export type SubmitOutcome =
  | { ok: true; response: JobSubmitResponse; contract: ProposedJobContract }
  | { ok: false; reason: "invalid"; issues: ValidationIssue[] }
  | { ok: false; reason: "mock-failed"; message: string; contract: ProposedJobContract }
  | { ok: false; reason: "persist-failed"; message: string; contract: ProposedJobContract; code?: string };

/** A key is created once per submit operation, then reused for a retry. */
export function sameSubmitKey(current: string | null): string {
  return current ?? createIdempotencyKey();
}

export function createIdempotencyKey(): string {
  return `dev-idem-${createId()}`;
}

export async function submitPreparedJob(
  draft: ClientJobDraft,
  idempotencyKey: string,
  activeItemId?: string,
  adapter: SubmitJobAdapter = mockSubmitJob,
): Promise<SubmitOutcome> {
  const validation = validateDraft(draft, activeItemId);
  if (!validation.valid) return { ok: false, reason: "invalid", issues: validation.issues };

  const contract = buildJobContract(draft, idempotencyKey, activeItemId);
  try {
    const response = await adapter(contract);
    return { ok: true, response, contract };
  } catch (error) {
    if (error instanceof PersistSubmitFailure) {
      return { ok: false, reason: "persist-failed", message: error.message, contract, code: error.code };
    }
    const message = error instanceof MockSubmitFailure || error instanceof Error ? error.message : "The mock submit did not complete.";
    return { ok: false, reason: "mock-failed", message, contract };
  }
}
