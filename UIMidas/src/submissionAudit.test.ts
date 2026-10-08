import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { submitPreparedJob } from "./contract/submitPreparedJob";
import type { ProposedJobContract } from "./contract/buildJobContract";
import { normalizeDraft } from "./normalization/normalizeDraft";
import { createEmptyBriefItem, createEmptyDraft } from "./state/emptyDraft";
import type { ClientJobDraft, OutputConcept, ScopeOutput } from "./types/draft";

const concepts: OutputConcept[] = [
  "white_bk",
  "lifestyle",
  "website",
  "new_composition",
  "variations",
  "create_with_this_item",
  "others",
];

function output(concept: OutputConcept, scope = createEmptyBriefItem().scope): ScopeOutput {
  return {
    id: concept,
    concept,
    otherLabel: concept === "others" ? "A styled corner" : "",
    views: scope.deliveryView ? [scope.deliveryView] : [],
    proportion: scope.deliveryProportion ?? null,
    resolution: scope.deliveryResolution ?? null,
    variationCount: concept === "variations" ? 3 : null,
    variationAspects: concept === "variations" ? ["lighting", "styling", "camera_view"] : undefined,
  };
}

function readyDraft(): ClientJobDraft {
  const draft = createEmptyDraft();
  draft.job = { kind: "new_project", newProjectMode: "one_by_one", editMode: null, savedItemId: null, singleItemRole: null };
  const item = draft.items[0];
  item.item = {
    categoryState: "specified",
    department: "home-furniture",
    category: "home-furniture/living-rooms",
    subcategory: "home-furniture/living-rooms/sofa",
  };
  const groupId = item.references.primaryProductGroupId;
  item.references.items = [
    {
      id: "ref-product",
      type: "product_image",
      source: "local_file",
      role: "product",
      relationship: "same_product",
      productGroupId: groupId,
      localStatus: "ready",
      asset: {
        id: "asset-product",
        fileName: "sofa.jpg",
        mediaKind: "image",
        sizeBytes: 2048,
        localPreviewUrl: "blob:http://local/sofa",
        libraryKey: null,
      },
    },
    {
      id: "ref-midas",
      type: "midas",
      source: "midas_library",
      role: "midas_reference",
      relationship: "supporting_context",
      productGroupId: null,
      asset: {
        id: "asset-midas",
        fileName: "Studio white sweep",
        mediaKind: "image",
        sizeBytes: null,
        localPreviewUrl: null,
        libraryKey: "midas-white-sweep",
      },
    },
  ];
  item.scope.outputs = concepts.map((concept) => output(concept, item.scope));
  item.scope.outputs = item.scope.outputs.map((entry) =>
    entry.concept === "lifestyle" || entry.concept === "variations" || entry.concept === "others"
      ? { ...entry, views: ["close_up"], proportion: "4:5", resolution: "4k" }
      : entry,
  );
  draft.preferences = { useWorkflowDefaults: false, lighting: "soft_daylight", wall: "ivory", floor: "light_oak" };
  draft.suggestions = { plants: "suggest", human: "suggest", mood: "warm_inviting" };
  return draft;
}

async function submitted(draft: ClientJobDraft, activeItemId = draft.items[0]?.id): Promise<ProposedJobContract> {
  const outcome = await submitPreparedJob(draft, "audit-key", activeItemId);
  assert.equal(outcome.ok, true);
  if (!outcome.ok) throw new Error("submit failed");
  return outcome.contract;
}

describe("client first submission audit", () => {
  it("keeps the current UI selections in the submitted contract", async () => {
    const draft = readyDraft();
    const contract = await submitted(draft);
    const item = contract.brief.items[0];
    assert.ok(item);
    assert.deepEqual(contract.brief.job, { kind: "new_project", newProjectMode: "one_by_one" });
    assert.equal(contract.role, null);
    assert.equal(contract.category, "home-furniture/living-rooms");
    assert.equal(item.department, "home-furniture");
    assert.equal(item.category, "home-furniture/living-rooms");
    assert.equal(item.subcategory, "home-furniture/living-rooms/sofa");
    assert.equal(item.categoryState, "specified");
    assert.deepEqual(
      item.requestedPackage.map((entry) => entry.concept),
      concepts,
    );
    assert.deepEqual(contract.package[0]?.outputs, item.requestedPackage);
    const lifestyle = item.requestedPackage.find((entry) => entry.concept === "lifestyle");
    const variations = item.requestedPackage.find((entry) => entry.concept === "variations");
    const others = item.requestedPackage.find((entry) => entry.concept === "others");
    assert.deepEqual(lifestyle, { concept: "lifestyle", views: ["close_up"], proportion: "4:5", resolution: "4k" });
    assert.deepEqual(variations, { concept: "variations", views: ["close_up"], proportion: "4:5", resolution: "4k", variationCount: 3 });
    assert.equal(JSON.stringify(variations).includes("lighting"), false);
    assert.deepEqual(others, { concept: "others", otherLabel: "A styled corner", views: ["close_up"], proportion: "4:5", resolution: "4k" });
    const white = item.requestedPackage.find((entry) => entry.concept === "white_bk");
    assert.deepEqual(white, {
      concept: "white_bk",
      views: ["category_template"],
      proportion: "standard_for_category",
      resolution: "standard_for_category",
    });
    assert.deepEqual(contract.brief.preferences, { lighting: "soft_daylight", wall: "ivory", floor: "light_oak" });
    assert.deepEqual(contract.brief.suggestions, { plants: "suggest", human: "suggest", mood: "warm_inviting" });
    assert.deepEqual(item.references, [
      {
        id: "ref-product",
        type: "product_image",
        source: "local_file",
        role: "product",
        relationship: "same_product",
        productGroupId: item.productGroupId,
        evidence: { fileName: "sofa.jpg", mediaKind: "image", sizeBytes: 2048, libraryKey: null },
      },
      {
        id: "ref-midas",
        type: "midas",
        source: "midas_library",
        role: "midas_reference",
        relationship: "supporting_context",
        productGroupId: null,
        evidence: { fileName: "Studio white sweep", mediaKind: "image", sizeBytes: null, libraryKey: "midas-white-sweep" },
      },
    ]);
    assert.equal(JSON.stringify(contract).includes("blob:"), false);
    assert.equal(contract.fileIds.value, null);
    assert.equal(contract.ownerIdentity.value, null);
    assert.equal(contract.limits.value, null);
  });

  it("submits the visible View & delivery defaults when the user leaves them unchanged", async () => {
    const draft = createEmptyDraft();
    draft.job = { kind: "single_item", newProjectMode: null, editMode: null, savedItemId: null, singleItemRole: "hero" };
    const item = draft.items[0];
    item.item = { categoryState: "automatic_unknown", department: null, category: null, subcategory: null };
    item.scope.outputs = [output("lifestyle", item.scope)];
    const contract = await submitted(draft);
    assert.deepEqual(contract.brief.items[0]?.requestedPackage[0], {
      concept: "lifestyle",
      views: ["category_template"],
      proportion: "standard_for_category",
      resolution: "standard_for_category",
    });
    assert.equal(contract.brief.items[0]?.categoryState, "automatic_unknown");
    assert.equal(contract.brief.items[0]?.department, undefined);
    assert.equal(contract.category, null);
    assert.equal(contract.role, "hero");
    assert.deepEqual(contract.brief.suggestions, { mood: "automatic" });
  });

  it("keeps room preferences when every output is white background", async () => {
    const draft = readyDraft();
    draft.items[0].scope.outputs = [output("white_bk", draft.items[0].scope)];
    const contract = await submitted(draft);
    assert.deepEqual(contract.brief.preferences, { lighting: "soft_daylight", wall: "ivory", floor: "light_oak" });
  });

  it("sends workflow defaults without the cleared room choices", async () => {
    const draft = readyDraft();
    draft.preferences = { useWorkflowDefaults: true, lighting: null, wall: null, floor: null };
    const contract = await submitted(draft);
    assert.deepEqual(contract.brief.preferences, { useWorkflowDefaults: true });
  });

  it("drops mode fields that no longer apply", () => {
    const draft = createEmptyDraft();
    draft.job = {
      kind: "single_item",
      newProjectMode: "batch",
      editMode: "new_item",
      savedItemId: "saving-lounge-chair",
      singleItemRole: "secondary",
    };
    assert.deepEqual(normalizeDraft(draft).job, { kind: "single_item", singleItemRole: "secondary" });

    draft.job = { kind: "new_project", newProjectMode: "batch", editMode: "new_item", savedItemId: "saving-lounge-chair", singleItemRole: "hero" };
    assert.deepEqual(normalizeDraft(draft).job, { kind: "new_project", newProjectMode: "batch" });

    draft.job = { kind: "edit", newProjectMode: "one_by_one", editMode: "new_item", savedItemId: "saving-lounge-chair", singleItemRole: "hero" };
    assert.deepEqual(normalizeDraft(draft).job, { kind: "edit", editMode: "new_item" });
  });

  it("submits each current job combination", async () => {
    const cases = [
      {
        job: { kind: "new_project" as const, newProjectMode: "batch" as const, editMode: null, savedItemId: null, singleItemRole: null },
        expected: { kind: "new_project", newProjectMode: "batch" },
        role: null,
      },
      {
        job: { kind: "new_project" as const, newProjectMode: "one_by_one" as const, editMode: null, savedItemId: null, singleItemRole: null },
        expected: { kind: "new_project", newProjectMode: "one_by_one" },
        role: null,
      },
      {
        job: { kind: "edit" as const, newProjectMode: null, editMode: "choose_from_saving" as const, savedItemId: "saving-lounge-chair", singleItemRole: null },
        expected: { kind: "edit", editMode: "choose_from_saving", savedItemId: "saving-lounge-chair" },
        role: null,
      },
      {
        job: { kind: "edit" as const, newProjectMode: null, editMode: "new_item" as const, savedItemId: null, singleItemRole: null },
        expected: { kind: "edit", editMode: "new_item" },
        role: null,
      },
      {
        job: { kind: "single_item" as const, newProjectMode: null, editMode: null, savedItemId: null, singleItemRole: "hero" as const },
        expected: { kind: "single_item", singleItemRole: "hero" },
        role: "hero" as const,
      },
      {
        job: { kind: "single_item" as const, newProjectMode: null, editMode: null, savedItemId: null, singleItemRole: "secondary" as const },
        expected: { kind: "single_item", singleItemRole: "secondary" },
        role: "secondary" as const,
      },
    ];
    for (const entry of cases) {
      const draft = readyDraft();
      draft.job = entry.job;
      if (entry.job.newProjectMode === "batch") {
        draft.items.push(createEmptyBriefItem());
        draft.items[1].item = { ...draft.items[0].item };
        draft.items[1].scope.outputs = [output("website", draft.items[1].scope)];
      }
      const contract = await submitted(draft, draft.items[0].id);
      assert.deepEqual(contract.brief.job, entry.expected);
      assert.equal(contract.role, entry.role);
      if (entry.job.newProjectMode === "batch") assert.equal(contract.brief.items.length, 2);
      else assert.equal(contract.brief.items.length, 1);
    }
  });

  it("submits a website section as the selected department", async () => {
    const draft = readyDraft();
    draft.items[0].item = {
      categoryState: "specified",
      department: "ashley",
      category: "ashley/living-rooms",
      subcategory: "ashley/living-rooms/sofa-and-love-seats/sofa-sets",
    };
    const contract = await submitted(draft);
    assert.equal(contract.brief.items[0]?.department, "ashley");
    assert.equal(contract.brief.items[0]?.category, "ashley/living-rooms");
    assert.equal(contract.brief.items[0]?.subcategory, "ashley/living-rooms/sofa-and-love-seats/sofa-sets");
    assert.equal(contract.category, "ashley/living-rooms");
  });
});
