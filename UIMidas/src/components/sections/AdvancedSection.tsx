import { useAdvancedDraft, useItemMetadata } from "../../state/DraftProvider";
import type { AdvancedDraft, ItemMetadata } from "../../types/draft";
import { SectionIntro, StepFooter } from "../ui/chrome";
import { NumberField, TextField } from "../ui/controls";
import { BatchItemBar } from "./BatchItemBar";

type MetadataTextKey = {
  [K in keyof ItemMetadata]: ItemMetadata[K] extends string ? K : never;
}[keyof ItemMetadata];

type NoteKey = keyof AdvancedDraft;

const factFields: { key: MetadataTextKey; label: string; multiline?: boolean }[] = [
  { key: "specificItemsCombo", label: "Specific items / combo", multiline: true },
  { key: "additionalInputData", label: "Additional input data", multiline: true },
  { key: "sku", label: "SKU" },
  { key: "dimensions", label: "Dimensions" },
  { key: "colour", label: "Colour" },
  { key: "fabricMaterial", label: "Fabric / material" },
  { key: "itemRelationships", label: "Item relationships", multiline: true },
  { key: "otherPieces", label: "Other pieces", multiline: true },
];

const noteFields: { key: NoteKey; label: string; multiline?: boolean }[] = [
  { key: "descriptionMetadataPreference", label: "Description and metadata preference", multiline: true },
  { key: "previousGeneration", label: "Previous generation" },
  { key: "customPrompting", label: "Custom prompting", multiline: true },
  { key: "fidelity", label: "Fidelity" },
  { key: "styling", label: "Styling" },
  { key: "cluttering", label: "Cluttering" },
  { key: "descriptionCheckpoint", label: "Description checkpoint" },
  { key: "semanticGrounding", label: "Semantic grounding" },
];

export function AdvancedSection({ onBack }: { onBack: () => void }) {
  const [metadata, setMetadata] = useItemMetadata();
  const [advanced, setAdvanced] = useAdvancedDraft();

  function setFact(key: MetadataTextKey, value: string) {
    setMetadata((current) => ({ ...current, [key]: value }));
  }

  function setNote(key: NoteKey, value: string) {
    setAdvanced((current) => ({ ...current, [key]: value }));
  }

  return (
    <div className="stack">
      <SectionIntro
        eyebrow="Optional"
        title="Advanced"
        lede="Extra facts and notes. They stay with the brief and out of the main path. Steering is not part of this step — these values are only stored."
      />

      <section className="stack" aria-labelledby="advanced-facts">
        <h2 id="advanced-facts">Item facts</h2>
        <p className="note">Facts about this item. They are separate from picture preferences.</p>
        <BatchItemBar />
        <div className="form-grid">
          {factFields.map((field) => (
            <TextField
              key={field.key}
              id={`advanced-${field.key}`}
              label={field.label}
              value={metadata[field.key]}
              multiline={field.multiline}
              wide={field.multiline}
              onChange={(value) => setFact(field.key, value)}
            />
          ))}
          <NumberField
            id="advanced-item-count"
            label="Item count"
            value={metadata.itemCount}
            onChange={(itemCount) => setMetadata((current) => ({ ...current, itemCount }))}
          />
        </div>
      </section>

      <section className="stack" aria-labelledby="advanced-notes">
        <h2 id="advanced-notes">Notes kept with the brief</h2>
        <div className="form-grid">
          {noteFields.map((field) => (
            <TextField
              key={field.key}
              id={`advanced-${field.key}`}
              label={field.label}
              value={advanced[field.key]}
              multiline={field.multiline}
              wide={field.multiline}
              onChange={(value) => setNote(field.key, value)}
            />
          ))}
        </div>
      </section>

      <StepFooter onBack={onBack} />
    </div>
  );
}
