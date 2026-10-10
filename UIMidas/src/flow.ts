import type { SectionId } from "./types/draft";

export const projectFlow: { id: "project" | "item" | "scope"; index: string; label: string }[] = [
  { id: "project", index: "01", label: "Project" },
  { id: "item", index: "02", label: "The Item" },
  { id: "scope", index: "03", label: "Scope" },
];

export const primaryFlow: { id: SectionId; index: string; label: string }[] = [
  { id: "job", index: "01", label: "The Job" },
  { id: "item", index: "02", label: "The Item" },
  { id: "scope", index: "03", label: "Scope" },
  { id: "preferences", index: "04", label: "Preferences" },
  { id: "suggestions", index: "05", label: "Suggestions" },
];

export const sectionLabels: Record<SectionId, string> = {
  job: "The Job",
  item: "The Item",
  references: "References",
  scope: "Scope",
  preferences: "Preferences",
  suggestions: "Suggestions",
  advanced: "Advanced",
  review: "Review",
};
