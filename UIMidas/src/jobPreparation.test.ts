import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { rememberLocalFile } from "./lib/references";
import { createEmptyBriefItem, createEmptyDraft } from "./state/emptyDraft";
import type { ClientJobDraft, ClientReference } from "./types/draft";
import { jobPreparationIssues } from "./validation/jobPreparation";

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

function reference(groupId: string): ClientReference {
  return {
    id: "prep-front",
    type: "product_image",
    source: "local_file",
    asset: {
      id: "front-asset",
      fileName: "front.png",
      mediaKind: "image",
      sizeBytes: PNG.length,
      localPreviewUrl: "blob:http://local/preview",
      libraryKey: null,
    },
    role: "product",
    relationship: "same_product",
    productGroupId: groupId,
    localStatus: "ready",
  };
}

function executableDraft(): ClientJobDraft {
  const draft = createEmptyDraft();
  draft.job = { kind: "new_project", newProjectMode: "one_by_one", editMode: null, savedItemId: null, singleItemRole: null };
  const item = draft.items[0] ?? createEmptyBriefItem();
  item.item = { categoryState: "specified", department: "home-furniture", category: "home-furniture/living-rooms", subcategory: null };
  item.references.items = [reference(item.references.primaryProductGroupId)];
  item.scope.outputs = [
    { id: "life", concept: "lifestyle", otherLabel: "", views: ["wide_view"], proportion: "1:1", resolution: "2k", variationCount: null },
  ];
  draft.items[0] = item;
  draft.preferences = { useWorkflowDefaults: false, lighting: "soft_daylight", wall: "ivory", floor: "light_oak" };
  draft.suggestions = { plants: "unspecified", human: "unspecified", mood: "automatic" };
  rememberLocalFile("prep-front", new File([PNG], "front.png", { type: "image/png" }));
  return draft;
}

describe("job preparation readiness", () => {
  it("blocks placeholders and missing files, not internal engine fields", () => {
    const draft = createEmptyDraft();
    draft.job = { kind: "new_project", newProjectMode: "one_by_one", editMode: null, savedItemId: null, singleItemRole: null };
    const item = draft.items[0];
    item.scope.outputs = [
      { id: "life", concept: "lifestyle", otherLabel: "", views: ["category_template"], proportion: "standard_for_category", resolution: "standard_for_category", variationCount: null },
    ];
    draft.preferences = { useWorkflowDefaults: true, lighting: null, wall: null, floor: null };
    const issues = jobPreparationIssues(draft, item.id);
    const messages = issues.map((issue) => issue.message).join(" ");
    assert.equal(messages.includes("input condition"), false);
    assert.equal(messages.includes("protected-identity"), false);
    assert.match(messages, /Workflow default/);
    assert.match(messages, /JPG, PNG, or WebP/);
    assert.match(messages, /Category template/);
  });

  it("is ready from a complete UIMidas brief without Phase-0 form fields", () => {
    const draft = executableDraft();
    assert.equal(jobPreparationIssues(draft, draft.items[0].id).length, 0);
  });
});
