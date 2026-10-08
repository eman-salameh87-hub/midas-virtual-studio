import { categoryById, departmentById, optionLabel, outputConceptOptions } from "../config/options";
import type { ClientReference, ItemDraft, OutputConcept, ReferencesDraft, VariationAspect } from "../types/draft";

export type ProjectStart = "product_or_collection" | "existing_room" | "new_styled_space" | "saved_project";

export const projectStartingPoints: { id: ProjectStart; title: string; description: string }[] = [
  { id: "product_or_collection", title: "Product or collection", description: "Images or catalogue products" },
  { id: "existing_room", title: "Existing room", description: "Furnish, replace or restyle" },
  { id: "new_styled_space", title: "New styled space", description: "Create a complete room" },
  { id: "saved_project", title: "Saved project", description: "Continue an existing direction" },
];

export interface ProjectScopeOutput {
  id: string;
  concept: OutputConcept;
  otherLabel: string;
  variationAspects: VariationAspect[];
}

export interface ProjectBrief {
  start: ProjectStart;
  existingRoom: string;
  newStyledSpace: string;
  item: ItemDraft;
  references: ReferencesDraft;
  outputs: ProjectScopeOutput[];
}

export type ProjectPlace = "project" | "item" | "scope";

export interface ProjectIssue {
  place: ProjectPlace;
  message: string;
}

const aspectLabels: Record<VariationAspect, string> = {
  lighting: "Lighting",
  styling: "Styling",
  camera_view: "Camera view",
};

const referenceLabels: Record<string, string> = {
  product_image: "Product / vendor reference",
  room_image: "Room / target space",
  inspiration: "Inspiration / look",
  previous_result: "Previous result",
  other_view: "Other views / pieces",
  detail: "Other views / pieces",
  specification_file: "Specifications / Excel",
  midas: "Midas reference",
};

export function referenceIssues(references: ReferencesDraft): ProjectIssue[] {
  const issues: ProjectIssue[] = [];
  for (const reference of references.items) {
    if (reference.localStatus === "uploading") {
      issues.push({ place: "item", message: "A file is still being added." });
    }
    if (reference.localStatus === "error") {
      const name = reference.asset?.fileName;
      const detail = reference.localStatusMessage?.trim();
      issues.push({
        place: "item",
        message: detail || (name ? `Remove ${name}. It could not be added.` : "Remove the file that could not be added."),
      });
    }
  }
  return issues;
}

export function isReadyProjectReference(reference: ClientReference): boolean {
  if (reference.localStatus === "uploading" || reference.localStatus === "error") return false;
  if (reference.source === "midas_library") return Boolean(reference.asset?.libraryKey);
  return Boolean(reference.asset);
}

export function projectIssues(brief: ProjectBrief): ProjectIssue[] {
  const issues: ProjectIssue[] = [];
  if (brief.start === "saved_project") {
    issues.push({ place: "project", message: "No saved projects yet. Choose a different starting point" });
  }
  if (brief.start === "existing_room" && brief.existingRoom.trim() === "") {
    issues.push({ place: "project", message: "What should stay or change?" });
  }
  if (brief.start === "new_styled_space" && brief.newStyledSpace.trim() === "") {
    issues.push({ place: "project", message: "Describe the space to create" });
  }
  if (brief.item.categoryState !== "automatic_unknown") {
    if (!brief.item.department) {
      issues.push({ place: "item", message: "Choose a department, or mark the category as unknown." });
    } else if (!brief.item.category) {
      issues.push({ place: "item", message: "Choose a category, or mark the category as unknown." });
    }
  }
  issues.push(...referenceIssues(brief.references));
  if (!brief.references.items.some(isReadyProjectReference)) {
    issues.push({ place: "item", message: "No product references yet." });
  }
  if (brief.outputs.length === 0) {
    issues.push({ place: "scope", message: "Choose at least one output." });
  }
  for (const output of brief.outputs) {
    if (output.concept === "others" && output.otherLabel.trim() === "") {
      issues.push({ place: "scope", message: "Name the other output." });
    }
  }
  return issues;
}

export function projectReviewFacts(brief: ProjectBrief): { place: ProjectPlace; title: string; lines: { label: string | null; text: string }[] }[] {
  const start = projectStartingPoints.find((option) => option.id === brief.start);
  const projectLines: { label: string | null; text: string }[] = [
    { label: null, text: start?.title ?? brief.start },
    { label: null, text: start?.description ?? "" },
  ];
  if (brief.start === "existing_room") {
    projectLines.push({ label: "What should stay or change?", text: brief.existingRoom.trim() || "Not set" });
  }
  if (brief.start === "new_styled_space") {
    projectLines.push({ label: "Describe the space to create", text: brief.newStyledSpace.trim() || "Not set" });
  }
  if (brief.start === "saved_project") {
    projectLines.push({ label: null, text: "No saved projects yet. Choose a different starting point" });
  }

  const automatic = brief.item.categoryState === "automatic_unknown";
  const department = departmentById(brief.item.department);
  const category = categoryById(brief.item.department, brief.item.category);
  const subcategory = category?.subcategories.find((entry) => entry.id === brief.item.subcategory) ?? null;
  const itemLines: { label: string | null; text: string }[] = [
    { label: "Department", text: automatic || !department ? "Automatic from references" : department.label },
    { label: "Category", text: automatic || !category ? "Automatic from references" : category.label },
    { label: "Sub-category", text: automatic || !subcategory ? "Automatic from references" : subcategory.label },
  ];
  if (brief.references.items.length === 0) {
    itemLines.push({ label: "References", text: "No product references yet." });
  } else {
    for (const reference of brief.references.items) {
      const name = reference.asset?.fileName ?? "Untitled";
      const kind = referenceLabels[reference.type] ?? "Reference";
      itemLines.push({ label: "References", text: `${name} · ${kind}` });
    }
  }

  const scopeLines: { label: string | null; text: string }[] = [];
  if (brief.outputs.length === 0) scopeLines.push({ label: null, text: "Choose at least one output." });
  for (const output of brief.outputs) {
    scopeLines.push({ label: null, text: optionLabel(outputConceptOptions, output.concept) });
    if (output.concept === "variations") {
      const aspects = output.variationAspects.map((aspect) => aspectLabels[aspect]);
      scopeLines.push({ label: "What should vary?", text: aspects.length > 0 ? aspects.join(", ") : "Not set" });
    }
    if (output.concept === "others") {
      scopeLines.push({ label: "Describe the other outcome", text: output.otherLabel.trim() || "Not set" });
    }
  }

  return [
    { place: "project", title: "Project", lines: projectLines },
    { place: "item", title: "The Item", lines: itemLines },
    { place: "scope", title: "Scope", lines: scopeLines },
  ];
}
