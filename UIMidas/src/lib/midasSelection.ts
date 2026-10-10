import { safeMidasUrl, type MidasProduct } from "../data/midasCatalogue";
import type { ClientReference, ReferencesDraft, SingleItemRole } from "../types/draft";
import { createId } from "./ids";
import { setMidasProductMembership } from "./references";

export interface MidasSelection {
  id: string;
  name: string;
  imageUrl: string | null;
  role: SingleItemRole;
}

export function midasRole(reference: ClientReference): SingleItemRole {
  return reference.relationship === "same_product" ? "hero" : "secondary";
}

export function isMidasReference(reference: ClientReference): boolean {
  return reference.type === "midas" && reference.source === "midas_library";
}

export function applyMidasSelection(references: ReferencesDraft, selected: readonly MidasSelection[]): ReferencesDraft {
  const choices = new Map<string, MidasSelection>();
  for (const choice of selected) {
    if (!choices.has(choice.id)) choices.set(choice.id, choice);
  }
  const kept: ClientReference[] = [];
  const seen = new Set<string>();
  for (const reference of references.items) {
    if (!isMidasReference(reference)) {
      kept.push(reference);
      continue;
    }
    const key = reference.asset?.libraryKey;
    const choice = key ? choices.get(key) : undefined;
    if (!key || !choice || seen.has(key)) continue;
    seen.add(key);
    kept.push(withMembership(reference, choice, references.primaryProductGroupId));
  }
  for (const choice of choices.values()) {
    if (seen.has(choice.id)) continue;
    kept.push(withMembership(referenceFromProduct(choice), choice, references.primaryProductGroupId));
  }
  return { ...references, items: kept };
}

function withMembership(reference: ClientReference, choice: MidasSelection, primaryProductGroupId: string): ClientReference {
  const imageUrl = safeMidasUrl(choice.imageUrl);
  const next = reference.asset
    ? {
        ...reference,
        asset: {
          ...reference.asset,
          fileName: choice.name,
          localPreviewUrl: imageUrl,
          libraryKey: choice.id,
        },
      }
    : reference;
  return setMidasProductMembership(next, choice.role === "hero", primaryProductGroupId);
}

function referenceFromProduct(choice: MidasSelection): ClientReference {
  return {
    id: createId(),
    type: "midas",
    source: "midas_library",
    asset: {
      id: createId(),
      fileName: choice.name,
      mediaKind: "image",
      sizeBytes: null,
      localPreviewUrl: safeMidasUrl(choice.imageUrl),
      libraryKey: choice.id,
    },
    role: "midas_reference",
    relationship: "supporting_context",
    productGroupId: null,
    localStatus: "ready",
    localStatusMessage: null,
  };
}

export function selectionFromProduct(product: MidasProduct, role: SingleItemRole): MidasSelection {
  return { id: product.id, name: product.name, imageUrl: product.imageUrl, role };
}
