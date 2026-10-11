import { moodOptions } from "../../config/options";
import { useSuggestionsDraft } from "../../state/DraftProvider";
import type { MoodVibe } from "../../types/draft";
import { StepFooter } from "../ui/chrome";
import { StudioSelect } from "../ui/StudioSelect";

export function SuggestionsSection({ onBack, onContinue }: { onBack: () => void; onContinue: () => void }) {
  const [suggestions, setSuggestions] = useSuggestionsDraft();

  function togglePlants() {
    setSuggestions((current) => ({
      ...current,
      plants: current.plants === "suggest" ? "leave_out" : "suggest",
    }));
  }

  function toggleHuman() {
    setSuggestions((current) => ({
      ...current,
      human: current.human === "suggest" ? "leave_out" : "suggest",
    }));
  }

  function setMood(mood: MoodVibe) {
    setSuggestions((current) => ({ ...current, mood }));
  }

  return (
    <div className="stack suggestions">
      <h2 className="suggestions__title" id="section-title" tabIndex={-1}>
        Add the finishing touches.
      </h2>

      <fieldset className="suggestions__group">
        <legend>Styling suggestions</legend>
        <div className="finish-grid">
          <button type="button" className="finish" aria-pressed={suggestions.plants === "suggest"} onClick={togglePlants}>
            <span className="finish__copy">
              <PlantMark />
              <span>
                <strong>Plants</strong>
                <span>Natural accents</span>
              </span>
            </span>
            <span className="finish__switch" aria-hidden="true" />
          </button>
          <button type="button" className="finish" aria-pressed={suggestions.human === "suggest"} onClick={toggleHuman}>
            <span className="finish__copy">
              <PersonMark />
              <span>
                <strong>Human</strong>
                <span>Lifestyle presence</span>
              </span>
            </span>
            <span className="finish__switch" aria-hidden="true" />
          </button>
        </div>
      </fieldset>

      <label className="select-field select-field--type">
        <span>Mood / Vibes</span>
        <StudioSelect
          value={suggestions.mood ?? "automatic"}
          options={moodOptions}
          onChange={(mood) => setMood(mood as MoodVibe)}
        />
      </label>

      <StepFooter onBack={onBack} onContinue={onContinue} continueLabel="Review choices" />
    </div>
  );
}

function PlantMark() {
  return (
    <svg className="finish__icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.5 19 2c1 2 2 4.2 2 8 0 5.5-4.8 10-10 10Z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M2 21c0-3 1.8-5.4 5.1-6C9.5 14.5 12 13 13 12" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function PersonMark() {
  return (
    <svg className="finish__icon" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="8" r="4" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <path d="M20 21a8 8 0 0 0-16 0" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
