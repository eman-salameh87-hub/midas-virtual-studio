import { useRef } from "react";
import { projectStartingPoints, type ProjectStart } from "../../lib/projectBrief";
import { useMagneticCards } from "../../motion/studioMotion";
import { StepFooter } from "../ui/chrome";

export type { ProjectStart };

export function ProjectSection({
  start,
  existingRoom,
  newStyledSpace,
  onStart,
  onExistingRoom,
  onNewStyledSpace,
  onContinue,
}: {
  start: ProjectStart;
  existingRoom: string;
  newStyledSpace: string;
  onStart: (start: ProjectStart) => void;
  onExistingRoom: (value: string) => void;
  onNewStyledSpace: (value: string) => void;
  onContinue: () => void;
}) {
  const cardsRef = useRef<HTMLDivElement>(null);
  useMagneticCards(cardsRef, ".project-card");

  return (
    <div className="stack project">
      <h2 className="project__title" id="section-title" tabIndex={-1}>
        Where would you like to begin?
      </h2>
      <div className="project-grid" role="group" aria-label="Starting point" ref={cardsRef}>
        {projectStartingPoints.map((option) => {
          const selected = start === option.id;
          return (
            <button
              key={option.id}
              type="button"
              className="project-card"
              aria-pressed={selected}
              onClick={() => onStart(option.id)}
            >
              <span className="project-card__title">{option.title}</span>
              <span className="project-card__hint">{option.description}</span>
              {selected ? <span className="project-card__check" aria-hidden="true" /> : null}
            </button>
          );
        })}
      </div>

      {start === "existing_room" ? (
        <label className="field field--wide">
          <span>What should stay or change?</span>
          <textarea
            rows={4}
            value={existingRoom}
            placeholder="Keep the windows and floor. Replace the seating with the supplied set."
            onChange={(event) => onExistingRoom(event.target.value)}
          />
        </label>
      ) : null}

      {start === "new_styled_space" ? (
        <label className="field field--wide">
          <span>Describe the space to create</span>
          <textarea
            rows={4}
            value={newStyledSpace}
            placeholder="A relaxed living room with the supplied sofa as the main subject."
            onChange={(event) => onNewStyledSpace(event.target.value)}
          />
        </label>
      ) : null}

      {start === "saved_project" ? <p className="project__empty">No saved projects yet. Choose a different starting point</p> : null}

      <StepFooter onContinue={onContinue} continueLabel="Continue to the item" showMoreOptions={false} />
    </div>
  );
}
