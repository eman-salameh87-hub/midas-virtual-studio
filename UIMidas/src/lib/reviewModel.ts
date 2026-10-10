import {
  categoryById,
  departmentById,
  editModeOptions,
  floorOptions,
  jobKindOptions,
  lightingOptions,
  mockSavedBriefs,
  moodOptions,
  newProjectModeOptions,
  optionLabel,
  outputConceptOptions,
  outputViewOptions,
  resolutionOptions,
  singleItemRoleOptions,
  wallOptions,
} from "../config/options";
import { reviewReferenceBlocks } from "./referenceSummary";
import { itemDisplayName } from "./itemLabel";
import { itemsForRequest } from "./requestItems";
import type { BriefItem, ClientJobDraft, ScopeOutput, SectionId } from "../types/draft";

export const reviewActions = {
  submit: "Submit job",
  preparing: "Preparing job…",
  created: "Job created",
  unable: "Unable to submit job.",
  retry: "Retry",
  viewBrief: "View submitted brief",
  startAnother: "Start another job",
} as const;

export interface ReviewFact {
  label: string | null;
  text: string;
  tone?: "kicker";
}

export interface ReviewOutputView {
  name: string;
  details: ReviewFact[];
}

export interface ReviewGroup {
  title: string | null;
  itemId: string | null;
  facts: ReviewFact[];
  outputs: ReviewOutputView[];
}

export interface ReviewSectionView {
  id: SectionId;
  title: string;
  groups: ReviewGroup[];
}

export interface ClientReview {
  sections: ReviewSectionView[];
}

export function buildClientReview(draft: ClientJobDraft, activeItemId?: string): ClientReview {
  const items = itemsForRequest(draft, activeItemId);
  return {
    sections: [
      jobSection(draft),
      itemsSection(draft, items),
      referencesSection(draft, items),
      packageSection(draft, items),
      preferencesSection(draft),
      suggestionsSection(draft),
      advancedSection(draft),
    ],
  };
}

function jobSection(draft: ClientJobDraft): ReviewSectionView {
  const facts: ReviewFact[] = [];
  if (draft.job.kind === "new_project") {
    facts.push({ label: null, text: `${optionLabel(jobKindOptions, draft.job.kind)} · ${optionLabel(newProjectModeOptions, draft.job.newProjectMode)}` });
  } else if (draft.job.kind === "edit") {
    const mode = optionLabel(editModeOptions, draft.job.editMode);
    const kind = optionLabel(jobKindOptions, draft.job.kind);
    facts.push({ label: null, text: mode === "Not set" ? kind : `${kind} · ${mode}` });
    if (draft.job.editMode === "choose_from_saving") {
      const saved = mockSavedBriefs.find((item) => item.id === draft.job.savedItemId);
      facts.push({ label: "Saved brief", text: saved?.label ?? "Not chosen" });
    }
  } else if (draft.job.kind === "single_item") {
    facts.push({
      label: null,
      text: `${optionLabel(jobKindOptions, draft.job.kind)} · ${optionLabel(singleItemRoleOptions, draft.job.singleItemRole)}`,
    });
  } else {
    facts.push({ label: null, text: "Not set" });
  }
  return { id: "job", title: "Job", groups: [{ title: null, itemId: null, facts, outputs: [] }] };
}

function itemsSection(draft: ClientJobDraft, items: BriefItem[]): ReviewSectionView {
  return {
    id: "item",
    title: "Items",
    groups: items.map((item) => itemGroup(draft, item, items.length > 1)),
  };
}

function itemGroup(draft: ClientJobDraft, item: BriefItem, multiple: boolean): ReviewGroup {
  const index = draft.items.findIndex((entry) => entry.id === item.id);
  const fallback = `Item ${index + 1}`;
  const facts: ReviewFact[] = [];
  if (item.item.categoryState === "automatic_unknown") {
    facts.push({ label: null, text: "Automatic / unknown" });
  } else {
    const department = departmentById(item.item.department);
    const category = categoryById(item.item.department, item.item.category);
    const subcategory = category?.subcategories.find((entry) => entry.id === item.item.subcategory);
    if (department) facts.push({ label: "Department", text: department.label });
    if (category) facts.push({ label: "Category", text: category.label });
    if (subcategory) facts.push({ label: "Sub-category", text: subcategory.label });
    if (!department && !category && !subcategory) facts.push({ label: null, text: "Not described yet" });
  }
  return {
    title: multiple ? fallback : null,
    itemId: item.id,
    facts,
    outputs: [],
  };
}

function referencesSection(draft: ClientJobDraft, items: BriefItem[]): ReviewSectionView {
  const multiple = items.length > 1;
  const blocks = reviewReferenceBlocks(
    items.map((item) => {
      const index = draft.items.findIndex((entry) => entry.id === item.id);
      return { title: multiple ? itemHeading(item, index) : null, references: item.references.items };
    }),
  );
  return {
    id: "references",
    title: "References",
    groups: blocks.map((block, index) => ({
      title: block.title,
      itemId: items[index]?.id ?? null,
      facts: block.lines.map((line) => ({
        label: null,
        text: line,
        tone: line === "Product" || line === "Supporting context" ? ("kicker" as const) : undefined,
      })),
      outputs: [],
    })),
  };
}

function packageSection(draft: ClientJobDraft, items: BriefItem[]): ReviewSectionView {
  const multiple = items.length > 1;
  return {
    id: "scope",
    title: "Scope",
    groups: items.map((item) => {
      const index = draft.items.findIndex((entry) => entry.id === item.id);
      const outputs = item.scope.outputs.map(outputView);
      return {
        title: multiple ? itemHeading(item, index) : null,
        itemId: item.id,
        facts: outputs.length === 0 ? [{ label: null, text: "No outputs requested" }] : [],
        outputs,
      };
    }),
  };
}

function outputView(output: ScopeOutput): ReviewOutputView {
  const name = output.concept === "others" ? output.otherLabel.trim() || "Others" : optionLabel(outputConceptOptions, output.concept);
  const details: ReviewFact[] = [];
  if (output.views.length > 0) {
    details.push({ label: "Views", text: output.views.map((view) => optionLabel(outputViewOptions, view)).join(", ") });
  }
  if (output.proportion) details.push({ label: "Proportion", text: output.proportion });
  if (output.resolution) details.push({ label: "Resolution", text: optionLabel(resolutionOptions, output.resolution) });
  if (output.variationCount !== null) details.push({ label: "Count", text: String(output.variationCount) });
  return { name, details };
}

function preferencesSection(draft: ClientJobDraft): ReviewSectionView {
  const facts: ReviewFact[] = [];
  if (draft.preferences.useWorkflowDefaults) {
    facts.push({ label: null, text: "Using workflow defaults" });
  } else {
    if (draft.preferences.lighting) facts.push({ label: "Lighting", text: optionLabel(lightingOptions, draft.preferences.lighting) });
    if (draft.preferences.wall) facts.push({ label: "Wall", text: optionLabel(wallOptions, draft.preferences.wall) });
    if (draft.preferences.floor) facts.push({ label: "Floor", text: optionLabel(floorOptions, draft.preferences.floor) });
    if (facts.length === 0) facts.push({ label: null, text: "No preferences selected" });
  }
  return { id: "preferences", title: "Preferences", groups: [{ title: null, itemId: null, facts, outputs: [] }] };
}

function suggestionsSection(draft: ClientJobDraft): ReviewSectionView {
  const facts: ReviewFact[] = [];
  if (draft.suggestions.plants === "suggest") facts.push({ label: null, text: "Plants" });
  if (draft.suggestions.plants === "leave_out") facts.push({ label: null, text: "Plants left out" });
  if (draft.suggestions.human === "suggest") facts.push({ label: null, text: "Human" });
  if (draft.suggestions.human === "leave_out") facts.push({ label: null, text: "Human left out" });
  if (draft.suggestions.mood) facts.push({ label: null, text: optionLabel(moodOptions, draft.suggestions.mood) });
  if (facts.length === 0) facts.push({ label: null, text: "No additional styling suggestions" });
  return { id: "suggestions", title: "Suggestions", groups: [{ title: null, itemId: null, facts, outputs: [] }] };
}

function advancedSection(draft: ClientJobDraft): ReviewSectionView {
  const facts: ReviewFact[] = [];
  const notes: [string, string][] = [
    ["Description and metadata", draft.advanced.descriptionMetadataPreference],
    ["Previous generation", draft.advanced.previousGeneration],
    ["Custom prompt", draft.advanced.customPrompting],
    ["Fidelity", draft.advanced.fidelity],
    ["Styling", draft.advanced.styling],
    ["Cluttering", draft.advanced.cluttering],
    ["Description checkpoint", draft.advanced.descriptionCheckpoint],
    ["Semantic grounding", draft.advanced.semanticGrounding],
  ];
  for (const [label, value] of notes) {
    if (value.trim()) facts.push({ label, text: value.trim() });
  }
  if (facts.length === 0) facts.push({ label: null, text: "Nothing added." });
  return { id: "advanced", title: "Advanced", groups: [{ title: null, itemId: null, facts, outputs: [] }] };
}

function itemHeading(item: BriefItem, index: number): string {
  const fallback = `Item ${index + 1}`;
  const name = itemDisplayName(item, index);
  return name === fallback ? fallback : `${fallback} · ${name}`;
}
