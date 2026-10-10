import type { MappingIssue, PreparedExecution } from "../adapters/prepareJobFromBrief";

const STORAGE_KEY = "midas.uimidas.job-session.v1";

export interface SessionExecution extends PreparedExecution {
  preGenerationApproved?: boolean;
}

export interface JobSession {
  briefId: string;
  ownerId: string;
  contractId: string;
  revision: number;
  jobId: string | null;
  mappingIssues: MappingIssue[];
  preGenerationApproved?: boolean;
  executions?: SessionExecution[];
}

export function loadJobSession(): JobSession | null {
  if (typeof localStorage === "undefined") return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (!isSession(parsed)) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveJobSession(session: JobSession): void {
  if (typeof localStorage === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearJobSession(): void {
  if (typeof localStorage === "undefined") return;
  localStorage.removeItem(STORAGE_KEY);
}

export function sessionExecutions(session: JobSession): SessionExecution[] {
  if (session.executions && session.executions.length > 0) return session.executions;
  if (!session.jobId) return [];
  return [
    {
      jobId: session.jobId,
      requestedView: "",
      imageProportions: "",
      resolution: "",
      requestedOutcomes: [],
      preGenerationApproved: session.preGenerationApproved,
    },
  ];
}

function isExecution(value: unknown): value is SessionExecution {
  if (typeof value !== "object" || value === null) return false;
  const row = value as SessionExecution;
  return (
    typeof row.jobId === "string" &&
    typeof row.requestedView === "string" &&
    typeof row.imageProportions === "string" &&
    typeof row.resolution === "string" &&
    Array.isArray(row.requestedOutcomes)
  );
}

function isSession(value: unknown): value is JobSession {
  if (typeof value !== "object" || value === null) return false;
  const row = value as JobSession;
  const executionsOk = row.executions === undefined || (Array.isArray(row.executions) && row.executions.every(isExecution));
  return (
    typeof row.briefId === "string" &&
    typeof row.ownerId === "string" &&
    typeof row.contractId === "string" &&
    typeof row.revision === "number" &&
    (row.jobId === null || typeof row.jobId === "string") &&
    Array.isArray(row.mappingIssues) &&
    executionsOk
  );
}
