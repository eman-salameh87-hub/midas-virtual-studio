import { itemsForRequest } from "../lib/requestItems";
import type {
  AdvancedDraft,
  BriefItem,
  ClientJobDraft,
  ClientReference,
  ItemMetadata,
  PreferencesDraft,
  ScopeOutput,
  SuggestionsDraft,
} from "../types/draft";

export interface NormalizedEvidence {
  fileName: string;
  mediaKind: "image" | "file";
  sizeBytes: number | null;
  libraryKey: string | null;
}

export interface NormalizedReference {
  id: string;
  type: ClientReference["type"];
  source: ClientReference["source"];
  role: ClientReference["role"];
  relationship: ClientReference["relationship"];
  productGroupId: string | null;
  evidence: NormalizedEvidence | null;
}

export interface NormalizedPackageOutput {
  concept: ScopeOutput["concept"];
  otherLabel?: string;
  views?: ScopeOutput["views"];
  proportion?: NonNullable<ScopeOutput["proportion"]>;
  resolution?: NonNullable<ScopeOutput["resolution"]>;
  variationCount?: number;
}

export interface NormalizedItemMetadata {
  specificItemsCombo?: string;
  additionalInputData?: string;
  sku?: string;
  dimensions?: string;
  colour?: string;
  fabricMaterial?: string;
  itemCount?: number;
  itemRelationships?: string;
  otherPieces?: string;
}

export interface NormalizedBriefItem {
  id: string;
  productGroupId: string;
  categoryState: BriefItem["item"]["categoryState"];
  department?: string;
  category?: string;
  subcategory?: string;
  references: NormalizedReference[];
  requestedPackage: NormalizedPackageOutput[];
  metadata?: NormalizedItemMetadata;
}

export interface NormalizedJob {
  kind?: NonNullable<ClientJobDraft["job"]["kind"]>;
  newProjectMode?: NonNullable<ClientJobDraft["job"]["newProjectMode"]>;
  editMode?: NonNullable<ClientJobDraft["job"]["editMode"]>;
  savedItemId?: string;
  singleItemRole?: NonNullable<ClientJobDraft["job"]["singleItemRole"]>;
}

export interface NormalizedPreferences {
  useWorkflowDefaults?: true;
  lighting?: NonNullable<PreferencesDraft["lighting"]>;
  wall?: NonNullable<PreferencesDraft["wall"]>;
  floor?: NonNullable<PreferencesDraft["floor"]>;
}

export interface NormalizedSuggestions {
  plants?: Exclude<SuggestionsDraft["plants"], "unspecified">;
  human?: Exclude<SuggestionsDraft["human"], "unspecified">;
  mood?: NonNullable<SuggestionsDraft["mood"]>;
}

export interface NormalizedNotes {
  descriptionMetadataPreference?: string;
  previousGeneration?: string;
  customPrompting?: string;
  fidelity?: string;
  styling?: string;
  cluttering?: string;
  descriptionCheckpoint?: string;
  semanticGrounding?: string;
}

export interface NormalizedClientBrief {
  job: NormalizedJob;
  items: NormalizedBriefItem[];
  preferences?: NormalizedPreferences;
  suggestions?: NormalizedSuggestions;
  notes?: NormalizedNotes;
}

function filled(value: string): string | undefined {
  const trimmed = value.trim();
  return trimmed === "" ? undefined : trimmed;
}

function isSettledReference(reference: ClientReference): boolean {
  return reference.localStatus !== "uploading" && reference.localStatus !== "error";
}

function normalizeReference(reference: ClientReference): NormalizedReference {
  const asset = reference.asset;
  return {
    id: reference.id,
    type: reference.type,
    source: reference.source,
    role: reference.role,
    relationship: reference.relationship,
    productGroupId: reference.productGroupId,
    evidence: asset
      ? {
          fileName: asset.fileName,
          mediaKind: asset.mediaKind,
          sizeBytes: asset.sizeBytes,
          libraryKey: asset.libraryKey,
        }
      : null,
  };
}

function normalizeOutput(output: ScopeOutput): NormalizedPackageOutput {
  const normalized: NormalizedPackageOutput = { concept: output.concept };
  const otherLabel = filled(output.otherLabel);
  if (otherLabel) normalized.otherLabel = otherLabel;
  if (output.views.length > 0) normalized.views = output.views;
  if (output.proportion) normalized.proportion = output.proportion;
  if (output.resolution) normalized.resolution = output.resolution;
  if (output.variationCount !== null) normalized.variationCount = output.variationCount;
  return normalized;
}

function normalizeMetadata(metadata: ItemMetadata): NormalizedItemMetadata | undefined {
  const normalized: NormalizedItemMetadata = {};
  const specificItemsCombo = filled(metadata.specificItemsCombo);
  const additionalInputData = filled(metadata.additionalInputData);
  const sku = filled(metadata.sku);
  const dimensions = filled(metadata.dimensions);
  const colour = filled(metadata.colour);
  const fabricMaterial = filled(metadata.fabricMaterial);
  const itemRelationships = filled(metadata.itemRelationships);
  const otherPieces = filled(metadata.otherPieces);
  if (specificItemsCombo) normalized.specificItemsCombo = specificItemsCombo;
  if (additionalInputData) normalized.additionalInputData = additionalInputData;
  if (sku) normalized.sku = sku;
  if (dimensions) normalized.dimensions = dimensions;
  if (colour) normalized.colour = colour;
  if (fabricMaterial) normalized.fabricMaterial = fabricMaterial;
  if (metadata.itemCount !== null) normalized.itemCount = metadata.itemCount;
  if (itemRelationships) normalized.itemRelationships = itemRelationships;
  if (otherPieces) normalized.otherPieces = otherPieces;
  return Object.keys(normalized).length > 0 ? normalized : undefined;
}

function normalizeItem(briefItem: BriefItem): NormalizedBriefItem {
  const normalized: NormalizedBriefItem = {
    id: briefItem.id,
    productGroupId: briefItem.references.primaryProductGroupId,
    categoryState: briefItem.item.categoryState,
    references: briefItem.references.items.filter(isSettledReference).map(normalizeReference),
    requestedPackage: briefItem.scope.outputs.map(normalizeOutput),
  };
  if (briefItem.item.department) normalized.department = briefItem.item.department;
  if (briefItem.item.category) normalized.category = briefItem.item.category;
  if (briefItem.item.subcategory) normalized.subcategory = briefItem.item.subcategory;
  const metadata = normalizeMetadata(briefItem.metadata);
  if (metadata) normalized.metadata = metadata;
  return normalized;
}

function normalizeJob(draft: ClientJobDraft): NormalizedJob {
  const job = draft.job;
  if (!job.kind) return {};
  if (job.kind === "new_project") {
    return job.newProjectMode ? { kind: job.kind, newProjectMode: job.newProjectMode } : { kind: job.kind };
  }
  if (job.kind === "edit") {
    const normalized: NormalizedJob = { kind: job.kind };
    if (job.editMode) normalized.editMode = job.editMode;
    if (job.editMode === "choose_from_saving" && job.savedItemId) normalized.savedItemId = job.savedItemId;
    return normalized;
  }
  return job.singleItemRole ? { kind: job.kind, singleItemRole: job.singleItemRole } : { kind: job.kind };
}

function normalizePreferences(preferences: PreferencesDraft): NormalizedPreferences | undefined {
  if (preferences.useWorkflowDefaults) return { useWorkflowDefaults: true };
  const normalized: NormalizedPreferences = {};
  if (preferences.lighting) normalized.lighting = preferences.lighting;
  if (preferences.wall) normalized.wall = preferences.wall;
  if (preferences.floor) normalized.floor = preferences.floor;
  return Object.keys(normalized).length > 0 ? normalized : undefined;
}

function normalizeSuggestions(suggestions: SuggestionsDraft): NormalizedSuggestions | undefined {
  const normalized: NormalizedSuggestions = {};
  if (suggestions.plants !== "unspecified") normalized.plants = suggestions.plants;
  if (suggestions.human !== "unspecified") normalized.human = suggestions.human;
  if (suggestions.mood) normalized.mood = suggestions.mood;
  return Object.keys(normalized).length > 0 ? normalized : undefined;
}

function normalizeNotes(notes: AdvancedDraft): NormalizedNotes | undefined {
  const normalized: NormalizedNotes = {};
  const entries = Object.entries(notes) as [keyof AdvancedDraft, string][];
  for (const [key, value] of entries) {
    const next = filled(value);
    if (next) normalized[key] = next;
  }
  return Object.keys(normalized).length > 0 ? normalized : undefined;
}

/** Draft values that belong in a backend contract. Preview URLs stay out. */
export function normalizeDraft(draft: ClientJobDraft, activeItemId?: string): NormalizedClientBrief {
  const brief: NormalizedClientBrief = {
    job: normalizeJob(draft),
    items: itemsForRequest(draft, activeItemId).map(normalizeItem),
  };
  const preferences = normalizePreferences(draft.preferences);
  const suggestions = normalizeSuggestions(draft.suggestions);
  const notes = normalizeNotes(draft.advanced);
  if (preferences) brief.preferences = preferences;
  if (suggestions) brief.suggestions = suggestions;
  if (notes) brief.notes = notes;
  return brief;
}
