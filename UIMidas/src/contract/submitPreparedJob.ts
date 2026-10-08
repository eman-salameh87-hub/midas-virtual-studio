import { mockSubmitJob, MockSubmitFailure, type MockSubmitResponse } from "../adapters/mockSubmitJob";
import { createId } from "../lib/ids";
import type { ClientJobDraft } from "../types/draft";
import { validateDraft, type ValidationIssue } from "../validation/validateDraft";
import { buildJobContract, type ProposedJobContract } from "./buildJobContract";

export type SubmitJobAdapter = (contract: ProposedJobContract) => Promise<MockSubmitResponse>;

export type SubmitOutcome =
  | { ok: true; response: MockSubmitResponse; contract: ProposedJobContract }
  | { ok: false; reason: "invalid"; issues: ValidationIssue[] }
  | { ok: false; reason: "mock-failed"; message: string; contract: ProposedJobContract };

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
    const message = error instanceof MockSubmitFailure || error instanceof Error ? error.message : "The mock submit did not complete.";
    return { ok: false, reason: "mock-failed", message, contract };
  }
}
