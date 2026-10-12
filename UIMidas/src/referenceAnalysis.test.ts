import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { ReferenceIntakeResult } from "./adapters/analyzeReferenceIntake";
import { matchItemTaxonomy, resolveTaxonomy } from "./lib/matchItemTaxonomy";
import {
  applyIntakeResult,
  applyTaxonomyFromIntake,
  invalidateAnalysis,
  nextAnalysisGeneration,
  referenceBlocksContinue,
} from "./lib/referenceAnalysis";
import { createEmptyBriefItem } from "./state/emptyDraft";
import type { ClientReference, ItemDraft } from "./types/draft";

function imageRef(): ClientReference {
  return {
    id: "ref-1",
    type: "product_image",
    source: "local_file",
    asset: {
      id: "asset-1",
      fileName: "chair.png",
      mediaKind: "image",
      sizeBytes: 12,
      localPreviewUrl: "blob:http://local/preview",
      libraryKey: null,
    },
    role: "product",
    relationship: "same_product",
    productGroupId: "group-1",
    localStatus: "ready",
    analysisStatus: "pending",
    analysisGeneration: 1,
    typeEditedByUser: false,
    relevanceConfirmed: false,
  };
}

const accepted: ReferenceIntakeResult = {
  status: "accepted",
  relevant: true,
  needs_confirmation: false,
  suggested_reference_type: "product_image",
  department: "home-furniture",
  category: "home-furniture/living-rooms",
  subcategory: "home-furniture/living-rooms/sofa",
  message: "Recognized as furniture or interior product reference material.",
};

describe("reference analysis helpers", () => {
  it("applies successful classification and taxonomy", () => {
    const applied = applyIntakeResult(imageRef(), 1, accepted, "group-1");
    assert.equal(applied?.analysisStatus, "accepted");
    assert.equal(applied?.type, "product_image");
    const item: ItemDraft = {
      categoryState: "automatic_unknown",
      department: null,
      category: null,
      subcategory: null,
    };
    const next = applyTaxonomyFromIntake(item, accepted);
    assert.equal(next.department, "home-furniture");
    assert.equal(next.category, "home-furniture/living-rooms");
    assert.equal(next.subcategory, "home-furniture/living-rooms/sofa");
  });

  it("rejects non-furniture and does not treat it as valid", () => {
    const applied = applyIntakeResult(
      imageRef(),
      1,
      {
        status: "rejected",
        relevant: false,
        needs_confirmation: false,
        suggested_reference_type: null,
        department: "home-furniture",
        category: null,
        subcategory: null,
        message: "not furniture",
      },
      "group-1",
    );
    assert.equal(applied?.analysisStatus, "rejected");
    assert.equal(referenceBlocksContinue(applied!), true);
    assert.equal(applyTaxonomyFromIntake(createEmptyBriefItem().item, {
      status: "rejected",
      relevant: false,
      needs_confirmation: false,
      suggested_reference_type: null,
      department: "home-furniture",
      category: null,
      subcategory: null,
      message: "not furniture",
    }).department, null);
  });

  it("keeps uncertain images from continuing until confirmed", () => {
    const applied = applyIntakeResult(
      imageRef(),
      1,
      {
        status: "uncertain",
        relevant: false,
        needs_confirmation: true,
        suggested_reference_type: null,
        department: null,
        category: null,
        subcategory: null,
        message: "confirm",
      },
      "group-1",
    );
    assert.equal(applied?.analysisStatus, "uncertain");
    assert.equal(referenceBlocksContinue(applied!), true);
  });

  it("does not overwrite manual taxonomy or reference type", () => {
    const typed = { ...imageRef(), type: "room_image" as const, typeEditedByUser: true, role: "room" as const };
    const applied = applyIntakeResult(typed, 1, accepted, "group-1");
    assert.equal(applied?.type, "room_image");
    const manual: ItemDraft = {
      categoryState: "specified",
      department: "office-furniture",
      category: "office-furniture/office-chairs",
      subcategory: null,
      taxonomyEditedByUser: true,
    };
    assert.equal(applyTaxonomyFromIntake(manual, accepted).department, "office-furniture");
  });

  it("ignores stale generations after replace", () => {
    const first = imageRef();
    const replaced = invalidateAnalysis(first);
    assert.equal(replaced.analysisStatus, "pending");
    assert.equal(replaced.analysisGeneration, 2);
    assert.equal(applyIntakeResult(replaced, 1, accepted, "group-1"), null);
    assert.equal(applyIntakeResult(replaced, 2, accepted, "group-1")?.analysisStatus, "accepted");
    assert.equal(nextAnalysisGeneration(replaced), 3);
  });

  it("maps model labels onto existing taxonomy ids", () => {
    const match = resolveTaxonomy({
      department: "Home Furniture",
      category: "Living Rooms",
      subcategory: "Sofas",
    });
    assert.equal(match.department, "home-furniture");
    assert.equal(match.category, "home-furniture/living-rooms");
    assert.equal(match.subcategory, "home-furniture/living-rooms/sofa");
    const item = applyTaxonomyFromIntake(
      { categoryState: "automatic_unknown", department: null, category: null, subcategory: null },
      {
        ...accepted,
        department: "Home Furniture",
        category: "Living Rooms",
        subcategory: "Sofas",
        suggested_reference_type: "Product / vendor reference" as ReferenceIntakeResult["suggested_reference_type"],
      },
    );
    assert.equal(item.department, "home-furniture");
    assert.equal(item.categoryState, "specified");
  });

  it("matches catalogue names to existing taxonomy only", () => {
    const match = matchItemTaxonomy(
      "ABALI DINING TABLE- WHITE",
      "https://midasfurniture.com/qtr_en/abali-dining-table-dining-rooms-midas.html",
    );
    assert.equal(match.department, "home-furniture");
    assert.equal(match.category, "home-furniture/dining-rooms");
    const unknown = matchItemTaxonomy("zzzz-not-a-category", "https://example.com/nope");
    assert.equal(unknown.department, null);
  });

  it("keeps preview url on the uploaded image asset", () => {
    assert.equal(imageRef().asset?.localPreviewUrl, "blob:http://local/preview");
  });
});
