export function SectionIntro({
  eyebrow,
  title,
  lede,
}: {
  eyebrow: string;
  title: string;
  lede: string;
}) {
  return (
    <header className="section-intro">
      <p className="eyebrow">{eyebrow}</p>
      <h2 id="section-title" tabIndex={-1}>
        {title}
      </h2>
      <p className="lede">{lede}</p>
    </header>
  );
}

export function StepFooter({
  onBack,
  onContinue,
  continueLabel = "Continue",
  continueDisabled = false,
  showMoreOptions = true,
}: {
  onBack?: () => void;
  onContinue?: () => void;
  continueLabel?: string;
  continueDisabled?: boolean;
  showMoreOptions?: boolean;
}) {
  return (
    <div className="step-footer">
      <div className="step-footer__side">
        {onBack ? (
          <button type="button" className="btn btn--ghost" onClick={onBack}>
            Back
          </button>
        ) : null}
        {showMoreOptions ? (
          <details className="more-options">
            <summary>More options</summary>
          </details>
        ) : null}
      </div>
      {onContinue ? (
        <button type="button" className="btn btn--primary" onClick={onContinue} disabled={continueDisabled}>
          {continueLabel}
        </button>
      ) : null}
    </div>
  );
}
