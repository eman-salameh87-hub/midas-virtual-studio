import type { ClientReference, ReferenceType } from "../types/draft";

export const emptyProductCopy = "No product references yet.";
export const emptyProductHint = "Upload the product images or views that should define this item.";
export const emptyContextCopy = "No supporting context added.";

export interface ReferenceReviewBlock {
  title: string | null;
  lines: string[];
}

const supportingPhrases: Partial<Record<ReferenceType, [string, string]>> = {
  room_image: ["room", "rooms"],
  inspiration: ["inspiration", "inspirations"],
  previous_result: ["previous result", "previous results"],
  specification_file: ["specification", "specifications"],
  midas: ["Midas reference", "Midas references"],
};

function isCountable(reference: ClientReference): boolean {
  return reference.localStatus !== "error" && reference.localStatus !== "uploading";
}

function countLine(count: number, singular: string, plural: string): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

export function reviewReferenceBlocks(entries: { title: string | null; references: ClientReference[] }[]): ReferenceReviewBlock[] {
  return entries.map((entry) => ({
    title: entry.title,
    lines: fullLines(entry.references),
  }));
}

function fullLines(references: ClientReference[]): string[] {
  const { images, midas, supporting, pending, failed } = tally(references);
  const lines = ["Product"];
  if (images === 0 && midas === 0) lines.push(emptyProductCopy);
  if (images > 0) lines.push(countLine(images, "image", "images"));
  if (midas > 0) lines.push(countLine(midas, "Midas reference", "Midas references"));
  lines.push("Supporting context");
  if (supporting.length === 0) lines.push(emptyContextCopy);
  lines.push(...supporting);
  if (pending > 0) lines.push(countLine(pending, "file is still being added", "files are still being added"));
  if (failed > 0) lines.push(countLine(failed, "file could not be added", "files could not be added"));
  return lines;
}

function tally(references: ClientReference[]): {
  images: number;
  midas: number;
  supporting: string[];
  pending: number;
  failed: number;
} {
  const ready = references.filter(isCountable);
  const product = ready.filter((reference) => reference.relationship === "same_product");
  const context = ready.filter((reference) => reference.relationship === "supporting_context");
  const images = product.filter((reference) => reference.type === "product_image" || reference.type === "other_view" || reference.type === "detail").length;
  const midas = product.filter((reference) => reference.type === "midas").length;
  const supporting: string[] = [];
  for (const [type, phrases] of Object.entries(supportingPhrases) as [ReferenceType, [string, string]][]) {
    const count = context.filter((reference) => reference.type === type).length;
    if (count > 0) supporting.push(countLine(count, phrases[0], phrases[1]));
  }
  return {
    images,
    midas,
    supporting,
    pending: references.filter((reference) => reference.localStatus === "uploading").length,
    failed: references.filter((reference) => reference.localStatus === "error").length,
  };
}
