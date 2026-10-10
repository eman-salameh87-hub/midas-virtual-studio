import type { BriefItem, ClientJobDraft } from "../types/draft";

export function isBatchJob(draft: ClientJobDraft): boolean {
  return draft.job.kind === "new_project" && draft.job.newProjectMode === "batch";
}

/** Items that belong in validation, the brief, and the mock submit. */
export function itemsForRequest(draft: ClientJobDraft, activeItemId?: string): BriefItem[] {
  if (draft.items.length === 0) return [];
  if (isBatchJob(draft)) return draft.items;
  return [draft.items.find((item) => item.id === activeItemId) ?? draft.items[0]];
}
