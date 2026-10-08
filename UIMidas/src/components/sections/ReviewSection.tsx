import { useEffect, useRef, useState } from "react";
import type { MockSubmitResponse } from "../../adapters/mockSubmitJob";
import type { ProposedJobContract } from "../../contract/buildJobContract";
import { sameSubmitKey, submitPreparedJob } from "../../contract/submitPreparedJob";
import { sectionLabels } from "../../flow";
import { reviewActions } from "../../lib/reviewModel";
import { normalizeDraft } from "../../normalization/normalizeDraft";
import { useActiveItemId, useClientJobDraft, useResetDraft, useBatchItems } from "../../state/DraftProvider";
import type { SectionId } from "../../types/draft";
import { validateDraft } from "../../validation/validateDraft";
import { SectionIntro } from "../ui/chrome";
import { ReviewSummary } from "./ReviewSummary";

type ReviewOutcome =
  | { type: "idle" }
  | { type: "invalid" }
  | { type: "submitting" }
  | { type: "success"; response: MockSubmitResponse; contract: ProposedJobContract; stamp: string; briefJson: string }
  | { type: "failed"; message: string; contract: ProposedJobContract };

export function ReviewSection({
  onBack,
  onNavigate,
  onStartOver,
}: {
  onBack: () => void;
  onNavigate: (section: SectionId) => void;
  onStartOver: () => void;
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
  const errors = validation.issues.filter((issue) => issue.severity === "error");
  const warnings = validation.issues.filter((issue) => issue.severity === "warning");

  useEffect(() => {
    if (outcome.type === "invalid") issuesRef.current?.focus();
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

    const key = sameSubmitKey(keyRef.current);
    keyRef.current = key;
    submittingRef.current = true;
    setOutcome({ type: "submitting" });
    const result = await submitPreparedJob(draft, key, activeItemId);
    submittingRef.current = false;

    if (result.ok) {
      setOutcome({
        type: "success",
        response: result.response,
        contract: result.contract,
        stamp: briefJson,
        briefJson,
      });
      return;
    }
    if (result.reason === "mock-failed") {
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
            {reviewActions.created}
          </h2>
          <p>
            Job ID
            <strong>{outcome.response.jobId}</strong>
          </p>
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
          role={outcome.type === "invalid" ? "alert" : undefined}
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
            <p>Development only. The summary above is the brief. This is the normalized request, the proposed contract, and the mock response when one exists.</p>
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
