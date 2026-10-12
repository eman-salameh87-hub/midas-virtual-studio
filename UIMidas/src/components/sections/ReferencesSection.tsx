import { useEffect, useRef, useState, type ReactNode } from "react";
import { analyzeReferenceIntake, type ReferenceIntakeResult } from "../../adapters/analyzeReferenceIntake";
import { loadMidasCatalogue } from "../../data/midasCatalogue";
import { isMidasReference } from "../../lib/midasSelection";
import {
  applyIntakeResult,
  applyTaxonomyFromIntake,
  invalidateAnalysis,
  nextAnalysisGeneration,
  referenceBlocksContinue,
  referenceIntakeMessage,
} from "../../lib/referenceAnalysis";
import {
  assignReferenceType,
  localFileFor,
  markReferenceReady,
  replaceLocalFile,
  revokePreview,
  stageLocalFiles,
  withoutReference,
  type LocalIntakeKind,
} from "../../lib/references";
import { useItemDraft, useReferencesDraft } from "../../state/DraftProvider";
import type { ClientReference, ItemDraft, ReferenceType, ReferencesDraft } from "../../types/draft";
import { MidasProductDialog, MidasSelectionList, useMidasCatalogue } from "../references/MidasProductPicker";
import { StudioSelect } from "../ui/StudioSelect";

export const intakeTypeOptions: { value: Exclude<LocalIntakeKind, never> | "other_view"; label: string }[] = [
  { value: "product", label: "Product / vendor reference" },
  { value: "room_image", label: "Room / target space" },
  { value: "inspiration", label: "Inspiration / look" },
  { value: "previous_result", label: "Previous result" },
  { value: "other_view", label: "Other views / pieces" },
  { value: "specification_file", label: "Specifications / Excel" },
];

const typeToPick: Record<string, (typeof intakeTypeOptions)[number]["value"]> = {
  product_image: "product",
  midas: "product",
  room_image: "room_image",
  inspiration: "inspiration",
  previous_result: "previous_result",
  other_view: "other_view",
  detail: "other_view",
  specification_file: "specification_file",
};

type UpdateReferences = (update: (current: ReferencesDraft) => ReferencesDraft) => void;
type UpdateItem = (update: (current: ItemDraft) => ItemDraft) => void;
type AnalyzeFn = typeof analyzeReferenceIntake;

export function ReferencesSection({ children }: { children?: ReactNode }) {
  const [, setItem] = useItemDraft();
  const [references, , itemId, updateItemReferences, settleUploads] = useReferencesDraft();
  return (
    <ReferencesIntake
      references={references}
      onReferences={(update) => updateItemReferences(itemId, update)}
      onItem={setItem}
      settleUploads={settleUploads}
    >
      {children}
    </ReferencesIntake>
  );
}

export function ReferencesIntake({
  references,
  onReferences,
  onItem,
  settleUploads,
  analyze = analyzeReferenceIntake,
  children,
}: {
  references: ReferencesDraft;
  onReferences: UpdateReferences;
  onItem?: UpdateItem;
  settleUploads?: () => void;
  analyze?: AnalyzeFn;
  children?: ReactNode;
}) {
  const [kind, setKind] = useState<(typeof intakeTypeOptions)[number]["value"]>("product");
  const [pickerOpen, setPickerOpen] = useState(false);
  const catalogue = useMidasCatalogue(loadMidasCatalogue);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    const pending = timers.current;
    return () => {
      for (const timer of pending) window.clearTimeout(timer);
      pending.length = 0;
      settleUploads?.();
    };
  }, [settleUploads]);

  function patchReference(id: string, update: (current: ClientReference) => ClientReference) {
    onReferences((current) => ({
      ...current,
      items: current.items.map((entry) => (entry.id === id ? update(entry) : entry)),
    }));
  }

  async function runAnalysis(reference: ClientReference, generation: number, file?: File | null) {
    if (reference.type === "specification_file" || reference.asset?.mediaKind === "file") {
      patchReference(reference.id, (current) => {
        if ((current.analysisGeneration ?? 0) !== generation) return current;
        return {
          ...current,
          analysisStatus: "skipped",
          analysisMessage: null,
          relevanceConfirmed: true,
        };
      });
      return;
    }
    try {
      const result = await analyze({
        libraryKey: reference.asset?.libraryKey,
        file: file ?? (reference.source === "local_file" ? localFileFor(reference.id) ?? null : null),
        intendedKind: null,
      });
      applyResult(reference.id, generation, result);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Image analysis failed. Retry or replace the image. It was not marked valid.";
      patchReference(reference.id, (current) => {
        if ((current.analysisGeneration ?? 0) !== generation) return current;
        return {
          ...current,
          analysisStatus: "failed",
          analysisMessage: message,
          relevanceConfirmed: false,
        };
      });
    }
  }

  function applyResult(id: string, generation: number, result: ReferenceIntakeResult) {
    onReferences((current) => {
      let applied = false;
      const items = current.items.map((entry) => {
        if (entry.id !== id) return entry;
        const next = applyIntakeResult(entry, generation, result, current.primaryProductGroupId);
        if (next) applied = true;
        return next ?? entry;
      });
      if (applied) {
        queueMicrotask(() => {
          onItem?.((item) => applyTaxonomyFromIntake(item, result));
        });
      }
      return { ...current, items };
    });
  }

  function addFiles(files: FileList) {
    const intake: LocalIntakeKind = kind === "other_view" ? "product" : kind;
    const created = stageLocalFiles(Array.from(files), intake, references.primaryProductGroupId, references.items).map(
      (reference) => {
        const typed =
          kind === "other_view"
            ? assignReferenceType(reference, "other_view", references.primaryProductGroupId)
            : reference;
        return kind === "product" ? typed : { ...typed, typeEditedByUser: true };
      },
    );
    const filesArray = Array.from(files);
    onReferences((current) => ({
      ...current,
      items: [...current.items, ...created.map((entry) => (entry.localStatus === "uploading" ? markReferenceReady(entry) : entry))],
    }));
    created.forEach((reference, index) => {
      if (reference.localStatus === "error") return;
      void runAnalysis(reference, reference.analysisGeneration ?? 1, filesArray[index]);
    });
  }

  function removeReference(id: string) {
    const existing = references.items.find((item) => item.id === id);
    if (existing) revokePreview(existing);
    onReferences((current) => ({ ...current, items: withoutReference(current.items, id) }));
  }

  function replaceReference(reference: ClientReference, file: File) {
    const next = invalidateAnalysis(
      replaceLocalFile(reference, file, references.primaryProductGroupId, references.items.filter((entry) => entry.id !== reference.id)),
    );
    onReferences((current) => ({
      ...current,
      items: current.items.map((entry) => (entry.id === reference.id ? next : entry)),
    }));
    void runAnalysis(next, next.analysisGeneration ?? 1, file);
  }

  function changeType(reference: ClientReference, pick: (typeof intakeTypeOptions)[number]["value"]) {
    if (reference.type === "midas") return;
    const type: ReferenceType = pick === "product" ? "product_image" : pick;
    patchReference(reference.id, (current) => ({
      ...assignReferenceType(current, type, references.primaryProductGroupId),
      typeEditedByUser: true,
    }));
  }

  const accept = kind === "specification_file" ? "image/*,.pdf,.txt,application/pdf,text/plain" : "image/*";
  const uploaded = references.items.filter((reference) => !isMidasReference(reference));
  const analyzing = references.items.some((reference) => reference.analysisStatus === "pending");

  return (
    <div className="item-board">
      <div className="item-board__setup">
        {children}
        <div className="item-board__rule" />
        <section className="references" aria-labelledby="references-title">
          <h3 id="references-title" className="references__title">
            Bring your references
          </h3>
          {analyzing ? (
            <p className="note" role="status">
              Analyzing image…
            </p>
          ) : null}

          {uploaded.length !== 1 ? (
            <label className="select-field select-field--type">
              <span>What are you adding?</span>
              <StudioSelect value={kind} options={intakeTypeOptions} onChange={(next) => setKind(next as (typeof intakeTypeOptions)[number]["value"])} />
            </label>
          ) : null}

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

          <button type="button" className="text-link" onClick={() => setPickerOpen(true)}>
            Choose from Midas
            <span aria-hidden="true"> ↗</span>
          </button>
        </section>
      </div>

      <aside className="item-gallery">
        {references.items.length === 0 ? (
          <p className="item-gallery__empty">No references selected yet. Upload a file or choose a product from Midas.</p>
        ) : (
          <div className="item-gallery__grid" data-count={selectionDensity(references.items.length)}>
            <MidasSelectionList
              references={references}
              products={catalogue.products}
              onReferences={(next) => onReferences(() => next)}
            />
            {uploaded.length > 0 ? (
              <ul className="file-list">
                {uploaded.map((reference) => (
                  <ReferencePreviewRow
                    key={reference.id}
                    reference={reference}
                    onRemove={() => removeReference(reference.id)}
                    onReplace={reference.source === "local_file" ? (file) => replaceReference(reference, file) : undefined}
                    onType={(pick) => changeType(reference, pick)}
                    onConfirm={() =>
                      patchReference(reference.id, (current) => ({
                        ...current,
                        analysisStatus: "accepted",
                        relevanceConfirmed: true,
                        analysisMessage: null,
                      }))
                    }
                    onRetry={() => {
                      const generation = nextAnalysisGeneration(reference);
                      patchReference(reference.id, (current) => ({
                        ...current,
                        analysisStatus: "pending",
                        analysisGeneration: generation,
                        relevanceConfirmed: false,
                      }));
                      void runAnalysis({ ...reference, analysisGeneration: generation }, generation);
                    }}
                  />
                ))}
              </ul>
            ) : null}
          </div>
        )}
      </aside>
      <MidasProductDialog
        open={pickerOpen}
        products={catalogue.products}
        status={catalogue.status}
        references={references}
        onClose={() => setPickerOpen(false)}
        onCommit={(next) => {
          const previous = new Set(references.items.map((entry) => entry.id));
          onReferences(() => next);
          for (const reference of next.items) {
            if (previous.has(reference.id) || !isMidasReference(reference)) continue;
            void runAnalysis(reference, reference.analysisGeneration ?? 1);
          }
        }}
      />
    </div>
  );
}

function ReferencePreviewRow({
  reference,
  onRemove,
  onReplace,
  onType,
  onConfirm,
  onRetry,
}: {
  reference: ClientReference;
  onRemove: () => void;
  onReplace?: (file: File) => void;
  onType: (pick: (typeof intakeTypeOptions)[number]["value"]) => void;
  onConfirm: () => void;
  onRetry: () => void;
}) {
  const fileName = reference.asset?.fileName ?? "Untitled";
  const preview = reference.asset?.localPreviewUrl;
  const message =
    reference.localStatus === "error"
      ? reference.localStatusMessage
      : referenceIntakeMessage(reference);
  const blocking = referenceBlocksContinue(reference);
  return (
    <li className="file-list__row pick-card" data-status={reference.analysisStatus ?? reference.localStatus}>
      <div className="pick-card__media file-preview">
        {preview && reference.asset?.mediaKind === "image" ? (
          <img src={preview} alt="" />
        ) : (
          <span className="file-tile">{reference.asset?.mediaKind === "file" ? "File" : "Image"}</span>
        )}
        <button type="button" className="pick-card__remove" onClick={onRemove} aria-label={`Remove ${fileName}`}>
          <span aria-hidden="true">×</span>
        </button>
      </div>
      <span className="file-list__meta pick-card__copy">
        <span className="pick-card__origin">Uploaded</span>
        <strong>{fileName}</strong>
        <label className="select-field select-field--type">
          <span>Reference type</span>
          <StudioSelect
            value={typeToPick[reference.type] ?? "product"}
            options={intakeTypeOptions}
            onChange={(next) => onType(next as (typeof intakeTypeOptions)[number]["value"])}
          />
        </label>
        {message ? (
          <span className={blocking ? "file-list__status file-list__status--error" : "file-list__status"} role={blocking ? "alert" : undefined}>
            {message}
          </span>
        ) : null}
      </span>
      <span className="file-list__actions">
        {reference.analysisStatus === "uncertain" && !reference.relevanceConfirmed ? (
          <button type="button" className="btn btn--secondary" onClick={onConfirm}>
            Confirm furniture reference
          </button>
        ) : null}
        {reference.analysisStatus === "failed" ? (
          <button type="button" className="btn btn--secondary" onClick={onRetry}>
            Retry analysis
          </button>
        ) : null}
        {onReplace ? (
          <label className="btn btn--ghost replace-control">
            Replace
            <input
              type="file"
              accept="image/*"
              aria-label={`Replace ${fileName}`}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) onReplace(file);
                event.target.value = "";
              }}
            />
          </label>
        ) : null}
      </span>
    </li>
  );
}

function selectionDensity(count: number): "1" | "2" | "few" | "many" {
  if (count <= 1) return "1";
  if (count === 2) return "2";
  if (count <= 4) return "few";
  return "many";
}

function UploadMark() {
  return (
    <svg className="upload__icon" viewBox="0 0 32 32" aria-hidden="true">
      <path d="M16 20V8M16 8l-4 4M16 8l4 4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M8 22v2h16v-2" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
