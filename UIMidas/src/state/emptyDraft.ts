import { createId } from "../lib/ids";
import type { AdvancedDraft, BriefItem, ClientJobDraft, ItemMetadata } from "../types/draft";

export function createEmptyItemMetadata(): ItemMetadata {
  return {
    specificItemsCombo: "",
    additionalInputData: "",
    sku: "",
    dimensions: "",
    colour: "",
    fabricMaterial: "",
    itemCount: null,
    itemRelationships: "",
    otherPieces: "",
  };
}

export function createEmptyAdvanced(): AdvancedDraft {
  return {
    descriptionMetadataPreference: "",
    previousGeneration: "",
    customPrompting: "",
    fidelity: "",
    styling: "",
    cluttering: "",
    descriptionCheckpoint: "",
    semanticGrounding: "",
  };
}

export function createEmptyBriefItem(): BriefItem {
  return {
    id: createId(),
    item: {
      categoryState: "specified",
      department: null,
      category: null,
      subcategory: null,
    },
    references: {
      primaryProductGroupId: createId(),
      items: [],
    },
    scope: {
      outputs: [],
      deliveryView: "category_template",
      deliveryProportion: "standard_for_category",
      deliveryResolution: "standard_for_category",
    },
    metadata: createEmptyItemMetadata(),
  };
}

export function createEmptyDraft(): ClientJobDraft {
  return {
    job: {
      kind: null,
      newProjectMode: null,
      editMode: null,
      savedItemId: null,
      singleItemRole: null,
    },
    items: [createEmptyBriefItem()],
    preferences: {
      useWorkflowDefaults: false,
      lighting: null,
      wall: null,
      floor: null,
    },
    suggestions: {
      plants: "unspecified",
      human: "unspecified",
      mood: "automatic",
    },
    advanced: createEmptyAdvanced(),
  };
}
