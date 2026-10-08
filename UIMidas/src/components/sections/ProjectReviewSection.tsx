import { useEffect, useRef, useState } from "react";
import type { MockSubmitResponse } from "../../adapters/mockSubmitJob";
import {
  submitPreparedProject,
  type PreparedProject,
  type ProjectSubmitAdapter,
} from "../../contract/submitPreparedProject";
import { sameSubmitKey } from "../../contract/submitPreparedJob";
import { projectIssues, projectReviewFacts, type ProjectBrief, type ProjectPlace } from "../../lib/projectBrief";
import { reviewActions } from "../../lib/reviewModel";
import { SectionIntro } from "../ui/chrome";

type ReviewOutcome =
  | { type: "idle" }
  | { type: "invalid" }
  | { type: "submitting" }
  | { type: "success"; response: MockSubmitResponse; prepared: PreparedProject; stamp: string }
  | { type: "failed"; message: string; prepared: PreparedProject };

export function ProjectReviewSection({
  brief,
  onBack,
  onEdit,
  onStartOver,
  submitAdapter,
}: {
  brief: ProjectBrief;
  onBack: () => void;
  onEdit: (place: ProjectPlace) => void;
  onStartOver: () => void;
  submitAdapter?: ProjectSubmitAdapter;
}) {
  const issues = projectIssues(brief);
  const sections = projectReviewFacts(brief);
  const stamp = JSON.stringify(brief);
  const [outcome, setOutcome] = useState<ReviewOutcome>({ type: "idle" });
  const [previewOpen, setPreviewOpen] = useState(false);
  const keyRef = useRef<string | null>(null);
  const stampRef = useRef("");
  const submittingRef = useRef(false);
  const issuesRef = useRef<HTMLDivElement>(null);
  const successRef = useRef<HTMLHeadingElement>(null);
  const placeLabel: Record<ProjectPlace, string> = {
    project: "Project",
    item: "The Item",
    scope: "Scope",
  };

  if (stampRef.current !== stamp) {
    stampRef.current = stamp;
    keyRef.current = null;
  }

  const successIsCurrent = outcome.type === "success" && outcome.stamp === stamp;
  const preparing = outcome.type === "submitting";

  useEffect(() => {
    if (outcome.type === "invalid") issuesRef.current?.focus();
    if (outcome.type === "success") successRef.current?.focus();
  }, [outcome]);

  async function submit() {
    if (submittingRef.current) return;
    const current = projectIssues(brief);
    if (current.length > 0) {
      setOutcome({ type: "invalid" });
      issuesRef.current?.scrollIntoView({ block: "start" });
      return;
    }

    const key = sameSubmitKey(keyRef.current);
    keyRef.current = key;
    submittingRef.current = true;
    setOutcome({ type: "submitting" });
    const result = await submitPreparedProject(brief, key, submitAdapter);
    submittingRef.current = false;

    if (result.ok) {
      setOutcome({ type: "success", response: result.response, prepared: result.prepared, stamp });
      return;
    }
    if (result.reason === "mock-failed") {
      setOutcome({ type: "failed", message: result.message, prepared: result.prepared });
      return;
    }
    setOutcome({ type: "invalid" });
    issuesRef.current?.scrollIntoView({ block: "start" });
  }

  function startAnother() {
    keyRef.current = null;
    setOutcome({ type: "idle" });
    setPreviewOpen(false);
    onStartOver();
  }

  const preparedJson =
    outcome.type === "success" || outcome.type === "failed" ? JSON.stringify(outcome.prepared.submission, null, 2) : "";

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

      {issues.length > 0 ? (
        <div
          className="issues"
          id="review-issues"
          tabIndex={-1}
          ref={issuesRef}
          role={outcome.type === "invalid" ? "alert" : undefined}
          aria-live="polite"
        >
          {issues.map((entry) => (
            <button
              key={`${entry.place}-${entry.message}`}
              type="button"
              className="issue issue--error"
              onClick={() => onEdit(entry.place)}
            >
              <span className="issue__where">{placeLabel[entry.place]}</span>
              <span>{entry.message}</span>
              <span className="issue__edit">Edit</span>
            </button>
          ))}
        </div>
      ) : null}

      <div className="summary">
        {sections.map((section) => (
          <section className="summary__card" key={section.place} aria-labelledby={`project-review-${section.place}`}>
            <div className="summary__head">
              <h2 id={`project-review-${section.place}`}>{section.title}</h2>
              <button type="button" className="btn btn--ghost" aria-label={`Edit ${section.title.toLowerCase()}`} onClick={() => onEdit(section.place)}>
                Edit
              </button>
            </div>
            <div className="summary__group">
              {section.lines.map((line, index) =>
                line.label ? (
                  <dl key={`${section.place}-${index}`}>
                    <div className="fact">
                      <dt>{line.label}</dt>
                      <dd>{line.text}</dd>
                    </div>
                  </dl>
                ) : (
                  <p key={`${section.place}-${index}`}>{line.text}</p>
                ),
              )}
            </div>
          </section>
        ))}
      </div>

      <div className="step-footer">
        <button type="button" className="btn btn--ghost" onClick={onBack}>
          Back
        </button>
        {successIsCurrent ? (
          <div className="button-row">
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

      <details className="debug-panel" open={previewOpen} onToggle={(event) => setPreviewOpen(event.currentTarget.open)}>
        <summary>Development preview</summary>
        <div className="debug-panel__body">
          <p>Development only. This is the Projects submission that can be represented with the current fields, and the mock response when one exists.</p>
          {outcome.type === "success" || outcome.type === "failed" ? <p>Idempotency key: {outcome.prepared.submission.idempotencyKey}</p> : <p>The idempotency key is created when you submit, and reused if that submit is retried.</p>}
          {preparedJson ? <pre>{preparedJson}</pre> : null}
          {outcome.type === "failed" ? <p>{outcome.message}</p> : null}
          {outcome.type === "success" ? <pre>{JSON.stringify(outcome.response, null, 2)}</pre> : null}
        </div>
      </details>
    </div>
  );
}
