import { floorOptions, lightingOptions, wallOptions } from "../../config/options";
import { usePreferencesDraft, useScopeDraft } from "../../state/DraftProvider";
import type { FloorPreference, LightingPreference, WallPreference } from "../../types/draft";
import { StepFooter } from "../ui/chrome";
import { ChoiceCard, OptionGroup, SwatchButton, SwitchRow } from "../ui/controls";

export function PreferencesSection({ onBack, onContinue }: { onBack: () => void; onContinue: () => void }) {
  const [preferences, setPreferences] = usePreferencesDraft();
  const [scope] = useScopeDraft();
  const onlyWhite = scope.outputs.length > 0 && scope.outputs.every((output) => output.concept === "white_bk");
  const showRoom = !preferences.useWorkflowDefaults && !onlyWhite;

  function setDefaults(useWorkflowDefaults: boolean) {
    setPreferences(() => ({
      useWorkflowDefaults,
      lighting: null,
      wall: null,
      floor: null,
    }));
  }

  function selectLighting(lighting: LightingPreference) {
    setPreferences((current) => ({
      ...current,
      lighting: current.lighting === lighting ? null : lighting,
    }));
  }

  function selectWall(wall: WallPreference) {
    setPreferences((current) => ({
      ...current,
      wall: current.wall === wall ? null : wall,
    }));
  }

  function selectFloor(floor: FloorPreference) {
    setPreferences((current) => ({
      ...current,
      floor: current.floor === floor ? null : floor,
    }));
  }

  return (
    <div className="stack prefs">
      <header className="prefs__intro">
        <h2 className="prefs__title" id="section-title" tabIndex={-1}>
          Preferences
        </h2>
        <p className="lede">Room preferences are not needed for white-background images.</p>
      </header>

      {showRoom ? (
        <>
          <OptionGroup legend="Lighting">
            <div className="choice-grid">
              {lightingOptions.map((option) => (
                <ChoiceCard
                  key={option.value}
                  type="toggle"
                  name="lighting"
                  value={option.value}
                  label={option.label}
                  checked={preferences.lighting === option.value}
                  onChange={() => selectLighting(option.value)}
                />
              ))}
            </div>
          </OptionGroup>

          <OptionGroup legend="Wall paint">
            <div className="swatch-grid">
              {wallOptions.map((option) => (
                <SwatchButton
                  key={option.value}
                  label={option.label}
                  swatch={option.swatch}
                  pressed={preferences.wall === option.value}
                  onClick={() => selectWall(option.value)}
                />
              ))}
            </div>
          </OptionGroup>

          <OptionGroup legend="Floor">
            <div className="swatch-grid swatch-grid--floor">
              {floorOptions.map((option) => (
                <SwatchButton
                  key={option.value}
                  label={option.label}
                  swatch={option.swatch}
                  pressed={preferences.floor === option.value}
                  onClick={() => selectFloor(option.value)}
                />
              ))}
            </div>
          </OptionGroup>
        </>
      ) : null}

      <SwitchRow
        checked={preferences.useWorkflowDefaults}
        onChange={setDefaults}
        title="Use workflow defaults"
      />

      <StepFooter onBack={onBack} onContinue={onContinue} />
    </div>
  );
}
