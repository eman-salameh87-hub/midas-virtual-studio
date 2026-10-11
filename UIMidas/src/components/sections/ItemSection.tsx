import { itemTaxonomy, itemTaxonomyGroups } from "../../config/options";
import { useItemDraft } from "../../state/DraftProvider";
import { StepFooter } from "../ui/chrome";
import { StudioSelect } from "../ui/StudioSelect";
import { ReferencesSection } from "./ReferencesSection";

export function ItemSection({ onBack, onContinue }: { onBack: () => void; onContinue: () => void }) {
  const [item, setItem] = useItemDraft();
  const automatic = item.categoryState === "automatic_unknown";
  const department = itemTaxonomy.find((entry) => entry.id === item.department) ?? null;
  const category = department?.categories.find((entry) => entry.id === item.category) ?? null;

  return (
    <div className="stack item">
      <h2 className="item__title" id="section-title" tabIndex={-1}>
        Add your item.
      </h2>

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
                setItem(() => ({ categoryState: "automatic_unknown", department: null, category: null, subcategory: null }));
                return;
              }
              setItem(() => ({
                categoryState: "specified",
                department: departmentId,
                category: null,
                subcategory: null,
              }));
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
              setItem((current) => ({
                ...current,
                categoryState: "specified",
                category: categoryId || null,
                subcategory: null,
              }));
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
              setItem((current) => ({ ...current, categoryState: "specified", subcategory: subcategory || null }));
            }}
          />
        </label>
      </div>

      <ReferencesSection />

      <StepFooter onBack={onBack} onContinue={onContinue} continueLabel="Choose the outcomes" />
    </div>
  );
}
