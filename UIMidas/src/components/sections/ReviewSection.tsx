import { useEffect, useRef, useState } from "react";
import type { JobSubmitResponse } from "../../contract/submitPreparedJob";
import type { ProposedJobContract } from "../../contract/buildJobContract";
import { persistAndPrepareJob, type JobPlanStatus, type MappingIssue, type PreparedExecution } from "../../adapters/prepareJobFromBrief";
import { isMockSubmitResponse } from "../../contract/submitPreparedJob";
import { shouldUseMockSubmit } from "../../adapters/persistClientBrief";
import { resolveJobSubmitAdapter } from "../../adapters/resolveSubmitAdapter";
import { sameSubmitKey, submitPreparedJob } from "../../contract/submitPreparedJob";
import { sectionLabels } from "../../flow";
import { saveJobSession, type JobSession } from "../../lib/jobSession";
import { reviewActions } from "../../lib/reviewModel";
import { normalizeDraft } from "../../normalization/normalizeDraft";
import { useActiveItemId, useClientJobDraft, useResetDraft, useBatchItems } from "../../state/DraftProvider";
import type { SectionId } from "../../types/draft";
import { jobPreparationIssues } from "../../validation/jobPreparation";
import { validateDraft } from "../../validation/validateDraft";
import { SectionIntro } from "../ui/chrome";
import { ReviewSummary } from "./ReviewSummary";

type ReviewOutcome =
  | { type: "idle" }
  | { type: "invalid" }
  | { type: "blocked" }
  | { type: "submitting" }
  | {
      type: "success";
      response: JobSubmitResponse;
      contract: ProposedJobContract;
      stamp: string;
      briefJson: string;
      mappingIssues: MappingIssue[];
      job: JobPlanStatus | null;
      executions: PreparedExecution[];
    }
  | { type: "failed"; message: string; contract: ProposedJobContract };

export function ReviewSection({
  onBack,
  onNavigate,
  onStartOver,
  onJobReady,
}: {
  onBack: () => void;
  onNavigate: (section: SectionId) => void;
  onStartOver: () => void;
  onJobReady?: (session: JobSession) => void;
}) {
  const draft = useClientJobDraft();
  const activeItemId = useActiveItemId();
  const { setActiveItemId } = useBatchItems();
  const reset = useResetDraft();
  const validation = validateDraft(draft, activeItemId);
  const brief = normalizeDraft(draft, activeItemId);
  const briefJson = JSON.stringify(brief, null, 2);
  const [outcome, setOutcome] = useState<ReviewOutcome>({ type: "idle" });
  const [previewOpen, setPreviewOpen] = useState(false);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const keyRef = useRef<string | null>(null);
  const stampRef = useRef("");
  const submittingRef = useRef(false);
  const issuesRef = useRef<HTMLDivElement>(null);
  const successRef = useRef<HTMLHeadingElement>(null);
  const previewRef = useRef<HTMLDetailsElement>(null);

  if (stampRef.current !== briefJson) {
    stampRef.current = briefJson;
    keyRef.current = null;
  }

  const successIsCurrent = outcome.type === "success" && outcome.stamp === briefJson;
  const preparationIssues = shouldUseMockSubmit() ? [] : jobPreparationIssues(draft, activeItemId);
  const errors = [...validation.issues.filter((issue) => issue.severity === "error"), ...preparationIssues];
  const warnings = validation.issues.filter((issue) => issue.severity === "warning");

  useEffect(() => {
    if (outcome.type === "invalid" || outcome.type === "blocked") issuesRef.current?.focus();
    if (outcome.type === "success") successRef.current?.focus();
  }, [outcome]);

  function edit(section: SectionId, itemId?: string) {
    if (itemId) setActiveItemId(itemId);
    onNavigate(section);
  }

  async function submit() {
    if (submittingRef.current) return;
    const current = validateDraft(draft, activeItemId);
    if (!current.valid) {
      setOutcome({ type: "invalid" });
      issuesRef.current?.scrollIntoView({ block: "start" });
      return;
    }
    if (!shouldUseMockSubmit() && jobPreparationIssues(draft, activeItemId).length > 0) {
      setOutcome({ type: "blocked" });
      issuesRef.current?.scrollIntoView({ block: "start" });
      return;
    }

    const key = sameSubmitKey(keyRef.current);
    keyRef.current = key;
    submittingRef.current = true;
    setOutcome({ type: "submitting" });
    const result = shouldUseMockSubmit()
      ? await submitPreparedJob(draft, key, activeItemId, resolveJobSubmitAdapter())
      : await submitPreparedJob(draft, key, activeItemId, async (contract) => {
          const prepared = await persistAndPrepareJob(
            contract,
            draft,
            activeItemId,
          );
          return {
            ...prepared.persist,
            mappingIssues: prepared.mappingIssues,
            job: prepared.job,
            executions: prepared.executions,
          };
        });
    submittingRef.current = false;

    if (result.ok) {
      const extras = result.response as JobSubmitResponse & {
        mappingIssues?: MappingIssue[];
        job?: JobPlanStatus | null;
        executions?: PreparedExecution[];
        briefId?: string;
        ownerId?: string;
        contractId?: string;
        revision?: number;
      };
      const mappingIssues = extras.mappingIssues ?? [];
      const job = extras.job ?? null;
      const executions = extras.executions ?? [];
      if (!isMockSubmitResponse(result.response) && extras.briefId && extras.ownerId && extras.contractId && extras.revision) {
        const session: JobSession = {
          briefId: extras.briefId,
          ownerId: extras.ownerId,
          contractId: extras.contractId,
          revision: extras.revision,
          jobId: executions[0]?.jobId ?? job?.jobId ?? null,
          mappingIssues,
          executions,
        };
        if (session.jobId) {
          saveJobSession(session);
          onJobReady?.(session);
        }
      }
      setOutcome({
        type: "success",
        response: result.response,
        contract: result.contract,
        stamp: briefJson,
        briefJson,
        mappingIssues,
        job,
        executions,
      });
      return;
    }
    if (result.reason === "mock-failed" || result.reason === "persist-failed") {
      setOutcome({ type: "failed", message: result.message, contract: result.contract });
      return;
    }
    setOutcome({ type: "invalid" });
    issuesRef.current?.scrollIntoView({ block: "start" });
  }

  function startAnother() {
    keyRef.current = null;
    setOutcome({ type: "idle" });
    setPreviewOpen(false);
    reset();
    onStartOver();
  }

  function viewSubmittedBrief() {
    setPreviewOpen(true);
    requestAnimationFrame(() => {
      previewRef.current?.scrollIntoView({ block: "start" });
      previewRef.current?.querySelector("summary")?.focus();
    });
  }

  async function copyPreview() {
    const payload =
      outcome.type === "success"
        ? { brief: JSON.parse(outcome.briefJson) as unknown, contract: outcome.contract, response: outcome.response }
        : outcome.type === "failed"
          ? { brief, contract: outcome.contract }
          : { brief };
    try {
      await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  }

  const preparing = outcome.type === "submitting";

  return (
    <div className="stack">
      <SectionIntro
        eyebrow="Review"
        title="Check the brief"
        lede="This is what you are asking Midas to produce. Submitting creates the job. It does not start production."
      />

      {successIsCurrent && outcome.type === "success" ? (
        <div className="job-created">
          <h2 id="job-created" tabIndex={-1} ref={successRef}>
            <span aria-hidden="true">✓ </span>
            {outcome.response.mock ? reviewActions.created : outcome.job ? "Job created" : "Brief saved"}
          </h2>
          {outcome.response.mock ? (
            <p>
              Job ID
              <strong>{outcome.response.jobId}</strong>
            </p>
          ) : (
            <>
              <p>
                Brief ID
                <strong>{outcome.response.briefId}</strong>
              </p>
              {outcome.executions.length > 0 || outcome.job ? (
                <>
                  {(outcome.executions.length > 0 ? outcome.executions : outcome.job ? [{ jobId: outcome.job.jobId, requestedView: "", imageProportions: "", resolution: "", requestedOutcomes: [] }] : []).map((execution) => (
                    <p key={execution.jobId}>
                      {execution.requestedView || "Job ID"}
                      <strong>{execution.jobId}</strong>
                    </p>
                  ))}
                  {outcome.job ? (
                    <p>
                      Plan
                      <strong>
                        {outcome.job.stage} · {outcome.job.state}
                        {outcome.job.compileAvailable ? " · compile ready" : ""}
                      </strong>
                    </p>
                  ) : null}
                  <p className="note">
                    Planning ran on the backend. Generation is not approved and was not started.
                  </p>
                </>
              ) : (
                <p className="note">
                  The brief is saved. A Phase-0 job was not created. Generation was not started.
                  Batch, Projects, saved projects, and catalogue execution are not supported.
                </p>
              )}
              {outcome.mappingIssues.length > 0 ? (
                <div className="status status--warn">
                  <p>The saved brief could not be mapped to Phase-0. These decisions are still unresolved:</p>
                  <ul>
                    {outcome.mappingIssues.map((issue) => (
                      <li key={`${issue.code}-${issue.field}`}>
                        <strong>{issue.code}</strong> {issue.message}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </>
          )}
          <p>
            Contract version
            <strong>{outcome.response.contractVersion}</strong>
          </p>
        </div>
      ) : null}

      {outcome.type === "success" && !successIsCurrent ? (
        <p className="note">The brief changed after the job was created. Submit again when this version is ready.</p>
      ) : null}

      {outcome.type === "failed" ? (
        <div className="status status--warn" aria-live="polite">
          <p>{reviewActions.unable}</p>
          <p>{outcome.message}</p>
          <button type="button" className="btn btn--secondary" onClick={submit}>
            {reviewActions.retry}
          </button>
        </div>
      ) : null}

      {errors.length > 0 || warnings.length > 0 ? (
        <div
          className="issues"
          id="review-issues"
          tabIndex={-1}
          ref={issuesRef}
          role={outcome.type === "invalid" || outcome.type === "blocked" ? "alert" : undefined}
          aria-live="polite"
        >
          {errors.map((entry) => (
            <button
              key={`${entry.path}-${entry.message}`}
              type="button"
              className="issue issue--error"
              onClick={() => edit(entry.section)}
            >
              <span className="issue__where">{sectionLabels[entry.section]}</span>
              <span>{entry.message}</span>
              <span className="issue__edit">Edit</span>
            </button>
          ))}
          {warnings.map((entry) => (
            <button
              key={`${entry.path}-${entry.message}`}
              type="button"
              className="issue issue--warning"
              onClick={() => edit(entry.section)}
            >
              <span className="issue__where">{sectionLabels[entry.section]}</span>
              <span>{entry.message}</span>
              <span className="issue__edit">Edit</span>
            </button>
          ))}
        </div>
      ) : null}

      <ReviewSummary draft={draft} activeItemId={activeItemId} onEdit={edit} />

      {shouldUseMockSubmit() ? (
        <p className="note">Mock submit stores the brief only. It does not create a job.</p>
      ) : (
        <p className="note">Submitting saves the brief, then creates a job from it. Generation stays behind an explicit approval.</p>
      )}

      <div className="step-footer">
        <button type="button" className="btn btn--ghost" onClick={onBack}>
          Back
        </button>
        {successIsCurrent ? (
          <div className="button-row">
            <button type="button" className="btn btn--secondary" onClick={viewSubmittedBrief}>
              {reviewActions.viewBrief}
            </button>
            <button type="button" className="btn btn--primary" onClick={startAnother}>
              {reviewActions.startAnother}
            </button>
          </div>
        ) : (
          <div className="button-row" aria-live="polite">
            <button type="button" className="btn btn--ghost" onClick={startAnother} disabled={preparing}>
              Start over
            </button>
            <button type="button" className="btn btn--primary" onClick={submit} disabled={preparing} aria-busy={preparing}>
              {preparing ? reviewActions.preparing : reviewActions.submit}
            </button>
          </div>
        )}
      </div>

      <details
        className="debug-panel"
        id="development-preview"
        ref={previewRef}
        open={previewOpen}
        onToggle={(event) => setPreviewOpen(event.currentTarget.open)}
      >
        <summary>Development preview</summary>
        <div className="debug-panel__body">
          <div className="debug-panel__head">
            <p>
              Development only. The summary above is the brief. This is the normalized request, the proposed
              contract, and the persist or mock response when one exists. Equivalence with the published Client
              Studio page is unverified.
            </p>
            <button type="button" className="btn btn--secondary" onClick={copyPreview}>
              {copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed" : "Copy preview"}
            </button>
          </div>
          {outcome.type === "success" || outcome.type === "failed" ? (
            <p>Idempotency key: {outcome.contract.idempotencyKey}</p>
          ) : (
            <p>The idempotency key is created when you submit, and reused if that submit is retried.</p>
          )}
          <pre>{outcome.type === "success" ? outcome.briefJson : briefJson}</pre>
          {outcome.type === "failed" ? <p>{outcome.message}</p> : null}
          {outcome.type === "success" || outcome.type === "failed" ? <pre>{JSON.stringify(outcome.contract, null, 2)}</pre> : null}
          {outcome.type === "success" ? <pre>{JSON.stringify(outcome.response, null, 2)}</pre> : null}
        </div>
      </details>
    </div>
  );
}
