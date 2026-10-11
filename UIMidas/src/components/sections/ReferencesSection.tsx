import { useEffect, useRef, useState } from "react";
import { loadMidasCatalogue } from "../../data/midasCatalogue";
import { MidasProductDialog, MidasSelectionList, useMidasCatalogue } from "../references/MidasProductPicker";
import { StudioSelect } from "../ui/StudioSelect";
import { isMidasReference } from "../../lib/midasSelection";
import {
  assignReferenceType,
  markReferenceReady,
  revokePreview,
  stageLocalFiles,
  withoutReference,
  type LocalIntakeKind,
} from "../../lib/references";
import { useReferencesDraft } from "../../state/DraftProvider";

type ReferencePick = LocalIntakeKind | "detail" | "other_view" | "midas";

const fileTypes: { value: Exclude<ReferencePick, "detail" | "midas">; label: string }[] = [
  { value: "product", label: "Product / vendor reference" },
  { value: "room_image", label: "Room / target space" },
  { value: "inspiration", label: "Inspiration / look" },
  { value: "previous_result", label: "Previous result" },
  { value: "other_view", label: "Other views / pieces" },
  { value: "specification_file", label: "Specifications / Excel" },
];

const shownTypeLabels: Record<string, string> = {
  product_image: "Product / vendor reference",
  room_image: "Room / target space",
  inspiration: "Inspiration / look",
  previous_result: "Previous result",
  other_view: "Other views / pieces",
  detail: "Other views / pieces",
  specification_file: "Specifications / Excel",
  midas: "Midas reference",
};

export function ReferencesSection() {
  const [references, , itemId, updateItemReferences, settleUploads] = useReferencesDraft();
  const [kind, setKind] = useState<ReferencePick>("product");
  const [pickerOpen, setPickerOpen] = useState(false);
  const catalogue = useMidasCatalogue(loadMidasCatalogue);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    const pending = timers.current;
    return () => {
      for (const timer of pending) window.clearTimeout(timer);
      pending.length = 0;
      settleUploads();
    };
  }, [settleUploads]);

  function addFiles(files: FileList) {
    if (kind === "midas") return;
    const intake: LocalIntakeKind = kind === "detail" || kind === "other_view" ? "product" : kind;
    const created = stageLocalFiles(Array.from(files), intake, references.primaryProductGroupId, references.items).map((reference) =>
      kind === "detail" || kind === "other_view" ? assignReferenceType(reference, kind, references.primaryProductGroupId) : reference,
    );
    updateItemReferences(itemId, (current) => ({ ...current, items: [...current.items, ...created] }));
    for (const reference of created) {
      if (reference.localStatus !== "uploading") continue;
      const assetId = reference.asset?.id;
      const timer = window.setTimeout(() => {
        updateItemReferences(itemId, (current) => ({
          ...current,
          items: current.items.map((entry) =>
            entry.id === reference.id && entry.asset?.id === assetId ? markReferenceReady(entry) : entry,
          ),
        }));
      }, 280);
      timers.current.push(timer);
    }
  }

  function removeReference(id: string) {
    const existing = references.items.find((item) => item.id === id);
    if (existing) revokePreview(existing);
    updateItemReferences(itemId, (current) => ({ ...current, items: withoutReference(current.items, id) }));
  }

  const accept = kind === "specification_file" ? "image/*,.pdf,.txt,application/pdf,text/plain" : "image/*";
  const uploaded = references.items.filter((reference) => !isMidasReference(reference));

  return (
    <section className="references" aria-labelledby="references-title">
      <div className="references__head">
        <h3 id="references-title">Bring your references</h3>
        <button type="button" className="text-link" onClick={() => setPickerOpen(true)}>
          Choose from Midas
          <span aria-hidden="true"> ↗</span>
        </button>
      </div>

      <label className="select-field select-field--type">
        <span>Reference type</span>
        <StudioSelect
          value={kind}
          options={fileTypes}
          onChange={(next) => setKind(next as ReferencePick)}
        />
      </label>

      <label className="upload">
          <input
            type="file"
            accept={accept}
            multiple
            onChange={(event) => {
              if (event.target.files && event.target.files.length > 0) addFiles(event.target.files);
              event.target.value = "";
            }}
          />
          <UploadMark />
          <span className="upload__title">Add images or product files</span>
          <span className="upload__action">Choose files from your device</span>
        </label>

      {uploaded.length > 0 ? (
        <ul className="file-list">
          {uploaded.map((reference) => {
            const typeLabel = shownTypeLabels[reference.type] ?? "Reference";
            const problem = reference.localStatus === "error" ? reference.localStatusMessage : null;
            return (
              <li key={reference.id}>
                <span>
                  <strong>{reference.asset?.fileName ?? "Untitled"}</strong>
                  <span>{problem ?? typeLabel}</span>
                </span>
                <button type="button" className="btn btn--ghost" onClick={() => removeReference(reference.id)} aria-label={`Remove ${reference.asset?.fileName ?? "file"}`}>
                  Remove
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
      <MidasSelectionList
        references={references}
        products={catalogue.products}
        onReferences={(next) => updateItemReferences(itemId, () => next)}
      />
      <MidasProductDialog
        open={pickerOpen}
        products={catalogue.products}
        status={catalogue.status}
        references={references}
        onClose={() => setPickerOpen(false)}
        onCommit={(next) => updateItemReferences(itemId, () => next)}
      />
    </section>
  );
}

function UploadMark() {
  return (
    <svg className="upload__icon" viewBox="0 0 32 32" aria-hidden="true">
      <path d="M16 20V8M16 8l-4 4M16 8l4 4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M8 22v2h16v-2" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
