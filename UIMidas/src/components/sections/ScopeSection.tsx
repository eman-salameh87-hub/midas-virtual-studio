import { deliveryProportionOptions, deliveryResolutionOptions, deliveryViewOptions, outputConceptOptions } from "../../config/options";
import { createId } from "../../lib/ids";
import { useScopeDraft } from "../../state/DraftProvider";
import type {
  ImageProportion,
  ImageResolution,
  OutputConcept,
  OutputView,
  ScopeDraft,
  ScopeOutput,
  VariationAspect,
} from "../../types/draft";
import { StepFooter } from "../ui/chrome";
import { ChoiceCard, NumberField, TextField } from "../ui/controls";

const conceptOrder = outputConceptOptions.map((option) => option.value);

const conceptDescriptions: Record<OutputConcept, string> = {
  white_bk: "Clean catalogue imagery",
  lifestyle: "The item in a styled setting",
  website: "A complete product image set",
  new_composition: "Arrange a coordinated space",
  variations: "Explore light, style and views",
  create_with_this_item: "Let this item lead the design",
  others: "Describe a different outcome",
};

const defaultView: OutputView = "category_template";
const defaultProportion: ImageProportion = "standard_for_category";
const defaultResolution: ImageResolution = "standard_for_category";

const variationAspectOptions: { value: VariationAspect; label: string }[] = [
  { value: "lighting", label: "Lighting" },
  { value: "styling", label: "Styling" },
  { value: "camera_view", label: "Camera view" },
];

export function ScopeSection({ onBack, onContinue }: { onBack: () => void; onContinue: () => void }) {
  const [scope, setScope] = useScopeDraft();
  const variations = scope.outputs.find((output) => output.concept === "variations") ?? null;
  const others = scope.outputs.find((output) => output.concept === "others") ?? null;
  const selectedAspects = variations?.variationAspects ?? [];

  function toggleConcept(concept: OutputConcept) {
    setScope((current) => {
      const exists = current.outputs.some((output) => output.concept === concept);
      const outputs = exists
        ? current.outputs.filter((output) => output.concept !== concept)
        : [...current.outputs, emptyOutput(concept, current)].sort(
            (a, b) => conceptOrder.indexOf(a.concept) - conceptOrder.indexOf(b.concept),
          );
      return { ...current, outputs };
    });
  }

  function patchOutput(id: string, patch: Partial<ScopeOutput>) {
    setScope((current) => ({
      ...current,
      outputs: current.outputs.map((output) => (output.id === id ? { ...output, ...patch } : output)),
    }));
  }

  function toggleAspect(aspect: VariationAspect) {
    if (!variations) return;
    const next = selectedAspects.includes(aspect)
      ? selectedAspects.filter((item) => item !== aspect)
      : [...selectedAspects, aspect];
    patchOutput(variations.id, { variationAspects: next });
  }

  function setDelivery(patch: { view?: OutputView | null; proportion?: ImageProportion | null; resolution?: ImageResolution | null }) {
    setScope((current) => ({
      ...current,
      deliveryView: patch.view !== undefined ? patch.view : current.deliveryView,
      deliveryProportion: patch.proportion !== undefined ? patch.proportion : current.deliveryProportion,
      deliveryResolution: patch.resolution !== undefined ? patch.resolution : current.deliveryResolution,
      outputs: current.outputs.map((output) => ({
        ...output,
        views: patch.view !== undefined ? (patch.view ? [patch.view] : []) : output.views,
        proportion: patch.proportion !== undefined ? patch.proportion : output.proportion,
        resolution: patch.resolution !== undefined ? patch.resolution : output.resolution,
      })),
    }));
  }

  return (
    <div className="stack scope">
      <header className="scope__intro">
        <h2 className="scope__title" id="section-title" tabIndex={-1}>
          What would you like to create?
        </h2>
        <p className="lede">Select one or more.</p>
      </header>

      <div className="choice-grid choice-grid--outcomes">
        {outputConceptOptions.map((option) => (
          <ChoiceCard
            key={option.value}
            type="checkbox"
            name="scope-output"
            value={option.value}
            label={option.label}
            description={conceptDescriptions[option.value]}
            checked={scope.outputs.some((output) => output.concept === option.value)}
            onChange={() => toggleConcept(option.value)}
          />
        ))}
      </div>

      {variations ? (
        <section className="scope-follow" aria-labelledby="vary-title">
          <h3 id="vary-title">What should vary?</h3>
          <div className="choice-grid choice-grid--vary">
            {variationAspectOptions.map((option) => (
              <ChoiceCard
                key={option.value}
                type="checkbox"
                name="variation-aspect"
                value={option.value}
                label={option.label}
                checked={selectedAspects.includes(option.value)}
                onChange={() => toggleAspect(option.value)}
              />
            ))}
          </div>
          <NumberField
            id={`variations-${variations.id}`}
            label="Count"
            narrow
            value={variations.variationCount}
            onChange={(variationCount) => patchOutput(variations.id, { variationCount })}
          />
        </section>
      ) : null}

      {others ? (
        <TextField
          id={`other-${others.id}`}
          label="Describe the other outcome"
          placeholder="What would you like to receive?"
          multiline
          value={others.otherLabel}
          onChange={(otherLabel) => patchOutput(others.id, { otherLabel })}
        />
      ) : null}

      <details className="delivery" open>
        <summary>View & delivery</summary>
        <div className="delivery-list">
          <label className="delivery-row">
            <span>Views</span>
            <select
              value={shown(displayedView(scope), deliveryViewOptions, defaultView)}
              onChange={(event) => setDelivery({ view: event.target.value as OutputView })}
            >
              {deliveryViewOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="delivery-row">
            <span>Image proportions</span>
            <select
              value={shown(displayedProportion(scope), deliveryProportionOptions, defaultProportion)}
              onChange={(event) => setDelivery({ proportion: event.target.value as ImageProportion })}
            >
              {deliveryProportionOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="delivery-row">
            <span>Resolution</span>
            <select
              value={shown(displayedResolution(scope), deliveryResolutionOptions, defaultResolution)}
              onChange={(event) => setDelivery({ resolution: event.target.value as ImageResolution })}
            >
              {deliveryResolutionOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </details>

      <StepFooter onBack={onBack} onContinue={onContinue} />
    </div>
  );
}

function emptyOutput(concept: OutputConcept, scope: ScopeDraft): ScopeOutput {
  return {
    id: createId(),
    concept,
    otherLabel: "",
    views: scope.deliveryView ? [scope.deliveryView] : [],
    proportion: scope.deliveryProportion ?? null,
    resolution: scope.deliveryResolution ?? null,
    variationCount: null,
  };
}

function displayedView(scope: ScopeDraft): string {
  return sharedValue(
    scope.outputs.map((output) => (output.views.length === 1 ? output.views[0] : output.views.length === 0 ? null : "mixed")),
    scope.deliveryView ?? null,
  );
}

function displayedProportion(scope: ScopeDraft): string {
  return sharedValue(
    scope.outputs.map((output) => output.proportion),
    scope.deliveryProportion ?? null,
  );
}

function displayedResolution(scope: ScopeDraft): string {
  return sharedValue(
    scope.outputs.map((output) => output.resolution),
    scope.deliveryResolution ?? null,
  );
}

function sharedValue(values: (string | null | "mixed")[], fallback: string | null): string {
  if (values.length === 0) return fallback ?? "";
  if (values.some((value) => value === "mixed")) return "";
  const first = values[0];
  if (values.every((value) => value === first)) return first ?? "";
  return "";
}

function shown(value: string, options: readonly { value: string }[], fallback: string): string {
  return options.some((option) => option.value === value) ? value : fallback;
}
