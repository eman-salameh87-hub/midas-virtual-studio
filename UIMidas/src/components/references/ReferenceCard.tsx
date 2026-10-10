import { useState } from "react";
import { referenceTypeOptions } from "../../config/options";
import { fileTypeLabel, formatBytes } from "../../lib/references";
import type { ClientReference, ReferenceType } from "../../types/draft";

const imageAccept = "image/*";
const specAccept = "image/*,.pdf,.txt,application/pdf,text/plain";

export function ReferenceCard({
  reference,
  onRemove,
  onReplace,
  onType,
  onTreatAsProduct,
  onRemoveFromProduct,
}: {
  reference: ClientReference;
  onRemove: () => void;
  onReplace?: (file: File) => void;
  onType?: (type: ReferenceType) => void;
  onTreatAsProduct?: () => void;
  onRemoveFromProduct?: () => void;
}) {
  const [previewFailed, setPreviewFailed] = useState(false);
  const typeLabel = referenceTypeOptions.find((option) => option.value === reference.type)?.label ?? reference.type;
  const fileName = reference.asset?.fileName ?? "Untitled";
  const preview = reference.asset?.localPreviewUrl;
  const size = formatBytes(reference.asset?.sizeBytes ?? null);
  const kind = reference.asset ? fileTypeLabel(reference.asset.fileName, reference.asset.mediaKind) : "";
  const previewMissing =
    previewFailed ||
    (reference.source === "local_file" &&
      reference.asset?.mediaKind === "image" &&
      !preview &&
      reference.localStatus === "ready");
  const status = statusLabel(reference, previewMissing);
  const typeChoices = typeChoicesFor(reference);
  const showPreview = Boolean(preview) && !previewFailed && reference.localStatus !== "error";

  return (
    <article className="ref-card" data-status={reference.localStatus ?? "ready"}>
      {showPreview ? (
        <img src={preview ?? undefined} alt="" onError={() => setPreviewFailed(true)} />
      ) : (
        <span className="file-tile" aria-hidden="true">
          {reference.type === "midas" ? "Midas" : kind || "File"}
        </span>
      )}
      <div className="ref-card__body">
        <p className="ref-card__type">{typeLabel}</p>
        <h3>{fileName}</h3>
        <p className="ref-card__file">
          {[kind, size].filter(Boolean).join(" · ")}
          {reference.source === "midas_library" ? `${kind || size ? " · " : ""}Midas` : ""}
        </p>
        {reference.relationship === "same_product" && reference.localStatus !== "error" ? (
          <p className="ref-card__meta">With this product</p>
        ) : null}
        <p className={reference.localStatus === "error" ? "ref-card__status ref-card__status--error" : "ref-card__status"} role={reference.localStatus === "error" ? "alert" : undefined}>
          {status}
        </p>
        <div className="ref-card__actions">
          {onTreatAsProduct ? (
            <button type="button" className="btn btn--secondary" onClick={onTreatAsProduct}>
              Treat as this product
            </button>
          ) : null}
          {onRemoveFromProduct ? (
            <button type="button" className="btn btn--ghost" onClick={onRemoveFromProduct}>
              Remove from product
            </button>
          ) : null}
          {onReplace ? <ReplaceControl fileName={fileName} accept={reference.type === "specification_file" ? specAccept : imageAccept} onReplace={onReplace} /> : null}
          <button type="button" className="btn btn--ghost" onClick={onRemove} aria-label={`Remove ${fileName}`}>
            Remove
          </button>
        </div>
        {onType && typeChoices.length > 1 ? (
          <details className="ref-more">
            <summary>Change type</summary>
            <div className="chip-row" role="group" aria-label={`Type for ${fileName}`}>
              {typeChoices.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className="chip"
                  aria-pressed={reference.type === option.value}
                  onClick={() => onType(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </details>
        ) : null}
      </div>
    </article>
  );
}

function ReplaceControl({
  fileName,
  accept,
  onReplace,
}: {
  fileName: string;
  accept: string;
  onReplace: (file: File) => void;
}) {
  return (
    <label className="btn btn--ghost replace-control">
      Replace
      <input
        type="file"
        accept={accept}
        aria-label={`Replace ${fileName}`}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onReplace(file);
          event.target.value = "";
        }}
      />
    </label>
  );
}

function statusLabel(reference: ClientReference, previewMissing: boolean): string {
  if (reference.localStatus === "uploading") return "Adding…";
  if (reference.localStatus === "error") return reference.localStatusMessage || "This file could not be added.";
  if (previewMissing) return reference.localStatusMessage || "Preview unavailable";
  return "Ready";
}

function typeChoicesFor(reference: ClientReference) {
  if (reference.type === "midas" || reference.source === "midas_library") return [];
  const fileOnly = reference.asset?.mediaKind === "file";
  return referenceTypeOptions.filter((option) => {
    if (option.value === "midas") return false;
    if (fileOnly) return option.value === "specification_file";
    return true;
  });
}
