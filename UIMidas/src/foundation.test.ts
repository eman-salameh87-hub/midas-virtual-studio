import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { MockSubmitFailure } from "./adapters/mockSubmitJob";
import { CONTRACT_VERSION, PROPOSED_JOBS_ENDPOINT } from "./contract/buildJobContract";
import { sameSubmitKey, submitPreparedJob } from "./contract/submitPreparedJob";
import { normalizeDraft } from "./normalization/normalizeDraft";
import { createEmptyBriefItem, createEmptyDraft } from "./state/emptyDraft";
import type { BriefItem, ClientJobDraft, ClientReference } from "./types/draft";
import { validateDraft } from "./validation/validateDraft";

function reference(groupId: string, id: string, type: ClientReference["type"], relationship: ClientReference["relationship"]): ClientReference {
  return {
    id,
    type,
    source: type === "midas" ? "midas_library" : "local_file",
    asset: {
      id: `${id}-asset`,
      fileName: `${id}.jpg`,
      mediaKind: "image",
      sizeBytes: 1200,
      localPreviewUrl: "blob:http://local/preview",
      libraryKey: type === "midas" ? "midas-white-sweep" : null,
    },
    role: type === "product_image" ? "product" : type === "other_view" ? "additional_view" : type === "room_image" ? "room" : type === "specification_file" ? "specification" : "midas_reference",
    relationship,
    productGroupId: relationship === "same_product" ? groupId : null,
  };
}

function withItem(draft: ClientJobDraft, fill: (item: BriefItem) => void): BriefItem {
  const item = draft.items[0];
  fill(item);
  return item;
}

describe("normalized brief", () => {
  it("normalizes a single item without inventing empty choices", () => {
    const draft = createEmptyDraft();
    draft.job = { kind: "single_item", newProjectMode: null, editMode: null, savedItemId: null, singleItemRole: "hero" };
    withItem(draft, (item) => {
      item.item = { categoryState: "specified", department: "furniture", category: "seating", subcategory: "lounge-chairs" };
      item.scope.outputs = [
        { id: "life", concept: "lifestyle", otherLabel: "", views: ["front"], proportion: "4:5", resolution: null, variationCount: null },
      ];
    });

    const brief = normalizeDraft(draft, draft.items[0].id);
    assert.deepEqual(brief.job, { kind: "single_item", singleItemRole: "hero" });
    assert.equal(brief.items.length, 1);
    assert.equal(brief.items[0]?.department, "furniture");
    assert.equal(brief.items[0]?.category, "seating");
    assert.equal(brief.items[0]?.subcategory, "lounge-chairs");
    assert.equal(brief.preferences, undefined);
    assert.deepEqual(brief.suggestions, { mood: "automatic" });
    assert.equal(brief.notes, undefined);
  });

  it("keeps several images on one product group", () => {
    const draft = createEmptyDraft();
    draft.job.newProjectMode = "one_by_one";
    draft.job.kind = "new_project";
    const item = draft.items[0];
    const groupId = item.references.primaryProductGroupId;
    item.references.items = [
      reference(groupId, "front", "product_image", "same_product"),
      reference(groupId, "side", "other_view", "same_product"),
      reference(groupId, "detail", "other_view", "same_product"),
    ];

    const brief = normalizeDraft(draft, item.id);
    const groups = new Set(brief.items[0]?.references.map((entry) => entry.productGroupId));
    assert.equal(groups.size, 1);
    assert.equal(brief.items[0]?.references.length, 3);
    assert.equal([...groups][0], brief.items[0]?.productGroupId);
  });

  it("leaves supporting references outside the product group", () => {
    const draft = createEmptyDraft();
    const item = draft.items[0];
    const groupId = item.references.primaryProductGroupId;
    item.references.items = [
      reference(groupId, "front", "product_image", "same_product"),
      reference(groupId, "room", "room_image", "supporting_context"),
      reference(groupId, "spec", "specification_file", "supporting_context"),
    ];

    const brief = normalizeDraft(draft, item.id);
    const supporting = brief.items[0]?.references.filter((entry) => entry.relationship === "supporting_context") ?? [];
    assert.equal(supporting.length, 2);
    assert.ok(supporting.every((entry) => entry.productGroupId === null));
    assert.notEqual(supporting[0]?.productGroupId, brief.items[0]?.productGroupId);
  });

  it("keeps multiple requested outputs on the package", () => {
    const draft = createEmptyDraft();
    withItem(draft, (item) => {
      item.scope.outputs = [
        { id: "life", concept: "lifestyle", otherLabel: "", views: [], proportion: null, resolution: null, variationCount: null },
        { id: "web", concept: "website", otherLabel: "", views: [], proportion: null, resolution: null, variationCount: null },
        { id: "vars", concept: "variations", otherLabel: "", views: [], proportion: null, resolution: null, variationCount: 2 },
      ];
    });

    const outputs = normalizeDraft(draft).items[0]?.requestedPackage ?? [];
    assert.deepEqual(
      outputs.map((output) => output.concept),
      ["lifestyle", "website", "variations"],
    );
    assert.equal(outputs[2]?.variationCount, 2);
  });

  it("includes every item when the job is a batch", () => {
    const draft = createEmptyDraft();
    draft.job = { kind: "new_project", newProjectMode: "batch", editMode: null, savedItemId: null, singleItemRole: null };
    const second = createEmptyBriefItem();
    second.item = { categoryState: "specified", department: "lighting", category: "lamps", subcategory: null };
    draft.items.push(second);

    const brief = normalizeDraft(draft, draft.items[0].id);
    assert.equal(brief.items.length, 2);
    assert.equal(brief.items[1]?.department, "lighting");
    assert.equal(brief.preferences, undefined);
  });

  it("omits preview urls from the normalized payload", () => {
    const draft = createEmptyDraft();
    const item = draft.items[0];
    item.references.items = [reference(item.references.primaryProductGroupId, "front", "product_image", "same_product")];
    const serialized = JSON.stringify(normalizeDraft(draft, item.id));
    assert.equal(serialized.includes("blob:"), false);
    assert.equal(serialized.includes("localPreviewUrl"), false);
    assert.equal(serialized.includes("front.jpg"), true);
  });
});

describe("validation and mock submit", () => {
  it("reports a validation failure and does not submit", async () => {
    let calls = 0;
    const result = await submitPreparedJob(createEmptyDraft(), "dev-idem-test", undefined, async () => {
      calls += 1;
      throw new Error("should not submit");
    });
    assert.equal(result.ok, false);
    if (result.ok || result.reason !== "invalid") throw new Error("expected a validation failure");
    assert.equal(calls, 0);
    assert.ok(result.issues.some((issue) => issue.path === "job.kind"));
    assert.equal(validateDraft(createEmptyDraft()).valid, false);
  });

  it("returns a mock job id and contract version", async () => {
    const draft = readyDraft();
    let fetchCalled = false;
    const originalFetch = globalThis.fetch;
    globalThis.fetch = () => {
      fetchCalled = true;
      throw new Error("network");
    };
    try {
      const result = await submitPreparedJob(draft, "dev-idem-success", draft.items[0].id);
      assert.equal(result.ok, true);
      if (!result.ok) return;
      assert.equal(result.response.mock, true);
      if (!result.response.mock) return;
      assert.match(result.response.jobId, /^dev-job-/);
      assert.equal(result.response.contractVersion, CONTRACT_VERSION);
      assert.equal(result.contract.endpoint, PROPOSED_JOBS_ENDPOINT);
      assert.equal(result.contract.ownerIdentity.value, null);
      assert.equal(result.contract.fileIds.value, null);
      assert.equal(result.contract.limits.value, null);
      assert.equal(result.contract.package.length, 1);
      assert.equal(result.contract.package[0]?.outputs.length, 2);
      assert.equal(fetchCalled, false);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("reuses one idempotency key for the same submit", async () => {
    const draft = readyDraft();
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
    assert.match(seen[0] ?? "", /^dev-idem-/);
    assert.equal(sameSubmitKey(seen[0] ?? null), seen[0]);
  });
});

function readyDraft(): ClientJobDraft {
  const draft = createEmptyDraft();
  draft.job = { kind: "new_project", newProjectMode: "one_by_one", editMode: null, savedItemId: null, singleItemRole: null };
  withItem(draft, (item) => {
    item.item = { categoryState: "automatic_unknown", department: null, category: null, subcategory: null };
    item.references.items = [reference(item.references.primaryProductGroupId, "front", "product_image", "same_product")];
    item.scope.outputs = [
      { id: "life", concept: "lifestyle", otherLabel: "", views: [], proportion: null, resolution: null, variationCount: null },
      { id: "web", concept: "website", otherLabel: "", views: [], proportion: null, resolution: null, variationCount: null },
    ];
  });
  return draft;
}
