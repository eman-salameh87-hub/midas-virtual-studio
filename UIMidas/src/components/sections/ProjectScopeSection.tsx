import { outputConceptOptions } from "../../config/options";
import { createId } from "../../lib/ids";
import type { ProjectScopeOutput } from "../../lib/projectBrief";
import type { OutputConcept, VariationAspect } from "../../types/draft";
import { StepFooter } from "../ui/chrome";
import { ChoiceCard, TextField } from "../ui/controls";

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

const variationAspectOptions: { value: VariationAspect; label: string }[] = [
  { value: "lighting", label: "Lighting" },
  { value: "styling", label: "Styling" },
  { value: "camera_view", label: "Camera view" },
];

export function ProjectScopeSection({
  outputs,
  onOutputs,
  onBack,
  onContinue,
}: {
  outputs: ProjectScopeOutput[];
  onOutputs: (update: (current: ProjectScopeOutput[]) => ProjectScopeOutput[]) => void;
  onBack: () => void;
  onContinue: () => void;
}) {
  const variations = outputs.find((output) => output.concept === "variations") ?? null;
  const others = outputs.find((output) => output.concept === "others") ?? null;
  const selectedAspects = variations?.variationAspects ?? [];

  function toggleConcept(concept: OutputConcept) {
    onOutputs((current) => {
      const exists = current.some((output) => output.concept === concept);
      const next = exists
        ? current.filter((output) => output.concept !== concept)
        : [...current, emptyOutput(concept)].sort(
            (a, b) => conceptOrder.indexOf(a.concept) - conceptOrder.indexOf(b.concept),
          );
      return next;
    });
  }

  function patchOutput(id: string, patch: Partial<ProjectScopeOutput>) {
    onOutputs((current) => current.map((output) => (output.id === id ? { ...output, ...patch } : output)));
  }

  function toggleAspect(aspect: VariationAspect) {
    if (!variations) return;
    const next = selectedAspects.includes(aspect)
      ? selectedAspects.filter((item) => item !== aspect)
      : [...selectedAspects, aspect];
    patchOutput(variations.id, { variationAspects: next });
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
            name="project-scope-output"
            value={option.value}
            label={option.label}
            description={conceptDescriptions[option.value]}
            checked={outputs.some((output) => output.concept === option.value)}
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
                name="project-variation-aspect"
                value={option.value}
                label={option.label}
                checked={selectedAspects.includes(option.value)}
                onChange={() => toggleAspect(option.value)}
              />
            ))}
          </div>
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

      <StepFooter
        onBack={onBack}
        onContinue={onContinue}
        continueLabel="Review choices"
        showMoreOptions={false}
      />
    </div>
  );
}

function emptyOutput(concept: OutputConcept): ProjectScopeOutput {
  return {
    id: createId(),
    concept,
    otherLabel: "",
    variationAspects: [],
  };
}
