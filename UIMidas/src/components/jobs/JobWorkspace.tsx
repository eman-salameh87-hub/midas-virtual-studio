import { useEffect, useState } from "react";
import {
  approveCandidate,
  approvePreGeneration,
  autoCritiqueFailedFor,
  clearAutoCritiqueFailure,
  fetchCompile,
  fetchCritique,
  fetchJobStatus,
  fetchRepair,
  generatedImageUrl,
  markAutoCritiqueCompleted,
  recordAutoCritiqueFailure,
  releaseCandidate,
  runCritiqueForGeneration,
  shouldAutoCritique,
  startGeneration,
  startRepair,
} from "../../adapters/jobWorkflow";
import { PersistSubmitFailure, retrieveClientBrief } from "../../adapters/persistClientBrief";
import type { MappingIssue } from "../../adapters/prepareJobFromBrief";
import {
  costBelongsToOutput,
  formatCostLine,
  type RecordedGenerationCost,
} from "../../lib/generationCost";
import { clearJobSession, saveJobSession, sessionExecutions, type JobSession, type SessionExecution } from "../../lib/jobSession";
import { SectionIntro } from "../ui/chrome";

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

function holdReasons(status: Record<string, unknown> | null): string[] {
  const hold = asRecord(status?.hold);
  const reasons = hold?.reasons;
  return Array.isArray(reasons) ? reasons.map(String) : [];
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function compiledModelId(compile: unknown): string | undefined {
  const root = asRecord(compile);
  const engine = asRecord(root?.engine);
  const compiled = asRecord(engine?.compile);
  if (typeof compiled?.model_id === "string" && compiled.model_id.trim()) return compiled.model_id;
  if (typeof engine?.model_id === "string" && engine.model_id.trim()) return engine.model_id;
  return undefined;
}

function critiqueAssessment(critique: Record<string, unknown> | null): Record<string, unknown> | null {
  const root = asRecord(critique?.critique) ?? critique;
  return asRecord(root?.assessment);
}

function failedFindings(assessment: Record<string, unknown> | null): Array<Record<string, unknown>> {
  const findings = assessment?.findings;
  if (!Array.isArray(findings)) return [];
  return findings.filter((item): item is Record<string, unknown> => {
    const row = asRecord(item);
    return Boolean(row && row.result === "fail");
  });
}

function outputImageReady(status: Record<string, unknown> | null): boolean {
  if (status?.generation_output_available === true) return true;
  if (status?.generation_output_available === false) return false;
  return status?.generation_available === true && status?.state !== "failed" && status?.state !== "hold";
}

function executionTitle(execution: SessionExecution): string {
  const parts = [execution.requestedView, execution.imageProportions, execution.resolution].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : "Job";
}

export function JobWorkspace({
  session,
  onLeave,
  onSession,
}: {
  session: JobSession;
  onLeave: () => void;
  onSession?: (session: JobSession) => void;
}) {
  const [briefHash, setBriefHash] = useState<string | null>(null);
  const [briefMessage, setBriefMessage] = useState<string | null>(null);
  const executions = sessionExecutions(session);

  useEffect(() => {
    let cancelled = false;
    void retrieveClientBrief(session.briefId, session.ownerId)
      .then((brief) => {
        if (!cancelled) setBriefHash(brief.briefHash);
      })
      .catch((error) => {
        if (!cancelled) setBriefMessage(error instanceof Error ? error.message : "The saved brief could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, [session.briefId, session.ownerId]);

  function leave() {
    clearJobSession();
    onLeave();
  }

  if (executions.length === 0) {
    return (
      <div className="stack">
        <SectionIntro
          eyebrow="Job"
          title="Brief saved"
          lede="A Phase-0 job was not created. The brief is still on the backend."
        />
        <MappingList issues={session.mappingIssues} />
        <button type="button" className="btn btn--primary" onClick={leave}>
          Back to brief
        </button>
      </div>
    );
  }

  return (
    <div className="stack">
      <SectionIntro
        eyebrow="Job"
        title="Results"
        lede="Each requested view or output is its own backend job. Approvals are explicit and are not skipped."
      />
      <div className="job-created">
        <p>
          Brief ID
          <strong>{session.briefId}</strong>
        </p>
        {briefHash ? (
          <p>
            Brief hash
            <strong>{briefHash}</strong>
          </p>
        ) : null}
        <p>
          Executions
          <strong>{executions.length}</strong>
        </p>
      </div>
      {briefMessage ? (
        <div className="status status--warn" aria-live="polite">
          <p>{briefMessage}</p>
        </div>
      ) : null}
      {executions.map((execution) => (
        <ExecutionPanel
          key={execution.jobId}
          execution={execution}
          session={session}
          onSession={onSession}
        />
      ))}
      <p className="note">Generate stays behind Approve generation. The backend still rejects generate without that record.</p>
      <button type="button" className="btn btn--ghost" onClick={leave}>
        Start another brief
      </button>
    </div>
  );
}

function ExecutionPanel({
  execution,
  session,
  onSession,
}: {
  execution: SessionExecution;
  session: JobSession;
  onSession?: (session: JobSession) => void;
}) {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [compile, setCompile] = useState<unknown>(null);
  const [critique, setCritique] = useState<Record<string, unknown> | null>(null);
  const [repair, setRepair] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [critiqueError, setCritiqueError] = useState<string | null>(null);
  const [preApproved, setPreApproved] = useState(Boolean(execution.preGenerationApproved));

  async function loadJobSurfaces(next: Record<string, unknown>) {
    setStatus(next);
    if (next.compile_available === true) {
      setCompile(await fetchCompile(execution.jobId, session.ownerId, session.revision));
    }
    if (next.critique_available === true) {
      setCritique(await fetchCritique(execution.jobId, session.ownerId, session.revision));
    } else {
      setCritique(null);
    }
    if (next.repair_available === true) {
      setRepair(await fetchRepair(execution.jobId, session.ownerId, session.revision));
    }
  }

  async function refresh() {
    const next = await fetchJobStatus(execution.jobId, session.ownerId, session.revision);
    await loadJobSurfaces(next);
  }

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const next = await fetchJobStatus(execution.jobId, session.ownerId, session.revision);
        if (cancelled) return;
        setMessage(null);
        await loadJobSurfaces(next);
      } catch (error) {
        if (!cancelled) setMessage(error instanceof Error ? error.message : "Status could not be loaded.");
      }
    }
    void tick();
    const timer = window.setInterval(() => void tick(), 800);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [execution.jobId, session.ownerId, session.revision]);

  useEffect(() => {
    const outputId = asString(status?.generation_output_id);
    if (!shouldAutoCritique(status, execution.jobId) || !outputId) return;
    let cancelled = false;
    setBusy("critique");
    setCritiqueError(null);
    void runCritiqueForGeneration(execution.jobId, session.ownerId, session.revision, outputId)
      .then(async () => {
        markAutoCritiqueCompleted(execution.jobId, outputId);
        if (cancelled) return;
        await refresh();
      })
      .catch((error) => {
        recordAutoCritiqueFailure(execution.jobId, outputId);
        if (!cancelled) {
          setCritiqueError(
            error instanceof PersistSubmitFailure || error instanceof Error
              ? error.message
              : "Critique could not be completed.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setBusy(null);
      });
    return () => {
      cancelled = true;
    };
  }, [
    execution.jobId,
    session.ownerId,
    session.revision,
    status?.generation_output_id,
    status?.generation_output_available,
    status?.critique_matches_generation,
    status?.state,
  ]);

  async function run(label: string, action: () => Promise<unknown>) {
    setBusy(label);
    setMessage(null);
    try {
      await action();
      await refresh();
    } catch (error) {
      setMessage(error instanceof PersistSubmitFailure || error instanceof Error ? error.message : "The action failed.");
    } finally {
      setBusy(null);
    }
  }

  const compileReady = status?.compile_available === true;
  const generated = status?.generation_available === true;
  const imageReady = outputImageReady(status);
  const critiqueReady = status?.critique_available === true;
  const critiqueCurrent = status?.critique_matches_generation === true;
  const critiqueResult = asString(status?.critique_overall_result);
  const repairEligible = status?.repair_eligible === true;
  const approved = status?.approved === true;
  const released = status?.review_status === "released";
  const held = holdReasons(status).length > 0;
  const failed = status?.state === "failed";
  const canApproveGeneration = compileReady && !held && !generated && !failed;
  const canGenerate = canApproveGeneration && preApproved;
  const assessment = critiqueAssessment(critique);
  const critiqueSummary = asString(assessment?.summary);
  const repairView = asRecord(repair?.repair) ?? repair;
  const repairStatus = asString(repairView?.status);
  const repairHold = Array.isArray(asRecord(repairView?.plan)?.hold_reasons)
    ? (asRecord(repairView?.plan)?.hold_reasons as unknown[]).map(String)
    : [];
  const repairCount = typeof status?.repair_count === "number" ? status.repair_count : 0;
  const repairLimit = typeof status?.repair_limit === "number" ? status.repair_limit : 2;
  const imageSrc = imageReady
    ? `${generatedImageUrl(execution.jobId, session.ownerId, session.revision)}&v=${repairCount}-${String(status?.stage ?? "")}`
    : null;
  const outputId = asString(status?.generation_output_id);
  const critiqueFailed = Boolean(outputId && autoCritiqueFailedFor(execution.jobId, outputId));
  const checkingImage =
    imageReady &&
    status?.generation_output_available === true &&
    !critiqueCurrent &&
    !critiqueFailed &&
    !failed;
  const canRetryCritique = imageReady && critiqueFailed && Boolean(outputId);
  const canApproveCandidate = critiqueReady && critiqueCurrent && critiqueResult === "pass" && !approved;
  const currentCost = asRecord(status?.generation_cost) as RecordedGenerationCost | null;
  const initialCost = asRecord(status?.initial_generation_cost) as RecordedGenerationCost | null;
  const repairCost = asRecord(status?.repair_generation_cost) as RecordedGenerationCost | null;
  const totalCost = asRecord(status?.generation_cost_total) as RecordedGenerationCost | null;
  const shownCost =
    currentCost && (!outputId || !currentCost.output_id || costBelongsToOutput(currentCost, outputId))
      ? currentCost
      : null;
  const outcomes = execution.requestedOutcomes.filter(Boolean);

  return (
    <article className="execution-card">
      <h3>{executionTitle(execution)}</h3>
      <div className="job-created">
        <p>
          Job ID
          <strong>{execution.jobId}</strong>
        </p>
        {outcomes.length > 0 ? (
          <p>
            Output
            <strong>{outcomes.join(", ")}</strong>
          </p>
        ) : null}
        <p>
          Status
          <strong>
            {message && !status
              ? "unavailable"
              : `${String(status?.stage ?? "loading")} · ${String(status?.state ?? "…")}`}
          </strong>
        </p>
      </div>
      <ul className="note">
        <li>Eye {status?.eye_available ? "done" : "waiting"}</li>
        <li>Brain {status?.brain_available ? "done" : "waiting"}</li>
        <li>Stylist {status?.stylist_available ? "done" : "waiting"}</li>
        <li>Compile {compileReady ? "done" : "waiting"}</li>
        <li>Generate {imageReady ? "done" : generated ? "pending" : failed ? "failed" : "not started"}</li>
        <li>
          Critique{" "}
          {checkingImage
            ? "checking image"
            : critiqueCurrent && critiqueResult
              ? critiqueResult.replaceAll("_", " ")
              : critiqueFailed
                ? "failed"
                : critiqueReady
                  ? "stale"
                  : "not started"}
        </li>
        <li>
          Repair {repairEligible ? "available" : repairCount >= repairLimit ? "limit reached" : repairStatus ?? "not started"}
        </li>
      </ul>
      {holdReasons(status).length > 0 ? (
        <div className="status status--warn">
          <p>HOLD</p>
          <ul>
            {holdReasons(status).map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {failed || status?.error ? (
        <div className="status status--warn">
          <p>{failed ? "This execution failed." : null}</p>
          {status?.error ? <p>{JSON.stringify(status.error)}</p> : null}
        </div>
      ) : null}
      {message ? (
        <div className="status status--warn" aria-live="polite">
          <p>{message}</p>
        </div>
      ) : null}
      {compile ? (
        <details className="debug-panel">
          <summary>Compiled plan</summary>
          <pre>{JSON.stringify(compile, null, 2)}</pre>
        </details>
      ) : !message ? (
        <p className="note">Waiting for compile. This page polls GET /status and does not start generation.</p>
      ) : null}
      <div className="button-row">
        <button
          type="button"
          className="btn btn--secondary"
          disabled={!canApproveGeneration || Boolean(busy) || preApproved}
          onClick={() =>
            run("approve", async () => {
              await approvePreGeneration(execution.jobId, session.ownerId, session.revision);
              const nextExecutions = sessionExecutions(session).map((row) =>
                row.jobId === execution.jobId ? { ...row, preGenerationApproved: true } : row,
              );
              const next: JobSession = {
                ...session,
                executions: nextExecutions,
                preGenerationApproved:
                  session.jobId === execution.jobId ? true : session.preGenerationApproved,
              };
              saveJobSession(next);
              onSession?.(next);
              setPreApproved(true);
            })
          }
        >
          {busy === "approve" ? "Approving…" : "Approve generation"}
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={!canGenerate || Boolean(busy)}
          onClick={() =>
            run("generate", () =>
              startGeneration(execution.jobId, session.ownerId, session.revision, compiledModelId(compile)),
            )
          }
        >
          {busy === "generate" ? "Generating…" : "Generate image"}
        </button>
      </div>
      {imageSrc ? (
        <figure className="result-frame">
          <img src={imageSrc} alt={`Generated result for ${executionTitle(execution)}`} />
          <figcaption>
            <p>{formatCostLine("Generation cost", shownCost)}</p>
            {repairCount > 0 ? (
              <>
                <p>{formatCostLine("Original generation cost", initialCost)}</p>
                <p>{formatCostLine("Repair cost", repairCost)}</p>
                {totalCost ? <p>{formatCostLine("Total recorded cost", totalCost)}</p> : null}
              </>
            ) : null}
          </figcaption>
        </figure>
      ) : null}
      {checkingImage ? (
        <div className="status" aria-live="polite">
          <p>Checking image…</p>
        </div>
      ) : null}
      {critiqueFailed ? (
        <div className="status status--warn" aria-live="polite">
          <p>Critique could not be completed.</p>
          {critiqueError ? <p>{critiqueError}</p> : null}
        </div>
      ) : null}
      {repairCount > 0 ? (
        <p className="note">Previous generations stay in job history. This page shows the current output only after the backend marks it complete.</p>
      ) : null}
      {critiqueCurrent && critiqueResult === "repair_required" ? (
        <div className="status status--warn">
          <p>Repair required</p>
          {critiqueSummary ? <p>{critiqueSummary}</p> : null}
          <ul>
            {failedFindings(assessment).map((item, index) => (
              <li key={`${String(item.dimension)}-${index}`}>
                <strong>{String(item.dimension)}</strong> {String(item.observation ?? item.expected ?? "")}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {critiqueCurrent && critiqueResult === "pass" ? (
        <p className="note">Critique passed. Owner approval is still required before release.</p>
      ) : null}
      {critiqueCurrent && critiqueResult === "hold" ? (
        <div className="status status--warn">
          <p>Critique hold. Repair is not available.</p>
          {critiqueSummary ? <p>{critiqueSummary}</p> : null}
        </div>
      ) : null}
      {repairStatus && repairStatus !== "completed" ? (
        <div className="status status--warn">
          <p>Repair {repairStatus.replaceAll("_", " ")}</p>
          {repairHold.length > 0 ? (
            <ul>
              {repairHold.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {imageReady ? (
        <div className="button-row">
          {canRetryCritique ? (
            <button
              type="button"
              className="btn btn--secondary"
              disabled={Boolean(busy)}
              onClick={() =>
                run("critique", async () => {
                  if (!outputId) return;
                  clearAutoCritiqueFailure(execution.jobId, outputId);
                  setCritiqueError(null);
                  await runCritiqueForGeneration(
                    execution.jobId,
                    session.ownerId,
                    session.revision,
                    outputId,
                  );
                })
              }
            >
              {busy === "critique" ? "Critiquing…" : "Retry critique"}
            </button>
          ) : null}
          {repairEligible || busy === "repair" ? (
            <button
              type="button"
              className="btn btn--secondary"
              disabled={!repairEligible || Boolean(busy) || held || failed}
              onClick={() =>
                run("repair", () =>
                  startRepair(
                    execution.jobId,
                    session.ownerId,
                    session.revision,
                    compiledModelId(compile),
                  ),
                )
              }
            >
              {busy === "repair" ? "Repairing…" : "Repair"}
            </button>
          ) : null}
          <button
            type="button"
            className="btn btn--secondary"
            disabled={!canApproveCandidate || Boolean(busy)}
            onClick={() => run("review", () => approveCandidate(execution.jobId, session.ownerId, session.revision))}
          >
            {busy === "review" ? "Saving approval…" : "Approve candidate"}
          </button>
          <button
            type="button"
            className="btn btn--primary"
            disabled={!approved || Boolean(busy) || released}
            onClick={() => run("release", () => releaseCandidate(execution.jobId, session.ownerId, session.revision))}
          >
            {busy === "release" ? "Releasing…" : "Release"}
          </button>
        </div>
      ) : null}
    </article>
  );
}

function MappingList({ issues }: { issues: MappingIssue[] }) {
  if (issues.length === 0) return null;
  return (
    <div className="status status--warn">
      <p>Unresolved Phase-0 decisions. The saved brief was not changed.</p>
      <ul>
        {issues.map((issue) => (
          <li key={`${issue.code}-${issue.field}`}>
            <strong>{issue.code}</strong> {issue.message}
          </li>
        ))}
      </ul>
    </div>
  );
}
