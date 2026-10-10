import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { emptyContextCopy, emptyProductCopy, reviewReferenceBlocks } from "./lib/referenceSummary";
import {
  markReferenceReady,
  referenceFromLibrary,
  replaceLocalFile,
  setMidasProductMembership,
  stageLocalFiles,
  withoutReference,
} from "./lib/references";
import { normalizeDraft } from "./normalization/normalizeDraft";
import { createEmptyBriefItem, createEmptyDraft } from "./state/emptyDraft";
import type { ClientReference } from "./types/draft";
import { validateDraft } from "./validation/validateDraft";
import { itemsForRequest } from "./lib/requestItems";

function file(name: string, type: string, contents = "image-bytes"): File {
  return new File([contents], name, { type });
}

function ready(reference: ClientReference): ClientReference {
  return reference.localStatus === "uploading" ? markReferenceReady(reference) : reference;
}

describe("reference assets", () => {
  it("puts several images in one product group", () => {
    const draft = createEmptyDraft();
    const item = draft.items[0];
    const staged = stageLocalFiles(
      [file("front.jpg", "image/jpeg"), file("side.jpg", "image/jpeg"), file("detail.jpg", "image/jpeg")],
      "product",
      item.references.primaryProductGroupId,
      [],
    ).map(ready);

    assert.equal(staged.length, 3);
    assert.equal(new Set(staged.map((entry) => entry.productGroupId)).size, 1);
    assert.ok(staged.every((entry) => entry.relationship === "same_product"));
    assert.equal(staged[0]?.productGroupId, item.references.primaryProductGroupId);
    item.references.items = staged;

    const brief = normalizeDraft(draft, item.id);
    assert.equal(brief.items[0]?.references.length, 3);
    assert.ok(brief.items[0]?.references.every((entry) => entry.productGroupId === brief.items[0]?.productGroupId));
  });

  it("keeps supporting context outside the product group", () => {
    const draft = createEmptyDraft();
    const item = draft.items[0];
    const groupId = item.references.primaryProductGroupId;
    const staged = [
      ...stageLocalFiles([file("front.jpg", "image/jpeg")], "product", groupId, []),
      ...stageLocalFiles([file("room.jpg", "image/jpeg")], "room_image", groupId, []),
      ...stageLocalFiles([file("mood.jpg", "image/jpeg")], "inspiration", groupId, []),
      ...stageLocalFiles([file("notes.pdf", "application/pdf", "spec")], "specification_file", groupId, []),
      ...stageLocalFiles([file("earlier.jpg", "image/jpeg")], "previous_result", groupId, []),
    ].map(ready);
    item.references.items = staged;

    const supporting = staged.filter((entry) => entry.relationship === "supporting_context");
    assert.equal(supporting.length, 4);
    assert.ok(supporting.every((entry) => entry.productGroupId === null));
    const brief = normalizeDraft(draft, item.id);
    const context = brief.items[0]?.references.filter((entry) => entry.relationship === "supporting_context") ?? [];
    assert.ok(context.every((entry) => entry.productGroupId === null));
    assert.ok(context.every((entry) => entry.productGroupId !== brief.items[0]?.productGroupId));
  });

  it("joins a Midas reference to the product only when asked", () => {
    const draft = createEmptyDraft();
    const item = draft.items[0];
    const library = referenceFromLibrary({ id: "midas-white-sweep", name: "Studio white sweep" });
    assert.equal(library.relationship, "supporting_context");
    assert.equal(library.productGroupId, null);

    const joined = setMidasProductMembership(library, true, item.references.primaryProductGroupId);
    assert.equal(joined.relationship, "same_product");
    assert.equal(joined.productGroupId, item.references.primaryProductGroupId);
    assert.equal(joined.type, "midas");
    assert.equal(joined.role, "midas_reference");

    const removed = setMidasProductMembership(joined, false, item.references.primaryProductGroupId);
    assert.equal(removed.productGroupId, null);
  });

  it("keeps batch item references apart", () => {
    const draft = createEmptyDraft();
    draft.job = { kind: "new_project", newProjectMode: "batch", editMode: null, savedItemId: null, singleItemRole: null };
    const second = createEmptyBriefItem();
    draft.items.push(second);
    const first = draft.items[0];
    assert.notEqual(first.references.primaryProductGroupId, second.references.primaryProductGroupId);

    first.references.items = stageLocalFiles(
      [file("chair-front.jpg", "image/jpeg"), file("chair-side.jpg", "image/jpeg")],
      "product",
      first.references.primaryProductGroupId,
      [],
    ).map(ready);
    second.references.items = stageLocalFiles(
      [file("lamp-front.jpg", "image/jpeg")],
      "product",
      second.references.primaryProductGroupId,
      [],
    ).map(ready);

    const requested = itemsForRequest(draft, first.id);
    assert.equal(requested.length, 2);
    assert.equal(requested[0]?.references.items.length, 2);
    assert.equal(requested[1]?.references.items.length, 1);
    assert.notEqual(requested[0]?.references.items[0]?.productGroupId, requested[1]?.references.items[0]?.productGroupId);
    assert.ok(requested[0]?.references.items.every((entry) => entry.asset?.fileName.startsWith("chair-")));
    assert.equal(requested[1]?.references.items[0]?.asset?.fileName, "lamp-front.jpg");
  });

  it("removes a reference without touching the others", () => {
    const draft = createEmptyDraft();
    const item = draft.items[0];
    const staged = stageLocalFiles(
      [file("front.jpg", "image/jpeg"), file("side.jpg", "image/jpeg")],
      "product",
      item.references.primaryProductGroupId,
      [],
    ).map(ready);
    const remaining = withoutReference(staged, staged[0].id);
    assert.equal(remaining.length, 1);
    assert.equal(remaining[0]?.id, staged[1]?.id);
    assert.equal(remaining[0]?.productGroupId, item.references.primaryProductGroupId);
  });

  it("replaces a reference and keeps its place in the product", () => {
    const draft = createEmptyDraft();
    const groupId = draft.items[0].references.primaryProductGroupId;
    const original = ready(stageLocalFiles([file("front.jpg", "image/jpeg")], "product", groupId, [])[0]);
    const replaced = ready(replaceLocalFile(original, file("front-new.jpg", "image/jpeg", "replacement"), groupId, []));
    assert.equal(replaced.id, original.id);
    assert.equal(replaced.asset?.fileName, "front-new.jpg");
    assert.equal(replaced.productGroupId, groupId);
    assert.equal(replaced.relationship, "same_product");
    assert.notEqual(replaced.asset?.id, original.asset?.id);
  });

  it("leaves preview urls and intake state out of the normalized brief", () => {
    const draft = createEmptyDraft();
    const item = draft.items[0];
    const staged = ready(stageLocalFiles([file("front.jpg", "image/jpeg")], "product", item.references.primaryProductGroupId, [])[0]);
    staged.asset = staged.asset
      ? { ...staged.asset, localPreviewUrl: "blob:http://local/preview" }
      : staged.asset;
    item.references.items = [staged];

    const brief = normalizeDraft(draft, item.id);
    const encoded = JSON.stringify(brief);
    assert.equal(encoded.includes("blob:"), false);
    assert.equal(encoded.includes("localPreviewUrl"), false);
    assert.equal(encoded.includes("localStatus"), false);
    assert.equal(brief.items[0]?.references[0]?.type, "product_image");
    assert.equal(brief.items[0]?.references[0]?.source, "local_file");
    assert.equal(brief.items[0]?.references[0]?.role, "product");
    assert.equal(brief.items[0]?.references[0]?.relationship, "same_product");
    assert.equal(brief.items[0]?.references[0]?.productGroupId, item.references.primaryProductGroupId);
    assert.equal(brief.items[0]?.id, item.id);
  });

  it("summarizes product images separately from supporting context", () => {
    const groupId = "product-1";
    const references: ClientReference[] = [
      ready(stageLocalFiles([file("front.jpg", "image/jpeg")], "product", groupId, [])[0]),
      ready(stageLocalFiles([file("side.jpg", "image/jpeg")], "product", groupId, [])[0]),
      ready(stageLocalFiles([file("detail.jpg", "image/jpeg")], "product", groupId, [])[0]),
    ];
    const midas = setMidasProductMembership(referenceFromLibrary({ id: "midas-1", name: "Sweep" }), true, groupId);
    const room = ready(stageLocalFiles([file("room.jpg", "image/jpeg")], "room_image", groupId, [])[0]);
    const spec = ready(stageLocalFiles([file("sheet.pdf", "application/pdf", "spec")], "specification_file", groupId, [])[0]);

    const [single] = reviewReferenceBlocks([{ title: null, references: [...references, midas, room, spec] }]);
    assert.deepEqual(single?.lines, [
      "Product",
      "3 images",
      "1 Midas reference",
      "Supporting context",
      "1 room",
      "1 specification",
    ]);

    const batch = reviewReferenceBlocks([
      { title: "Item 1", references: [...references, room] },
      { title: "Item 2", references: references.slice(0, 2) },
    ]);
    assert.deepEqual(batch[0]?.lines, ["Product", "3 images", "Supporting context", "1 room"]);
    assert.deepEqual(batch[1]?.lines, ["Product", "2 images", "Supporting context", "No supporting context added."]);
    assert.equal(batch[0]?.title, "Item 1");
    assert.equal(batch[1]?.title, "Item 2");
  });

  it("describes an empty reference list without treating it as an error", () => {
    const [block] = reviewReferenceBlocks([{ title: null, references: [] }]);
    assert.ok(block?.lines.includes(emptyProductCopy));
    assert.ok(block?.lines.includes("Supporting context"));
    assert.ok(block?.lines.includes(emptyContextCopy));
    assert.equal(block?.lines.some((line) => line.toLowerCase().includes("error")), false);
  });

  it("records a local upload problem without sending it in the brief", () => {
    const draft = createEmptyDraft();
    draft.job = { kind: "single_item", newProjectMode: null, editMode: null, savedItemId: null, singleItemRole: "hero" };
    const item = draft.items[0];
    const groupId = item.references.primaryProductGroupId;
    const empty = stageLocalFiles([file("blank.jpg", "image/jpeg", "")], "product", groupId, [])[0];
    const unsupported = stageLocalFiles([file("notes.zip", "application/zip", "zip")], "product", groupId, [])[0];
    const first = ready(stageLocalFiles([file("front.jpg", "image/jpeg")], "product", groupId, [])[0]);
    const duplicate = stageLocalFiles([file("front.jpg", "image/jpeg")], "product", groupId, [first])[0];

    assert.equal(empty.localStatus, "error");
    assert.equal(empty.localStatusMessage, "This file is empty.");
    assert.equal(unsupported.localStatus, "error");
    assert.equal(unsupported.localStatusMessage, "Use a JPG, PNG, or WebP image for this product.");
    assert.equal(duplicate.localStatus, "error");
    assert.equal(duplicate.localStatusMessage, "This file is already here.");

    item.references.items = [empty];
    item.scope.outputs = [
      { id: "life", concept: "lifestyle", otherLabel: "", views: [], proportion: null, resolution: null, variationCount: null },
    ];
    const result = validateDraft(draft, item.id);
    assert.equal(result.valid, false);
    assert.ok(result.issues.some((issue) => issue.message === "This file is empty."));

    const brief = normalizeDraft(draft, item.id);
    assert.equal(brief.items[0]?.references.length, 0);
    assert.equal(JSON.stringify(brief).includes("blank.jpg"), false);
  });

  it("rejects GIF and HEIC product uploads that Phase-0 cannot intake", () => {
    const groupId = "group-1";
    const gif = stageLocalFiles([file("shot.gif", "image/gif")], "product", groupId, [])[0];
    const heic = stageLocalFiles([file("shot.heic", "image/heic")], "product", groupId, [])[0];
    assert.equal(gif.localStatus, "error");
    assert.equal(heic.localStatus, "error");
    assert.match(gif.localStatusMessage ?? "", /JPG, PNG, or WebP/);
  });
});
