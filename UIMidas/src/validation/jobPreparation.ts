import { isPhase0ImageFile, localFileFor } from "../lib/references";
import { itemsForRequest } from "../lib/requestItems";
import type { ClientJobDraft, ScopeOutput } from "../types/draft";
import type { ValidationIssue } from "./validateDraft";

const PLACEHOLDER_VIEWS = new Set(["category_template"]);
const PLACEHOLDER_PROPORTIONS = new Set(["standard_for_category"]);
const UNSUPPORTED_RESOLUTIONS = new Set(["web", "standard", "high", "print"]);
const PHASE0_RESOLUTIONS = new Set(["2k", "4k"]);
const PHASE0_VIEWS = new Set([
  "wide_view",
  "close_up",
  "wide_view_close_up",
  "front",
  "three_quarter",
  "side",
  "back",
  "top",
  "detail",
  "in_situ",
]);
const PHASE0_PROPORTIONS = new Set(["1:1", "4:5", "16:9", "3:4", "4:3", "9:16", "2:3"]);
const STYLED_OUTCOMES = new Set(["lifestyle", "new_composition", "variations", "create_with_this_item", "others"]);

function issue(section: ValidationIssue["section"], path: string, message: string): ValidationIssue {
  return { severity: "error", section, path, message };
}

function needsStyledRoom(draft: ClientJobDraft, activeItemId?: string): boolean {
  return itemsForRequest(draft, activeItemId).some((item) =>
    item.scope.outputs.some((output) => STYLED_OUTCOMES.has(output.concept)),
  );
}

/** User-facing gaps that still block job creation. Internal engine fields are not listed. */
export function jobPreparationIssues(draft: ClientJobDraft, activeItemId?: string): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const items = itemsForRequest(draft, activeItemId);

  if (draft.preferences.useWorkflowDefaults) {
    issues.push(
      issue(
        "preferences",
        "brief.preferences.useWorkflowDefaults",
        "Workflow default is a placeholder. Choose lighting, wall, and floor, or leave them unset for white-background jobs.",
      ),
    );
  } else if (needsStyledRoom(draft, activeItemId) && (!draft.preferences.lighting || !draft.preferences.wall || !draft.preferences.floor)) {
    issues.push(
      issue(
        "preferences",
        "brief.preferences",
        "Lifestyle and other styled outcomes need lighting, wall, and floor.",
      ),
    );
  }

  for (const item of items) {
    for (const output of item.scope.outputs) {
      issues.push(...outputPreparationIssues(item.id, output));
    }
    issues.push(...referencePreparationIssues(item.id, item.references.items));
  }

  if (!items.some((item) => item.references.items.some((reference) => usableLocalImage(reference.id)))) {
    issues.push(
      issue(
        "references",
        "brief.items[0].references",
        "Upload at least one JPG, PNG, or WebP product image. The file must still be available in this session.",
      ),
    );
  }

  return issues;
}

function outputPreparationIssues(itemId: string, output: ScopeOutput): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const path = `items.${itemId}.scope.outputs.${output.id}`;
  const views = output.views ?? [];
  if (views.length === 0 || views.some((view) => PLACEHOLDER_VIEWS.has(view))) {
    issues.push(
      issue("scope", `${path}.views`, "Choose a camera view. Category template cannot create a job."),
    );
  } else if (views.some((view) => !PHASE0_VIEWS.has(view))) {
    issues.push(issue("scope", `${path}.views`, "That view is not an executable camera view."));
  }
  if (!output.proportion || PLACEHOLDER_PROPORTIONS.has(output.proportion)) {
    issues.push(
      issue("scope", `${path}.proportion`, "Choose image proportions. Standard for category cannot create a job."),
    );
  } else if (!PHASE0_PROPORTIONS.has(output.proportion)) {
    issues.push(issue("scope", `${path}.proportion`, "That proportion cannot be executed."));
  }
  if (!output.resolution || PLACEHOLDER_PROPORTIONS.has(output.resolution)) {
    issues.push(issue("scope", `${path}.resolution`, "Choose 2K or 4K. Standard for category cannot create a job."));
  } else if (UNSUPPORTED_RESOLUTIONS.has(output.resolution)) {
    issues.push(issue("scope", `${path}.resolution`, "Web, Standard, High, and Print cannot be executed. Choose 2K or 4K."));
  } else if (!PHASE0_RESOLUTIONS.has(output.resolution)) {
    issues.push(issue("scope", `${path}.resolution`, "Only 2K and 4K can be executed."));
  }
  if (output.variationCount !== null) {
    issues.push(
      issue(
        "scope",
        `${path}.variationCount`,
        "A variation count cannot be executed as extra jobs. Clear the count, or keep it as brief-only and do not create this job.",
      ),
    );
  }
  return issues;
}

function referencePreparationIssues(
  itemId: string,
  references: ClientJobDraft["items"][number]["references"]["items"],
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  for (const reference of references) {
    if (reference.source === "midas_library") {
      issues.push(
        issue(
          "references",
          `items.${itemId}.references.${reference.id}`,
          "Midas catalogue references are not executed in this job path. Use a local JPG, PNG, or WebP.",
        ),
      );
      continue;
    }
    if (reference.source !== "local_file" || reference.localStatus === "error") continue;
    const file = localFileFor(reference.id);
    if (!file) {
      issues.push(
        issue(
          "references",
          `items.${itemId}.references.${reference.id}`,
          "This image is listed but the file bytes are not in the session. Upload it again.",
        ),
      );
      continue;
    }
    if (reference.asset?.mediaKind === "image" && !isPhase0ImageFile(file)) {
      issues.push(
        issue(
          "references",
          `items.${itemId}.references.${reference.id}`,
          "Executable image intake accepts JPG, PNG, or WebP only.",
        ),
      );
    }
  }
  return issues;
}

function usableLocalImage(referenceId: string): boolean {
  const file = localFileFor(referenceId);
  return Boolean(file && isPhase0ImageFile(file));
}
