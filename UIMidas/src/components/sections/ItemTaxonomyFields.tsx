import { itemTaxonomy, itemTaxonomyGroups } from "../../config/options";
import { markTaxonomyManual } from "../../lib/referenceAnalysis";
import type { ItemDraft } from "../../types/draft";
import { StudioSelect } from "../ui/StudioSelect";

type UpdateItem = (update: (current: ItemDraft) => ItemDraft) => void;

export function ItemTaxonomyFields({ item, onItem }: { item: ItemDraft; onItem: UpdateItem }) {
  const automatic = item.categoryState === "automatic_unknown";
  const department = itemTaxonomy.find((entry) => entry.id === item.department) ?? null;
  const category = department?.categories.find((entry) => entry.id === item.category) ?? null;

  return (
    <div className="taxonomy">
      <label className="select-field">
        <span>Department</span>
        <StudioSelect
          value={item.department ?? ""}
          disabled={automatic}
          options={[{ value: "", label: "Automatic from references" }]}
          groups={itemTaxonomyGroups.map((group) => ({
            label: group.label,
            options: group.options.map((option) => ({ value: option.id, label: option.label })),
          }))}
          onChange={(departmentId) => {
            if (!departmentId) {
              onItem(() =>
                markTaxonomyManual({
                  categoryState: "automatic_unknown",
                  department: null,
                  category: null,
                  subcategory: null,
                  taxonomyEditedByUser: true,
                }),
              );
              return;
            }
            onItem(() =>
              markTaxonomyManual({
                categoryState: "specified",
                department: departmentId,
                category: null,
                subcategory: null,
                taxonomyEditedByUser: true,
              }),
            );
          }}
        />
      </label>
      <label className="select-field">
        <span>Category</span>
        <StudioSelect
          value={item.category ?? ""}
          disabled={automatic || !department || department.categories.length === 0}
          options={[
            { value: "", label: "Automatic from references" },
            ...(department?.categories.map((option) => ({ value: option.id, label: option.label })) ?? []),
          ]}
          onChange={(categoryId) => {
            onItem((current) =>
              markTaxonomyManual({
                ...current,
                categoryState: "specified",
                category: categoryId || null,
                subcategory: null,
                taxonomyEditedByUser: true,
              }),
            );
          }}
        />
      </label>
      <label className="select-field">
        <span>Sub-category</span>
        <StudioSelect
          value={item.subcategory ?? ""}
          disabled={automatic || !category || category.subcategories.length === 0}
          options={[
            { value: "", label: "Automatic from references" },
            ...(category?.subcategories.map((option) => ({ value: option.id, label: option.label })) ?? []),
          ]}
          onChange={(subcategory) => {
            onItem((current) =>
              markTaxonomyManual({
                ...current,
                categoryState: "specified",
                subcategory: subcategory || null,
                taxonomyEditedByUser: true,
              }),
            );
          }}
        />
      </label>
    </div>
  );
}
