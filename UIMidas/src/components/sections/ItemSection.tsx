import { itemTaxonomy, itemTaxonomyGroups } from "../../config/options";
import { useItemDraft } from "../../state/DraftProvider";
import { StepFooter } from "../ui/chrome";
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
          <select
            value={item.department ?? ""}
            disabled={automatic}
            onChange={(event) => {
              const departmentId = event.target.value || null;
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
          >
            <option value="">Automatic from references</option>
            {itemTaxonomyGroups.map((group) => (
              <optgroup key={group.label} label={group.label}>
                {group.options.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <label className="select-field">
          <span>Category</span>
          <select
            value={item.category ?? ""}
            disabled={automatic || !department || department.categories.length === 0}
            onChange={(event) => {
              const categoryId = event.target.value || null;
              setItem((current) => ({
                ...current,
                categoryState: "specified",
                category: categoryId,
                subcategory: null,
              }));
            }}
          >
            <option value="">Automatic from references</option>
            {department?.categories.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="select-field">
          <span>Sub-category</span>
          <select
            value={item.subcategory ?? ""}
            disabled={automatic || !category || category.subcategories.length === 0}
            onChange={(event) => {
              const subcategory = event.target.value || null;
              setItem((current) => ({ ...current, categoryState: "specified", subcategory }));
            }}
          >
            <option value="">Automatic from references</option>
            {category?.subcategories.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <ReferencesSection />

      <StepFooter onBack={onBack} onContinue={onContinue} continueLabel="Choose the outcomes" />
    </div>
  );
}
