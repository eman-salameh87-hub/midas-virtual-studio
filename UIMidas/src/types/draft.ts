/**
 * One client brief. Sections write their own slice.
 * A batch holds several items. Preferences stay with the job.
 */

export type SectionId =
  | "job"
  | "item"
  | "references"
  | "scope"
  | "preferences"
  | "suggestions"
  | "advanced"
  | "review";

export type JobKind = "new_project" | "edit" | "single_item";
export type NewProjectMode = "batch" | "one_by_one";
export type EditMode = "choose_from_saving" | "new_item";
export type SingleItemRole = "hero" | "secondary";

export interface JobDraft {
  kind: JobKind | null;
  newProjectMode: NewProjectMode | null;
  editMode: EditMode | null;
  /** Set only when editMode is choose_from_saving. Points at a saved brief. */
  savedItemId: string | null;
  singleItemRole: SingleItemRole | null;
}

export type CategoryState = "specified" | "automatic_unknown";

export interface ItemDraft {
  categoryState: CategoryState;
  department: string | null;
  category: string | null;
  subcategory: string | null;
}

export type ReferenceType =
  | "midas"
  | "product_image"
  | "other_view"
  | "detail"
  | "room_image"
  | "previous_result"
  | "inspiration"
  | "specification_file";

export type ReferenceSource = "local_file" | "midas_library";

export type ReferenceRole =
  | "product"
  | "additional_view"
  | "detail"
  | "room"
  | "previous_result"
  | "inspiration"
  | "specification"
  | "midas_reference";

/** Browser-only intake state. Idle belongs to the drop zone, not the reference. */
export type LocalAssetStatus = "uploading" | "ready" | "error";

/** same_product joins the item. supporting_context must not become another product. */
export type ReferenceRelationship = "same_product" | "supporting_context";

export interface ReferenceAsset {
  id: string;
  fileName: string;
  mediaKind: "image" | "file";
  sizeBytes: number | null;
  /** Blob URL kept for on-screen preview only. Omitted from the debug payload. */
  localPreviewUrl: string | null;
  /** Set when the asset comes from the local Midas library sample. */
  libraryKey: string | null;
}

export interface ClientReference {
  id: string;
  type: ReferenceType;
  source: ReferenceSource;
  asset: ReferenceAsset | null;
  role: ReferenceRole;
  relationship: ReferenceRelationship;
  /** Shared by every reference that describes the same product. */
  productGroupId: string | null;
  /**
   * Local intake state for the references screen.
   * Omitted from the normalized brief and the proposed job contract.
   */
  localStatus?: LocalAssetStatus;
  /** Client-facing intake note. Omitted from the normalized brief. */
  localStatusMessage?: string | null;
}

export interface ReferencesDraft {
  /**
   * Product images and other views use this id.
   * Extra images join the group instead of becoming new products.
   */
  primaryProductGroupId: string;
  items: ClientReference[];
}

export type OutputConcept =
  | "white_bk"
  | "lifestyle"
  | "website"
  | "new_composition"
  | "variations"
  | "create_with_this_item"
  | "others";

export type OutputView =
  | "category_template"
  | "wide_view"
  | "close_up"
  | "wide_view_close_up"
  | "front"
  | "three_quarter"
  | "side"
  | "back"
  | "top"
  | "detail"
  | "in_situ";

export type ImageProportion =
  | "standard_for_category"
  | "1:1"
  | "4:5"
  | "16:9"
  | "3:4"
  | "4:3"
  | "9:16"
  | "2:3";

export type ImageResolution =
  | "standard_for_category"
  | "2k"
  | "4k"
  | "web"
  | "standard"
  | "high"
  | "print";

/** UI-only. Not copied into the normalized brief. */
export type VariationAspect = "lighting" | "styling" | "camera_view";

export interface ScopeOutput {
  id: string;
  concept: OutputConcept;
  /** Used when concept is "others". */
  otherLabel: string;
  views: OutputView[];
  proportion: ImageProportion | null;
  resolution: ImageResolution | null;
  variationCount: number | null;
  /** UI-only. Not copied into the normalized brief. */
  variationAspects?: VariationAspect[];
}

export interface ScopeDraft {
  outputs: ScopeOutput[];
  /** UI-only delivery choices, including when no output is selected yet. */
  deliveryView?: OutputView | null;
  deliveryProportion?: ImageProportion | null;
  deliveryResolution?: ImageResolution | null;
}

export type LightingPreference = "soft_daylight" | "golden_afternoon" | "warm_evening";

export type WallPreference =
  | "white"
  | "ivory"
  | "sand"
  | "greige"
  | "taupe"
  | "sage"
  | "charcoal"
  | "terracotta";

export type FloorPreference = "light_oak" | "dark_walnut" | "limestone" | "marble";

export interface PreferencesDraft {
  useWorkflowDefaults: boolean;
  lighting: LightingPreference | null;
  wall: WallPreference | null;
  floor: FloorPreference | null;
}

export type InclusionChoice = "unspecified" | "suggest" | "leave_out";

export type MoodVibe =
  | "automatic"
  | "calm_natural"
  | "warm_inviting"
  | "refined_elegant"
  | "bold_expressive";

export interface SuggestionsDraft {
  plants: InclusionChoice;
  human: InclusionChoice;
  mood: MoodVibe | null;
}

/** Facts that belong to one item. Steering notes stay on the job. */
export interface ItemMetadata {
  specificItemsCombo: string;
  additionalInputData: string;
  sku: string;
  dimensions: string;
  colour: string;
  fabricMaterial: string;
  itemCount: number | null;
  itemRelationships: string;
  otherPieces: string;
}

/**
 * One product in the brief.
 * Its images share references.primaryProductGroupId.
 */
export interface BriefItem {
  id: string;
  item: ItemDraft;
  references: ReferencesDraft;
  scope: ScopeDraft;
  metadata: ItemMetadata;
}

/**
 * Job-level notes. These fields have no steering behavior in this step.
 */
export interface AdvancedDraft {
  descriptionMetadataPreference: string;
  previousGeneration: string;
  customPrompting: string;
  fidelity: string;
  styling: string;
  cluttering: string;
  descriptionCheckpoint: string;
  semanticGrounding: string;
}

export interface ClientJobDraft {
  job: JobDraft;
  items: BriefItem[];
  preferences: PreferencesDraft;
  suggestions: SuggestionsDraft;
  advanced: AdvancedDraft;
}
