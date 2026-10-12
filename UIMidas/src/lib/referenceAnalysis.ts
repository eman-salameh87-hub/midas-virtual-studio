import { resolveTaxonomy } from "./matchItemTaxonomy";
import { assignReferenceType } from "./references";
import type { ClientReference, ItemDraft, ReferenceType } from "../types/draft";
import type { ReferenceIntakeResult } from "../adapters/analyzeReferenceIntake";

const IMAGE_TYPES = new Set<ReferenceType>([
  "product_image",
  "other_view",
  "room_image",
  "inspiration",
  "previous_result",
]);

const TYPE_ALIASES: Record<string, ReferenceType> = {
  product_image: "product_image",
  "product / vendor reference": "product_image",
  "product image": "product_image",
  product: "product_image",
  room_image: "room_image",
  "room / target space": "room_image",
  "room image": "room_image",
  inspiration: "inspiration",
  "inspiration / look": "inspiration",
  previous_result: "previous_result",
  "previous result": "previous_result",
  other_view: "other_view",
  "other views / pieces": "other_view",
};

export function coerceReferenceType(value: string | null | undefined): ReferenceType | null {
  if (!value) return null;
  return TYPE_ALIASES[value.trim().toLowerCase()] ?? (IMAGE_TYPES.has(value as ReferenceType) ? (value as ReferenceType) : null);
}

export const NOT_FURNITURE_MESSAGE =
  "This image is not recognized as relevant furniture, product, or interior reference material. Replace it with a product, room, or interior photo, or choose a Midas catalogue item.";

export function nextAnalysisGeneration(reference: ClientReference): number {
  return (reference.analysisGeneration ?? 0) + 1;
}

export function invalidateAnalysis(reference: ClientReference): ClientReference {
  return {
    ...reference,
    analysisStatus: reference.asset?.mediaKind === "file" ? "skipped" : "pending",
    analysisMessage: null,
    analysisGeneration: nextAnalysisGeneration(reference),
    relevanceConfirmed: false,
  };
}

export function applyIntakeResult(
  reference: ClientReference,
  generation: number,
  result: ReferenceIntakeResult,
  primaryProductGroupId: string,
): ClientReference | null {
  if ((reference.analysisGeneration ?? 0) !== generation) return null;
  const status = result.status === "skipped" ? "skipped" : result.status;
  if (status === "accepted" && !result.relevant) {
    return {
      ...reference,
      analysisStatus: "rejected",
      analysisMessage: NOT_FURNITURE_MESSAGE,
      relevanceConfirmed: false,
    };
  }
  let next: ClientReference = {
    ...reference,
    analysisStatus: status === "accepted" || status === "skipped" ? "accepted" : status,
    analysisMessage: result.message,
    relevanceConfirmed: status === "accepted" || status === "skipped",
  };
  if (
    !reference.typeEditedByUser &&
    coerceReferenceType(result.suggested_reference_type) &&
    reference.type !== "midas"
  ) {
    next = assignReferenceType(next, coerceReferenceType(result.suggested_reference_type)!, primaryProductGroupId);
  }
  return next;
}

export function applyTaxonomyFromIntake(item: ItemDraft, result: ReferenceIntakeResult): ItemDraft {
  if (item.taxonomyEditedByUser) return item;
  if (result.status !== "accepted" || !result.relevant) return item;
  const match = resolveTaxonomy({
    department: result.department,
    category: result.category,
    subcategory: result.subcategory,
  });
  if (!match.department) return item;
  return {
    ...item,
    categoryState: "specified",
    department: match.department,
    category: match.category,
    subcategory: match.subcategory,
    taxonomyEditedByUser: false,
  };
}

export function markTaxonomyManual(next: ItemDraft): ItemDraft {
  return { ...next, taxonomyEditedByUser: true };
}

export function referenceBlocksContinue(reference: ClientReference): boolean {
  if (reference.localStatus === "uploading") return true;
  if (reference.localStatus === "error") return true;
  if (reference.asset?.mediaKind === "file" || reference.analysisStatus === "skipped") return false;
  if (reference.analysisStatus === "pending" || reference.analysisStatus === "failed") return true;
  if (reference.analysisStatus === "rejected") return true;
  if (reference.analysisStatus === "uncertain" && !reference.relevanceConfirmed) return true;
  return false;
}

export function referenceIntakeMessage(reference: ClientReference): string | null {
  if (reference.analysisStatus === "pending") return "Analyzing this image…";
  if (reference.analysisStatus === "rejected") return reference.analysisMessage || NOT_FURNITURE_MESSAGE;
  if (reference.analysisStatus === "failed") {
    return reference.analysisMessage || "Image analysis failed. Retry or replace the image. It was not marked valid.";
  }
  if (reference.analysisStatus === "uncertain" && !reference.relevanceConfirmed) {
    return reference.analysisMessage || "Confirm that this is furniture, product, or interior reference material.";
  }
  if (reference.analysisStatus === "accepted" || reference.analysisStatus === "skipped") {
    return reference.analysisMessage || "Classified using the existing catalogue options.";
  }
  return null;
}
