import { useEffect, useRef } from "react";
import { useMagneticCards } from "../../motion/studioMotion";
import { editModeOptions, jobKindOptions } from "../../config/options";
import { useJobDraft } from "../../state/DraftProvider";
import type { EditMode, JobDraft, JobKind, NewProjectMode, SingleItemRole } from "../../types/draft";
import { isJobReady } from "../../validation/validateDraft";
import { StepFooter } from "../ui/chrome";

const jobTypes: { value: JobKind; label: string }[] = [
  { value: "new_project", label: "New Project" },
  { value: "edit", label: "Edit" },
  { value: "single_item", label: "Single item" },
];

const workModes: { value: NewProjectMode; label: string }[] = [
  { value: "batch", label: "Batch" },
  { value: "one_by_one", label: "One by one (same department)" },
];

const editModes = editModeOptions.map((option) => ({ value: option.value, label: option.label }));
const editSupport = jobKindOptions.find((option) => option.value === "edit")?.description ?? "";
/** The application has no saved-project source. The Edit screen must not use mockSavedBriefs. */
const savedProjects: readonly { id: string; label: string }[] = [];
const noSavedProjectsMessage = "No saved projects are currently available. Select New item to continue.";

const itemRoles: { value: SingleItemRole; label: string }[] = [
  { value: "hero", label: "Hero" },
  { value: "secondary", label: "Secondary" },
];

function jobChoiceReady(job: JobDraft): boolean {
  if (job.kind === "edit") return job.editMode !== null;
  return isJobReady(job);
}

export function JobSection({ onContinue }: { onContinue: () => void }) {
  const [job, setJob] = useJobDraft();
  const cardsRef = useRef<HTMLDivElement>(null);
  useMagneticCards(cardsRef, ".job-card");

  useEffect(() => {
    if (job.kind !== null) return;
    setJob(() => ({
      kind: "new_project",
      newProjectMode: null,
      editMode: null,
      savedItemId: null,
      singleItemRole: null,
    }));
  }, [job.kind, setJob]);

  function selectKind(kind: JobKind) {
    setJob(() => ({
      kind,
      newProjectMode: null,
      editMode: null,
      savedItemId: null,
      singleItemRole: null,
    }));
  }

  function selectNewProjectMode(mode: NewProjectMode) {
    setJob((current) => ({ ...current, newProjectMode: mode }));
  }

  function selectEditMode(mode: EditMode) {
    setJob((current) => ({
      ...current,
      editMode: mode,
      savedItemId: mode === "choose_from_saving" ? current.savedItemId : null,
    }));
  }

  function selectRole(role: SingleItemRole) {
    setJob((current) => ({ ...current, singleItemRole: role }));
  }

  function selectSavedBrief(id: string) {
    setJob((current) => ({ ...current, savedItemId: id }));
  }


  return (
    <div className="stack job">
      <h2 className="job__title" id="section-title" tabIndex={-1}>
        What would you like to do?
      </h2>

      <div className="choice-grid choice-grid--jobs" role="group" aria-label="Job type" ref={cardsRef}>
        {jobTypes.map((option) => {
          const selected = job.kind === option.value;
          return (
            <div key={option.value} className={selected ? "job-card job-card--open" : "job-card"}>
              <button type="button" className="job-card__select" aria-pressed={selected} onClick={() => selectKind(option.value)}>
                <span className="job-card__title">{option.label}</span>
                {selected ? <span className="job-card__check" aria-hidden="true" /> : <span className="job-card__arrow" aria-hidden="true">→</span>}
              </button>
              {selected && option.value === "new_project" ? (
                <ChoicePills label="Work on" options={workModes} selected={job.newProjectMode} onSelect={selectNewProjectMode} />
              ) : null}
              {selected && option.value === "edit" ? (
                <>
                  {editSupport ? <p className="field-label">{editSupport}</p> : null}
                  <ChoicePills label="Start from" options={editModes} selected={job.editMode} onSelect={selectEditMode} />
                  {job.editMode === "choose_from_saving" ? (
                    <SavedBriefChoices briefs={savedProjects} selectedId={job.savedItemId} onSelect={selectSavedBrief} />
                  ) : null}
                </>
              ) : null}
              {selected && option.value === "single_item" ? (
                <ChoicePills label="Item role" options={itemRoles} selected={job.singleItemRole} onSelect={selectRole} />
              ) : null}
            </div>
          );
        })}
      </div>

      <StepFooter
        onContinue={onContinue}
        continueLabel="Continue to the item"
        continueDisabled={!jobChoiceReady(job)}
        showMoreOptions={false}
      />
    </div>
  );
}

export function SavedBriefChoices({
  briefs,
  selectedId,
  onSelect,
}: {
  briefs: readonly { id: string; label: string }[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (briefs.length === 0) {
    return (
      <div className="job-work">
        <p className="job-work__label">{noSavedProjectsMessage}</p>
      </div>
    );
  }
  return (
    <div className="job-work">
      <p className="job-work__label" id="saved-brief-label">
        Saved brief
      </p>
      <div className="pill-row" role="group" aria-labelledby="saved-brief-label">
        {briefs.map((brief) => {
          const pressed = selectedId === brief.id;
          return (
            <button key={brief.id} type="button" className="pill" aria-pressed={pressed} onClick={() => onSelect(brief.id)}>
              {brief.label}
              {pressed ? <CheckMark /> : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ChoicePills<T extends string>({
  label,
  options,
  selected,
  onSelect,
}: {
  label: string;
  options: { value: T; label: string }[];
  selected: T | null;
  onSelect: (value: T) => void;
}) {
  return (
    <div className="job-work">
      <p className="job-work__label" id="job-secondary-label">
        {label}
      </p>
      <div className="pill-row" role="group" aria-labelledby="job-secondary-label">
        {options.map((option) => {
          const pressed = selected === option.value;
          return (
            <button key={option.value} type="button" className="pill" aria-pressed={pressed} onClick={() => onSelect(option.value)}>
              {option.label}
              {pressed ? <CheckMark /> : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function CheckMark() {
  return (
    <svg className="pill__check" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M3.5 8.2 6.4 11 12.5 5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
