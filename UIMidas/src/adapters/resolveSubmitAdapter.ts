import { mockSubmitJob } from "./mockSubmitJob";
import { persistClientBrief, shouldUseMockSubmit, type EnvReader, readSubmitEnv } from "./persistClientBrief";
import type { SubmitJobAdapter } from "../contract/submitPreparedJob";

/** Review uses persist-only unless VITE_USE_MOCK_SUBMIT=true. */
export function resolveJobSubmitAdapter(env: EnvReader = readSubmitEnv()): SubmitJobAdapter {
  if (shouldUseMockSubmit(env)) return mockSubmitJob;
  return (contract) => persistClientBrief(contract, env);
}
