import { CONTRACT_VERSION, type ProposedJobContract } from "../contract/buildJobContract";
import { createId } from "../lib/ids";

export interface MockSubmitResponse {
  jobId: string;
  contractVersion: typeof CONTRACT_VERSION;
  idempotencyKey: string;
  mock: true;
}

export class MockSubmitFailure extends Error {
  constructor(message = "The mock submit did not complete.") {
    super(message);
    this.name = "MockSubmitFailure";
  }
}

/**
 * Local stand-in for POST /api/studio/v2/jobs.
 * It does not call the network, start generation, or run a workflow.
 */
export async function mockSubmitJob(contract: ProposedJobContract): Promise<MockSubmitResponse> {
  if (!contract.idempotencyKey) throw new MockSubmitFailure("The submit is missing an idempotency key.");
  return {
    jobId: `dev-job-${createId()}`,
    contractVersion: CONTRACT_VERSION,
    idempotencyKey: contract.idempotencyKey,
    mock: true,
  };
}
