import { itemDisplayName } from "../lib/itemLabel";
import { itemsForRequest } from "../lib/requestItems";
import type {
  AdvancedDraft,
  BriefItem,
  ClientJobDraft,
  ClientReference,
  ItemDraft,
  ItemMetadata,
  JobDraft,
  PreferencesDraft,
  ScopeDraft,
  ScopeOutput,
  SectionId,
  SuggestionsDraft,
} from "../types/draft";

export interface ValidationIssue {
  severity: "error" | "warning";
  section: SectionId;
  path: string;
  message: string;
}

export interface ValidationResult {
  valid: boolean;
  issues: ValidationIssue[];
}

export interface SectionCompletion {
  job: boolean;
  item: boolean;
  references: boolean;
  scope: boolean;
  preferences: boolean;
  suggestions: boolean;
  advanced: boolean;
}

const sectionOrder: SectionId[] = [
  "job",
  "item",
  "references",
  "scope",
  "preferences",
  "suggestions",
  "advanced",
  "review",
];

function issue(
  severity: ValidationIssue["severity"],
  section: SectionId,
  path: string,
  message: string,
): ValidationIssue {
  return { severity, section, path, message };
}

export function isJobReady(job: JobDraft): boolean {
  if (job.kind === "new_project") return job.newProjectMode !== null;
  if (job.kind === "edit" && job.editMode === "new_item") return true;
  if (job.kind === "edit" && job.editMode === "choose_from_saving") return job.savedItemId !== null;
  if (job.kind === "single_item") return job.singleItemRole !== null;
  return false;
}

function jobIssues(job: JobDraft): ValidationIssue[] {
  if (!job.kind) return [issue("error", "job", "job.kind", "Choose a job type.")];
  if (job.kind === "new_project" && !job.newProjectMode) {
    return [issue("error", "job", "job.newProjectMode", "Choose batch or one by one.")];
  }
  if (job.kind === "edit" && !job.editMode) {
    return [issue("error", "job", "job.editMode", "Choose from saving, or choose a new item.")];
  }
  if (job.kind === "edit" && job.editMode === "choose_from_saving" && !job.savedItemId) {
    return [issue("error", "job", "job.savedItemId", "Choose a saved brief.")];
  }
  if (job.kind === "single_item" && !job.singleItemRole) {
    return [issue("error", "job", "job.singleItemRole", "Choose hero or secondary.")];
  }
  return [];
}

export function isItemReady(item: ItemDraft): boolean {
  if (item.categoryState === "automatic_unknown") return true;
  return item.department !== null && item.category !== null;
}

function itemIssues(briefItem: BriefItem, label: string | null): ValidationIssue[] {
  const item = briefItem.item;
  const prefix = label ? `${label}: ` : "";
  if (item.categoryState === "automatic_unknown") return [];
  if (!item.department) {
    return [issue("error", "item", `items.${briefItem.id}.item.department`, `${prefix}Choose a department, or mark the category as unknown.`)];
  }
  if (!item.category) {
    return [issue("error", "item", `items.${briefItem.id}.item.category`, `${prefix}Choose a category, or mark the category as unknown.`)];
  }
  return [];
}

function outputIssues(briefItem: BriefItem, output: ScopeOutput, label: string | null): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const prefix = label ? `${label}: ` : "";
  if (output.concept === "others" && output.otherLabel.trim() === "") {
    issues.push(issue("error", "scope", `items.${briefItem.id}.scope.outputs.${output.id}.otherLabel`, `${prefix}Name the other output.`));
  }
  if (output.variationCount !== null && (!Number.isInteger(output.variationCount) || output.variationCount < 1)) {
    issues.push(
      issue(
        "error",
        "scope",
        `items.${briefItem.id}.scope.outputs.${output.id}.variationCount`,
        `${prefix}Variation count needs to be a whole number of at least 1.`,
      ),
    );
  } else if (output.concept === "variations" && output.variationCount === null) {
    issues.push(
      issue(
        "error",
        "scope",
        `items.${briefItem.id}.scope.outputs.${output.id}.variationCount`,
        `${prefix}Set how many variations.`,
      ),
    );
  }
  return issues;
}

export function isScopeReady(scope: ScopeDraft): boolean {
  return scope.outputs.length > 0 && scope.outputs.every((output) => outputReady(output));
}

function outputReady(output: ScopeOutput): boolean {
  if (output.concept === "others" && output.otherLabel.trim() === "") return false;
  if (output.variationCount !== null && (!Number.isInteger(output.variationCount) || output.variationCount < 1)) return false;
  if (output.concept === "variations" && output.variationCount === null) return false;
  return true;
}

function scopeIssues(briefItem: BriefItem, label: string | null): ValidationIssue[] {
  const prefix = label ? `${label}: ` : "";
  if (briefItem.scope.outputs.length === 0) {
    return [issue("error", "scope", `items.${briefItem.id}.scope.outputs`, `${prefix}Choose at least one output.`)];
  }
  return briefItem.scope.outputs.flatMap((output) => outputIssues(briefItem, output, label));
}

function referenceIssues(briefItem: BriefItem, label: string | null): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const groupId = briefItem.references.primaryProductGroupId;
  const prefix = label ? `${label}: ` : "";

  for (const reference of briefItem.references.items) {
    issues.push(...integrityIssues(briefItem.id, reference, groupId));
  }

  const describesProduct = briefItem.references.items.some(
    (reference) =>
      reference.localStatus !== "error" &&
      reference.localStatus !== "uploading" &&
      reference.relationship === "same_product" &&
      reference.productGroupId === groupId,
  );
  if (!describesProduct) {
    issues.push(
      issue(
        "warning",
        "references",
        `items.${briefItem.id}.references.items`,
        `${prefix}No images of this product yet. You can still prepare the brief.`,
      ),
    );
  }

  return issues;
}

function integrityIssues(itemId: string, reference: ClientReference, primaryProductGroupId: string): ValidationIssue[] {
  const path = `items.${itemId}.references.items.${reference.id}`;
  const issues: ValidationIssue[] = [];

  if (reference.localStatus === "uploading") {
    issues.push(issue("error", "references", path, "A file is still being added."));
  }

  if (reference.localStatus === "error") {
    const name = reference.asset?.fileName;
    const detail = reference.localStatusMessage?.trim();
    issues.push(
      issue(
        "error",
        "references",
        path,
        detail || (name ? `Remove ${name}. It could not be added.` : "Remove the file that could not be added."),
      ),
    );
  }

  if (
    (reference.type === "product_image" || reference.type === "other_view" || reference.type === "detail") &&
    reference.relationship !== "same_product" &&
    reference.localStatus !== "error"
  ) {
    issues.push(issue("error", "references", path, "A product image, other view, or detail must stay with this product."));
  }

  if (reference.relationship === "same_product" && reference.productGroupId !== primaryProductGroupId) {
    issues.push(issue("error", "references", `${path}.productGroupId`, "References of this product must share one product group."));
  }

  if (reference.relationship === "supporting_context" && reference.productGroupId !== null) {
    issues.push(issue("error", "references", `${path}.productGroupId`, "A supporting reference was grouped as its own product."));
  }

  if (reference.source === "local_file" && !reference.asset) {
    issues.push(issue("error", "references", `${path}.asset`, "A local reference is missing its file."));
  }

  if (reference.source === "midas_library" && !reference.asset?.libraryKey) {
    issues.push(issue("error", "references", `${path}.asset.libraryKey`, "A Midas reference is missing its library entry."));
  }

  return issues;
}

function metadataIssues(briefItem: BriefItem, label: string | null): ValidationIssue[] {
  const count = briefItem.metadata.itemCount;
  if (count !== null && (!Number.isInteger(count) || count < 1)) {
    const prefix = label ? `${label}: ` : "";
    return [
      issue(
        "error",
        "advanced",
        `items.${briefItem.id}.metadata.itemCount`,
        `${prefix}Item count should be at least 1, or left blank.`,
      ),
    ];
  }
  return [];
}

export function isMetadataFilled(metadata: ItemMetadata): boolean {
  if (metadata.itemCount !== null) return true;
  return Object.entries(metadata).some(([, value]) => typeof value === "string" && value.trim() !== "");
}

export function isAdvancedFilled(advanced: AdvancedDraft): boolean {
  return Object.values(advanced).some((value) => value.trim() !== "");
}

export function isPreferencesEngaged(preferences: PreferencesDraft): boolean {
  return preferences.useWorkflowDefaults || preferences.lighting !== null || preferences.wall !== null || preferences.floor !== null;
}

export function isSuggestionsEngaged(suggestions: SuggestionsDraft): boolean {
  return suggestions.plants !== "unspecified" || suggestions.human !== "unspecified" || suggestions.mood !== null;
}

export function sectionCompletion(draft: ClientJobDraft, activeItemId?: string): SectionCompletion {
  const items = itemsForRequest(draft, activeItemId);
  return {
    job: isJobReady(draft.job),
    item: items.length > 0 && items.every((entry) => isItemReady(entry.item)),
    references: items.some((entry) => entry.references.items.length > 0),
    scope: items.length > 0 && items.every((entry) => isScopeReady(entry.scope)),
    preferences: isPreferencesEngaged(draft.preferences),
    suggestions: isSuggestionsEngaged(draft.suggestions),
    advanced: isAdvancedFilled(draft.advanced) || items.some((entry) => isMetadataFilled(entry.metadata)),
  };
}

export function validateDraft(draft: ClientJobDraft, activeItemId?: string): ValidationResult {
  const requested = itemsForRequest(draft, activeItemId);
  const labelFor = requested.length > 1 ? (entry: BriefItem) => itemDisplayName(entry, draft.items.findIndex((item) => item.id === entry.id)) : () => null;

  const issues = [
    ...jobIssues(draft.job),
    ...requested.flatMap((entry) => itemIssues(entry, labelFor(entry))),
    ...requested.flatMap((entry) => referenceIssues(entry, labelFor(entry))),
    ...requested.flatMap((entry) => scopeIssues(entry, labelFor(entry))),
    ...requested.flatMap((entry) => metadataIssues(entry, labelFor(entry))),
  ].sort((a, b) => {
    if (a.severity !== b.severity) return a.severity === "error" ? -1 : 1;
    return sectionOrder.indexOf(a.section) - sectionOrder.indexOf(b.section);
  });

  return {
    valid: issues.every((entry) => entry.severity !== "error"),
    issues,
  };
}
