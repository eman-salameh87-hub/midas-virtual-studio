import { useEffect, useRef, type ReactNode } from "react";
import { useAmbientStudioLight } from "../../motion/studioMotion";

export function StudioShell({
  section,
  onSection,
  steps,
  mode,
  onMode,
  children,
}: {
  section: string;
  onSection: (section: string) => void;
  steps: { id: string; index: string; label: string }[];
  mode: "projects" | "manual";
  onMode: (mode: "projects" | "manual") => void;
  children: ReactNode;
}) {
  const firstRender = useRef(true);
  const stageRef = useRef<HTMLDivElement>(null);
  const review = section === "review";
  const studioHome = section === "job" || section === "project";
  const namedStep = studioHome || section === "item";
  useAmbientStudioLight(stageRef, studioHome);
  const current = Math.max(0, steps.findIndex((step) => step.id === section));
  const progress = `${Math.round(((current + 1) / (steps.length + 1)) * 100)}%`;

  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    document.getElementById("section-title")?.focus();
  }, [section]);

  const switcher = (
    <div className="mode-switch" role="group" aria-label="Create mode">
      <button type="button" aria-pressed={mode === "projects"} onClick={() => onMode("projects")}>Projects</button>
      <button type="button" aria-pressed={mode === "manual"} onClick={() => onMode("manual")}>Manual</button>
    </div>
  );

  const navigation = (
    <nav className="steps" aria-label="Brief sections">
      {steps.map((step) => (
        <span className="steps__item" key={step.id}>
          <button type="button" aria-current={section === step.id ? "step" : undefined} onClick={() => onSection(step.id)}>
            <span className="steps__num">{step.index}</span>
            <span>{step.label}</span>
          </button>
        </span>
      ))}
    </nav>
  );

  const stage = (
    <div key={`${mode}-${section}`} className={namedStep ? "step-stage step-stage--flow" : "step-stage"}>
      {children}
    </div>
  );

  if (review) {
    return (
      <div className="studio studio--review">
        <a className="skip" href="#brief">
          Skip to brief
        </a>
        <div className="app">
          <aside className="side">
            <Brand />
            {switcher}
            {navigation}
          </aside>
          <div className="main">
            <main id="brief">{stage}</main>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="studio studio--stage">
      <a className="skip" href="#brief">
        Skip to brief
      </a>
      <div className="stage" ref={stageRef}>
        <div className="orb orb--one" aria-hidden="true" />
        <div className="orb orb--two" aria-hidden="true" />
        <div className="orb orb--three" aria-hidden="true" />
        {studioHome ? <div className="stage__glow" aria-hidden="true" /> : null}
        {section === "job" || section === "project" ? <svg className="stage__art" viewBox="0 0 560 480" aria-hidden="true">
          <path className="stage__art-fill" d="M400 190 L500 190 L560 440 L340 440 Z" />
          <path d="M80 360 V300 Q80 240 140 240 H260 Q320 240 320 300 V360" />
          <path d="M60 360 H340 Q350 360 350 372 V400 H50 V372 Q50 360 60 360 Z" style={{ animationDelay: "0.6s" }} />
          <path d="M80 400 V440 M320 400 V440" style={{ animationDelay: "1.2s" }} />
          <path d="M420 110 H480 L500 190 H400 Z" style={{ animationDelay: "1.4s" }} />
          <path d="M450 190 V440 M420 440 H480" style={{ animationDelay: "1.8s" }} />
          <path d="M20 440 H540" style={{ animationDelay: "2.2s" }} />
        </svg> : null}
        <header className="stage__top">
          <Brand />
          {switcher}
        </header>
        <div className="stage__nav">
          {navigation}
          <div className="stage__bar" aria-hidden="true">
            <div style={{ width: progress }} />
          </div>
        </div>
        <main id="brief" className="stage__body">
          {stage}
        </main>
      </div>
    </div>
  );
}

function Brand() {
  return (
    <h1 className="brand">
      midas <i>Virtual Studio</i>
      <span className="sr-only">Start creating.</span>
    </h1>
  );
}
