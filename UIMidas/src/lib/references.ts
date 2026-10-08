import type { ClientReference, ReferenceRole, ReferenceType } from "../types/draft";
import { createId } from "./ids";

const roleForType: Record<ReferenceType, ReferenceRole> = {
  product_image: "product",
  other_view: "additional_view",
  detail: "detail",
  room_image: "room",
  previous_result: "previous_result",
  inspiration: "inspiration",
  specification_file: "specification",
  midas: "midas_reference",
};

export const productReferenceTypes: readonly ReferenceType[] = ["product_image", "other_view", "detail"];

export const supportingReferenceTypes: readonly ReferenceType[] = [
  "room_image",
  "inspiration",
  "previous_result",
  "specification_file",
];

export type LocalIntakeKind = "product" | "room_image" | "inspiration" | "previous_result" | "specification_file";

export function roleForReferenceType(type: ReferenceType): ReferenceRole {
  return roleForType[type];
}

export function isProductReferenceType(type: ReferenceType): boolean {
  return type === "product_image" || type === "other_view" || type === "detail";
}

export function referenceFromFile(
  file: File,
  type: ReferenceType,
  primaryProductGroupId: string,
): ClientReference {
  const staged = stageLocalFiles([file], intakeKindFor(type), primaryProductGroupId, [])[0];
  if (!staged || staged.localStatus === "error" || !isProductReferenceType(type)) return staged;
  return { ...assignReferenceType(staged, type, primaryProductGroupId), localStatus: staged.localStatus };
}

function intakeKindFor(type: ReferenceType): LocalIntakeKind {
  if (type === "room_image" || type === "inspiration" || type === "previous_result" || type === "specification_file") return type;
  return "product";
}

export function referenceFromLibrary(entry: { id: string; name: string }): ClientReference {
  return {
    id: createId(),
    type: "midas",
    source: "midas_library",
    asset: {
      id: createId(),
      fileName: entry.name,
      mediaKind: "image",
      sizeBytes: null,
      localPreviewUrl: null,
      libraryKey: entry.id,
    },
    role: "midas_reference",
    relationship: "supporting_context",
    productGroupId: null,
    localStatus: "ready",
    localStatusMessage: null,
  };
}

export function setMidasProductMembership(
  reference: ClientReference,
  joinProduct: boolean,
  primaryProductGroupId: string,
): ClientReference {
  if (reference.type !== "midas") return reference;
  if (joinProduct) {
    return {
      ...reference,
      relationship: "same_product",
      productGroupId: primaryProductGroupId,
    };
  }
  return {
    ...reference,
    relationship: "supporting_context",
    productGroupId: null,
  };
}

export function assignReferenceType(
  reference: ClientReference,
  type: ReferenceType,
  primaryProductGroupId: string,
): ClientReference {
  if (type === "midas" || reference.type === "midas") return reference;
  if (reference.asset?.mediaKind === "file" && isProductReferenceType(type)) return reference;
  if (reference.asset?.mediaKind === "file" && type !== "specification_file") return reference;
  const product = isProductReferenceType(type);
  return {
    ...reference,
    type,
    role: roleForType[type],
    relationship: product ? "same_product" : "supporting_context",
    productGroupId: product ? primaryProductGroupId : null,
  };
}

export function stageLocalFiles(
  files: File[],
  kind: LocalIntakeKind,
  primaryProductGroupId: string,
  existing: ClientReference[],
): ClientReference[] {
  const staged: ClientReference[] = [];
  for (const file of files) {
    staged.push(stageLocalFile(file, kind, primaryProductGroupId, [...existing, ...staged]));
  }
  return staged;
}

export function replaceLocalFile(
  reference: ClientReference,
  file: File,
  primaryProductGroupId: string,
  siblings: ClientReference[],
): ClientReference {
  const kind = intakeKindFor(reference.type);
  const staged = stageLocalFile(file, kind, primaryProductGroupId, siblings);
  return {
    ...staged,
    id: reference.id,
    type: reference.localStatus === "error" ? staged.type : reference.type,
    role: reference.localStatus === "error" ? staged.role : reference.role,
    relationship: reference.localStatus === "error" ? staged.relationship : reference.relationship,
    productGroupId: reference.localStatus === "error" ? staged.productGroupId : reference.productGroupId,
  };
}

export function withoutReference(items: ClientReference[], id: string): ClientReference[] {
  return items.filter((item) => item.id !== id);
}

export function markReferenceReady(reference: ClientReference): ClientReference {
  if (reference.localStatus !== "uploading") return reference;
  const missingPreview = reference.asset?.mediaKind === "image" && !reference.asset.localPreviewUrl;
  return {
    ...reference,
    localStatus: "ready",
    localStatusMessage: missingPreview ? "Preview unavailable" : null,
  };
}

export function revokePreview(reference: ClientReference): void {
  const url = reference.asset?.localPreviewUrl;
  if (url?.startsWith("blob:") && typeof URL.revokeObjectURL === "function") URL.revokeObjectURL(url);
}

export function formatBytes(size: number | null): string {
  if (size === null) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function fileTypeLabel(fileName: string, mediaKind: "image" | "file"): string {
  const extension = fileName.split(".").pop()?.toLowerCase() ?? "";
  const labels: Record<string, string> = {
    jpg: "JPEG",
    jpeg: "JPEG",
    png: "PNG",
    gif: "GIF",
    webp: "WebP",
    avif: "AVIF",
    heic: "HEIC",
    tif: "TIFF",
    tiff: "TIFF",
    pdf: "PDF",
    txt: "Text",
  };
  if (extension && labels[extension]) return labels[extension];
  return mediaKind === "image" ? "Image" : "File";
}

function stageLocalFile(
  file: File,
  kind: LocalIntakeKind,
  primaryProductGroupId: string,
  existing: ClientReference[],
): ClientReference {
  const type = kind === "product" ? "product_image" : kind;
  const product = kind === "product";
  const problem = intakeProblem(file, kind, existing);
  const image = isImageFile(file);
  let previewUrl: string | null = null;
  let readFailed = false;
  if (!problem && image) {
    try {
      previewUrl = createPreviewUrl(file);
    } catch {
      readFailed = true;
    }
  }

  const failed = Boolean(problem) || readFailed;
  return {
    id: createId(),
    type,
    source: "local_file",
    asset: {
      id: createId(),
      fileName: file.name || "Untitled",
      mediaKind: image ? "image" : "file",
      sizeBytes: file.size,
      localPreviewUrl: failed ? null : previewUrl,
      libraryKey: null,
    },
    role: roleForType[type],
    relationship: product ? "same_product" : "supporting_context",
    productGroupId: product ? primaryProductGroupId : null,
    localStatus: failed ? "error" : "uploading",
    localStatusMessage: readFailed ? "This file could not be read." : problem,
  };
}

function intakeProblem(file: File, kind: LocalIntakeKind, existing: ClientReference[]): string | null {
  if (file.size === 0) return "This file is empty.";
  if (isDuplicate(file, existing)) return "This file is already here.";
  if (kind === "specification_file") {
    return isSpecificationFile(file) ? null : "Use an image, PDF, or text file.";
  }
  if (!isImageFile(file)) return kind === "product" ? "Use an image for this product." : "Use an image for this reference.";
  return null;
}

function isDuplicate(file: File, existing: ClientReference[]): boolean {
  return existing.some((reference) => {
    const asset = reference.asset;
    if (!asset) return false;
    return asset.fileName === file.name && asset.sizeBytes === file.size;
  });
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  if (dot <= 0) return "";
  return name.slice(dot + 1).toLowerCase();
}

function isImageFile(file: File): boolean {
  if (file.type.startsWith("image/")) return true;
  return ["jpg", "jpeg", "png", "gif", "webp", "avif", "heic", "tif", "tiff"].includes(extensionOf(file.name));
}

function isSpecificationFile(file: File): boolean {
  if (isImageFile(file)) return true;
  if (file.type === "application/pdf" || file.type === "text/plain") return true;
  return extensionOf(file.name) === "pdf" || extensionOf(file.name) === "txt";
}

function createPreviewUrl(file: File): string | null {
  if (typeof URL.createObjectURL !== "function") return null;
  const url = URL.createObjectURL(file);
  return url || null;
}
