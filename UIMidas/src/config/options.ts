import type {
  EditMode,
  FloorPreference,
  ImageProportion,
  ImageResolution,
  InclusionChoice,
  JobKind,
  LightingPreference,
  MoodVibe,
  NewProjectMode,
  OutputConcept,
  OutputView,
  ReferenceRelationship,
  ReferenceRole,
  ReferenceSource,
  ReferenceType,
  SingleItemRole,
  WallPreference,
} from "../types/draft";
import { departmentTaxonomy as extractedDepartments, websiteSectionTaxonomy as extractedSections } from "./midasTaxonomy";

/**
 * Local stand-ins for laying out the screen.
 * Not a production catalogue, library, or saved-work service.
 */

export interface LabeledOption<T extends string> {
  value: T;
  label: string;
  description?: string;
}

export const jobKindOptions: LabeledOption<JobKind>[] = [
  {
    value: "new_project",
    label: "New project",
    description: "Start work that is not already in the studio.",
  },
  {
    value: "edit",
    label: "Edit",
    description: "Change an existing piece of work.",
  },
  {
    value: "single_item",
    label: "Single item",
    description: "One piece, placed in a larger set.",
  },
];

export const newProjectModeOptions: LabeledOption<NewProjectMode>[] = [
  {
    value: "batch",
    label: "Batch",
    description: "Several items prepared as one project.",
  },
  {
    value: "one_by_one",
    label: "One by one (same department)",
    description: "Each item is briefed on its own.",
  },
];

export const editModeOptions: LabeledOption<EditMode>[] = [
  {
    value: "choose_from_saving",
    label: "Choose from saving",
    description: "Open a brief that was saved earlier.",
  },
  {
    value: "new_item",
    label: "New item",
    description: "Add a new item to this edit.",
  },
];

export const singleItemRoleOptions: LabeledOption<SingleItemRole>[] = [
  {
    value: "hero",
    label: "Hero",
    description: "The piece the picture is built around.",
  },
  {
    value: "secondary",
    label: "Secondary",
    description: "A supporting piece alongside something else.",
  },
];

export const mockSavedBriefs = [
  { id: "saving-lounge-chair", label: "Lounge chair" },
  { id: "saving-table-lamp", label: "Ceramic table lamp" },
  { id: "saving-linen-sofa", label: "Linen sofa" },
] as const;

export interface TaxonomyCategory {
  id: string;
  label: string;
  subcategories: { id: string; label: string }[];
}

export type TaxonomyOptionType = "department" | "website_section";

export interface TaxonomyDepartment {
  id: string;
  label: string;
  type: TaxonomyOptionType;
  categories: TaxonomyCategory[];
}

const departmentTaxonomy = extractedDepartments as TaxonomyDepartment[];
const websiteSectionTaxonomy = extractedSections as TaxonomyDepartment[];

export const itemTaxonomyGroups: { label: string; options: TaxonomyDepartment[] }[] = [
  { label: "Departments", options: departmentTaxonomy },
  { label: "Other website sections", options: websiteSectionTaxonomy },
];

/** Earlier sample ids. Kept so stored briefs still resolve. Not shown in the Department control. */
const retainedItemTaxonomy: TaxonomyDepartment[] = [
  {
    id: "furniture",
    label: "Furniture",
    type: "department",
    categories: [
      {
        id: "seating",
        label: "Seating",
        subcategories: [
          { id: "lounge-chairs", label: "Lounge chairs" },
          { id: "sofas", label: "Sofas" },
          { id: "stools", label: "Stools" },
        ],
      },
      {
        id: "tables",
        label: "Tables",
        subcategories: [
          { id: "dining-tables", label: "Dining tables" },
          { id: "side-tables", label: "Side tables" },
          { id: "coffee-tables", label: "Coffee tables" },
        ],
      },
    ],
  },
  {
    id: "lighting",
    label: "Lighting",
    type: "department",
    categories: [
      {
        id: "lamps",
        label: "Lamps",
        subcategories: [
          { id: "table-lamps", label: "Table lamps" },
          { id: "floor-lamps", label: "Floor lamps" },
        ],
      },
      { id: "pendants", label: "Pendants", subcategories: [] },
    ],
  },
  {
    id: "textiles",
    label: "Textiles",
    type: "department",
    categories: [
      { id: "rugs", label: "Rugs", subcategories: [] },
      { id: "cushions", label: "Cushions", subcategories: [] },
    ],
  },
];

export const itemTaxonomy: TaxonomyDepartment[] = [
  ...departmentTaxonomy,
  ...websiteSectionTaxonomy,
  ...retainedItemTaxonomy,
];

export const mockMidasReferences = [
  { id: "midas-white-sweep", name: "Studio white sweep" },
  { id: "midas-daylight-room", name: "Soft daylight room" },
  { id: "midas-material-set", name: "Material close-up set" },
] as const;

export const referenceTypeOptions: LabeledOption<ReferenceType>[] = [
  { value: "product_image", label: "Product image" },
  { value: "other_view", label: "Other view" },
  { value: "detail", label: "Detail" },
  { value: "midas", label: "Midas reference" },
  { value: "room_image", label: "Room" },
  { value: "previous_result", label: "Previous result" },
  { value: "inspiration", label: "Inspiration" },
  { value: "specification_file", label: "Specification file" },
];

export const referenceRoleLabels: Record<ReferenceRole, string> = {
  product: "Product",
  additional_view: "Additional view",
  detail: "Detail",
  room: "Room",
  previous_result: "Previous result",
  inspiration: "Inspiration",
  specification: "Specification",
  midas_reference: "Midas reference",
};

export const referenceSourceLabels: Record<ReferenceSource, string> = {
  local_file: "Local file",
  midas_library: "Midas library",
};

export const referenceRelationshipLabels: Record<ReferenceRelationship, string> = {
  same_product: "Same product",
  supporting_context: "Supporting context",
};

export const outputConceptOptions: LabeledOption<OutputConcept>[] = [
  {
    value: "white_bk",
    label: "White BK",
    description: "The item on a white background.",
  },
  {
    value: "lifestyle",
    label: "Lifestyle",
    description: "The item in a lived-in setting.",
  },
  {
    value: "website",
    label: "Website",
    description: "A picture prepared for the site.",
  },
  {
    value: "new_composition",
    label: "New Composition",
    description: "A new arrangement of the scene.",
  },
  {
    value: "variations",
    label: "Variations",
    description: "Several versions of an output.",
  },
  {
    value: "create_with_this_item",
    label: "Create with this item",
    description: "Build the picture around this item.",
  },
  {
    value: "others",
    label: "Others",
    description: "An output that needs its own name.",
  },
];

export const deliveryViewOptions: LabeledOption<OutputView>[] = [
  { value: "category_template", label: "Category template" },
  { value: "wide_view", label: "Wide view" },
  { value: "close_up", label: "Close-up" },
  { value: "wide_view_close_up", label: "Wide view + close-up" },
];

export const deliveryProportionOptions: LabeledOption<ImageProportion>[] = [
  { value: "standard_for_category", label: "Standard for category" },
  { value: "1:1", label: "Square · 1:1" },
  { value: "4:5", label: "Portrait · 4:5" },
  { value: "16:9", label: "Landscape · 16:9" },
];

export const deliveryResolutionOptions: LabeledOption<ImageResolution>[] = [
  { value: "standard_for_category", label: "Standard for category" },
  { value: "2k", label: "2K" },
  { value: "4k", label: "4K" },
];

/** Includes earlier stored ids so existing briefs still resolve. The Scope dropdown uses the delivery lists. */
export const outputViewOptions: LabeledOption<OutputView>[] = [
  ...deliveryViewOptions,
  { value: "front", label: "Front" },
  { value: "three_quarter", label: "Three-quarter" },
  { value: "side", label: "Side" },
  { value: "back", label: "Back" },
  { value: "top", label: "Top" },
  { value: "detail", label: "Detail" },
  { value: "in_situ", label: "In situ" },
];

export const proportionOptions: LabeledOption<ImageProportion>[] = [
  ...deliveryProportionOptions,
  { value: "3:4", label: "3:4" },
  { value: "4:3", label: "4:3" },
  { value: "9:16", label: "9:16" },
  { value: "2:3", label: "2:3" },
];

export const resolutionOptions: LabeledOption<ImageResolution>[] = [
  ...deliveryResolutionOptions,
  { value: "web", label: "Web" },
  { value: "standard", label: "Standard" },
  { value: "high", label: "High" },
  { value: "print", label: "Print" },
];

export const lightingOptions: (LabeledOption<LightingPreference> & {
  accent: "daylight" | "afternoon" | "evening";
})[] = [
  { value: "soft_daylight", label: "Soft daylight", description: "Even, cool-neutral light.", accent: "daylight" },
  { value: "golden_afternoon", label: "Golden afternoon", description: "Warm light and a longer shadow.", accent: "afternoon" },
  { value: "warm_evening", label: "Warm evening", description: "Low, amber light.", accent: "evening" },
];

export const wallOptions: (LabeledOption<WallPreference> & { swatch: string })[] = [
  { value: "white", label: "White", swatch: "#f7f6f3" },
  { value: "ivory", label: "Ivory", swatch: "#f3ead7" },
  { value: "sand", label: "Sand", swatch: "#e4d2b6" },
  { value: "greige", label: "Greige", swatch: "#d5cdc3" },
  { value: "taupe", label: "Taupe", swatch: "#b7a99a" },
  { value: "sage", label: "Sage", swatch: "#a8b5a0" },
  { value: "charcoal", label: "Charcoal", swatch: "#3e3e3c" },
  { value: "terracotta", label: "Terracotta", swatch: "#c46a4a" },
];

export const floorOptions: (LabeledOption<FloorPreference> & { swatch: string })[] = [
  { value: "light_oak", label: "Light oak", swatch: "linear-gradient(135deg, #eddcc4, #c9a67a)" },
  { value: "dark_walnut", label: "Dark walnut", swatch: "linear-gradient(135deg, #6b4630, #3d291c)" },
  { value: "limestone", label: "Limestone", swatch: "linear-gradient(135deg, #e8e3da, #cfc6b8)" },
  { value: "marble", label: "Marble", swatch: "linear-gradient(135deg, #f6f4f1 20%, #d5d0c9 42%, #f7f5f2 43%, #c8c2bb 70%, #f4f1ec)" },
];

export const moodOptions: LabeledOption<MoodVibe>[] = [
  { value: "automatic", label: "Automatic", description: "Leave the mood open." },
  { value: "calm_natural", label: "Calm & natural", description: "Quiet, daylight, unforced." },
  { value: "warm_inviting", label: "Warm & inviting", description: "Soft warmth and welcome." },
  { value: "refined_elegant", label: "Refined & elegant", description: "Spare, precise, polished." },
  { value: "bold_expressive", label: "Bold & expressive", description: "Stronger contrast and character." },
];

export const inclusionOptions: LabeledOption<Exclude<InclusionChoice, "unspecified">>[] = [
  { value: "suggest", label: "Suggest" },
  { value: "leave_out", label: "Leave out" },
];

export function optionLabel<T extends string>(
  options: readonly { value: T; label: string }[],
  value: T | null | undefined,
): string {
  if (!value) return "Not set";
  return options.find((option) => option.value === value)?.label ?? value;
}

export function departmentById(id: string | null) {
  if (!id) return null;
  return itemTaxonomy.find((department) => department.id === id) ?? null;
}

export function categoryById(departmentId: string | null, categoryId: string | null) {
  if (!categoryId) return null;
  return departmentById(departmentId)?.categories.find((category) => category.id === categoryId) ?? null;
}
