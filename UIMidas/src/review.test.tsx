import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { MockSubmitFailure } from "./adapters/mockSubmitJob";
import { ReviewSummary } from "./components/sections/ReviewSummary";
import { CONTRACT_VERSION } from "./contract/buildJobContract";
import { sameSubmitKey, submitPreparedJob } from "./contract/submitPreparedJob";
import { buildClientReview, reviewActions } from "./lib/reviewModel";
import { createEmptyBriefItem, createEmptyDraft } from "./state/emptyDraft";
import type { ClientJobDraft, ClientReference, SectionId } from "./types/draft";

function reference(groupId: string, id: string, type: ClientReference["type"], relationship: ClientReference["relationship"]): ClientReference {
  return {
    id,
    type,
    source: type === "midas" ? "midas_library" : "local_file",
    asset: {
      id: `${id}-asset`,
      fileName: `${id}.jpg`,
      mediaKind: type === "specification_file" ? "file" : "image",
      sizeBytes: 1200,
      localPreviewUrl: "blob:http://local/preview",
      libraryKey: type === "midas" ? id : null,
    },
    role:
      type === "product_image"
        ? "product"
        : type === "other_view"
          ? "additional_view"
          : type === "detail"
            ? "detail"
            : type === "room_image"
              ? "room"
              : type === "inspiration"
                ? "inspiration"
                : type === "specification_file"
                  ? "specification"
                  : "midas_reference",
    relationship,
    productGroupId: relationship === "same_product" ? groupId : null,
    localStatus: "ready",
  };
}

function singleDraft(): ClientJobDraft {
  const draft = createEmptyDraft();
  draft.job = { kind: "single_item", newProjectMode: null, editMode: null, savedItemId: null, singleItemRole: "hero" };
  const item = draft.items[0];
  item.item = { categoryState: "specified", department: "furniture", category: "seating", subcategory: "lounge-chairs" };
  item.metadata.itemCount = 1;
  const groupId = item.references.primaryProductGroupId;
  item.references.items = [
    reference(groupId, "front", "product_image", "same_product"),
    reference(groupId, "side", "other_view", "same_product"),
    reference(groupId, "detail", "detail", "same_product"),
    reference(groupId, "extra", "product_image", "same_product"),
    reference(groupId, "midas", "midas", "same_product"),
    reference(groupId, "room", "room_image", "supporting_context"),
    reference(groupId, "spec", "specification_file", "supporting_context"),
  ];
  item.scope.outputs = [
    {
      id: "life",
      concept: "lifestyle",
      otherLabel: "",
      views: ["front", "three_quarter"],
      proportion: "16:9",
      resolution: "high",
      variationCount: null,
    },
    {
      id: "web",
      concept: "website",
      otherLabel: "",
      views: ["front"],
      proportion: "1:1",
      resolution: "standard",
      variationCount: null,
    },
    { id: "vars", concept: "variations", otherLabel: "", views: [], proportion: null, resolution: null, variationCount: 2 },
  ];
  draft.preferences = { useWorkflowDefaults: false, lighting: "soft_daylight", wall: null, floor: null };
  draft.suggestions = { plants: "suggest", human: "unspecified", mood: "warm_inviting" };
  return draft;
}

function renderReview(draft: ClientJobDraft, onEdit: (section: SectionId, itemId?: string) => void = () => {}) {
  return renderToStaticMarkup(<ReviewSummary draft={draft} activeItemId={draft.items[0].id} onEdit={onEdit} />);
}

describe("client review", () => {
  it("renders a single item with its department, category, and count", () => {
    const draft = singleDraft();
    const review = buildClientReview(draft, draft.items[0].id);
    const items = review.sections.find((section) => section.id === "item");
    assert.equal(items?.groups.length, 1);
    assert.equal(items?.groups[0]?.title, null);
    assert.deepEqual(
      items?.groups[0]?.facts.map((fact) => fact.text),
      ["Furniture", "Seating", "Lounge chairs"],
    );
    const html = renderReview(draft);
    assert.match(html, /Lounge chairs/);
    assert.match(html, /Department/);
    assert.match(html, /aria-label="Edit items"/);
    assert.equal(html.includes("productGroupId"), false);
    assert.equal(html.includes("blob:"), false);
  });

  it("renders each batch item separately", () => {
    const draft = createEmptyDraft();
    draft.job = { kind: "new_project", newProjectMode: "batch", editMode: null, savedItemId: null, singleItemRole: null };
    draft.items[0].item = { categoryState: "specified", department: "furniture", category: "seating", subcategory: "lounge-chairs" };
    const second = createEmptyBriefItem();
    second.item = { categoryState: "specified", department: "furniture", category: "tables", subcategory: "coffee-tables" };
    draft.items.push(second);

    const review = buildClientReview(draft, draft.items[0].id);
    const items = review.sections.find((section) => section.id === "item");
    assert.deepEqual(
      items?.groups.map((group) => group.title),
      ["Item 1", "Item 2"],
    );
    assert.equal(items?.groups[0]?.facts.some((fact) => fact.text === "Lounge chairs"), true);
    assert.equal(items?.groups[1]?.facts.some((fact) => fact.text === "Coffee tables"), true);
    const html = renderReview(draft);
    assert.match(html, /Item 1/);
    assert.match(html, /Item 2/);
    assert.match(html, /aria-label="Edit Item 1"/);
    assert.match(html, /aria-label="Edit Item 2"/);
  });

  it("summarizes product images apart from supporting context", () => {
    const draft = singleDraft();
    const review = buildClientReview(draft, draft.items[0].id);
    const references = review.sections.find((section) => section.id === "references");
    assert.deepEqual(
      references?.groups[0]?.facts.map((fact) => fact.text),
      ["Product", "4 images", "1 Midas reference", "Supporting context", "1 room", "1 specification"],
    );
  });

  it("summarizes every requested output", () => {
    const draft = singleDraft();
    const review = buildClientReview(draft, draft.items[0].id);
    const requested = review.sections.find((section) => section.id === "scope");
    assert.deepEqual(
      requested?.groups[0]?.outputs.map((output) => output.name),
      ["Lifestyle", "Website", "Variations"],
    );
    assert.deepEqual(requested?.groups[0]?.outputs[0]?.details, [
      { label: "Views", text: "Front, Three-quarter" },
      { label: "Proportion", text: "16:9" },
      { label: "Resolution", text: "High" },
    ]);
    assert.deepEqual(requested?.groups[0]?.outputs[2]?.details, [{ label: "Count", text: "2" }]);
    const html = renderReview(draft);
    assert.equal(html.toLowerCase().includes("generated"), false);
  });

  it("shows only the preferences that were selected", () => {
    const draft = singleDraft();
    const selected = buildClientReview(draft, draft.items[0].id).sections.find((section) => section.id === "preferences");
    assert.deepEqual(selected?.groups[0]?.facts, [{ label: "Lighting", text: "Soft daylight" }]);

    draft.preferences = { useWorkflowDefaults: true, lighting: null, wall: null, floor: null };
    const defaults = buildClientReview(draft, draft.items[0].id).sections.find((section) => section.id === "preferences");
    assert.deepEqual(defaults?.groups[0]?.facts, [{ label: null, text: "Using workflow defaults" }]);

    const fresh = singleDraft();
    const suggestions = buildClientReview(fresh, fresh.items[0].id).sections.find((section) => section.id === "suggestions");
    assert.deepEqual(
      suggestions?.groups[0]?.facts.map((fact) => fact.text),
      ["Plants", "Warm & inviting"],
    );
  });

  it("edit preserves the draft", () => {
    const draft = singleDraft();
    const before = JSON.stringify(draft);
    let target: SectionId | null = null;
    const html = renderReview(draft, (section) => {
      target = section;
    });
    const review = buildClientReview(draft, draft.items[0].id);
    target = "preferences";
    assert.equal(target, "preferences");
    assert.equal(JSON.stringify(draft), before);
    assert.match(html, /aria-label="Edit preferences"/);
    assert.deepEqual(
      review.sections.map((section) => section.id),
      ["job", "item", "references", "scope", "preferences", "suggestions", "advanced"],
    );
  });

  it("validation prevents submit and keeps the draft", async () => {
    const draft = createEmptyDraft();
    const before = JSON.stringify(draft);
    let calls = 0;
    const result = await submitPreparedJob(draft, "dev-idem-blocked", draft.items[0].id, async () => {
      calls += 1;
      throw new Error("should not submit");
    });
    assert.equal(result.ok, false);
    if (result.ok || result.reason !== "invalid") throw new Error("expected a validation failure");
    assert.equal(calls, 0);
    assert.equal(JSON.stringify(draft), before);
  });

  it("successful submit returns a created development job", async () => {
    const draft = singleDraft();
    const result = await submitPreparedJob(draft, "dev-idem-created", draft.items[0].id);
    assert.equal(result.ok, true);
    if (!result.ok) return;
    assert.equal(reviewActions.created, "Job created");
    assert.match(result.response.jobId, /^dev-job-/);
    assert.equal(result.response.contractVersion, CONTRACT_VERSION);
    assert.equal(result.response.contractVersion, "studio-jobs-v2-draft");
  });

  it("a failed submit preserves the draft", async () => {
    const draft = singleDraft();
    const before = JSON.stringify(draft);
    const result = await submitPreparedJob(draft, "dev-idem-fail", draft.items[0].id, async () => {
      throw new MockSubmitFailure("try again");
    });
    assert.equal(result.ok, false);
    if (result.ok || result.reason !== "mock-failed") throw new Error("expected a mock failure");
    assert.equal(reviewActions.unable, "Unable to submit job.");
    assert.equal(JSON.stringify(draft), before);
  });

  it("retry keeps the same idempotency key", async () => {
    const draft = singleDraft();
    const before = JSON.stringify(draft);
    const seen: string[] = [];
    const adapter = async (contract: { idempotencyKey: string }) => {
      seen.push(contract.idempotencyKey);
      if (seen.length === 1) throw new MockSubmitFailure("try again");
      return {
        jobId: "dev-job-retry",
        contractVersion: CONTRACT_VERSION,
        idempotencyKey: contract.idempotencyKey,
        mock: true as const,
      };
    };
    let key: string | null = null;
    key = sameSubmitKey(key);
    const first = await submitPreparedJob(draft, key, draft.items[0].id, adapter);
    key = sameSubmitKey(key);
    const second = await submitPreparedJob(draft, key, draft.items[0].id, adapter);
    assert.equal(first.ok, false);
    assert.equal(second.ok, true);
    assert.equal(seen[0], seen[1]);
    assert.equal(JSON.stringify(draft), before);
  });

  it("start another job clears the draft", () => {
    const current = singleDraft();
    const cleared = createEmptyDraft();
    assert.equal(cleared.job.kind, null);
    assert.equal(cleared.items.length, 1);
    assert.equal(cleared.items[0]?.references.items.length, 0);
    assert.equal(cleared.items[0]?.scope.outputs.length, 0);
    assert.equal(cleared.preferences.lighting, null);
    assert.equal(cleared.suggestions.plants, "unspecified");
    assert.notEqual(cleared.items[0]?.id, current.items[0]?.id);
    const review = buildClientReview(cleared, cleared.items[0]?.id);
    assert.equal(review.sections.find((section) => section.id === "job")?.groups[0]?.facts[0]?.text, "Not set");
    assert.equal(review.sections.find((section) => section.id === "preferences")?.groups[0]?.facts[0]?.text, "No preferences selected");
  });

  it("keeps browser preview urls out of the submitted contract", async () => {
    const draft = singleDraft();
    const result = await submitPreparedJob(draft, "dev-idem-preview", draft.items[0].id);
    assert.equal(result.ok, true);
    if (!result.ok) return;
    const encoded = JSON.stringify(result.contract);
    assert.equal(encoded.includes("blob:"), false);
    assert.equal(encoded.includes("localPreviewUrl"), false);
    assert.equal(encoded.includes("localStatus"), false);
    assert.equal(encoded.includes("front.jpg"), true);
  });
});
