import { itemTaxonomy, itemTaxonomyGroups } from "../../config/options";
import type { ProjectIssue } from "../../lib/projectBrief";
import type { ItemDraft, ReferencesDraft } from "../../types/draft";
import { StepFooter } from "../ui/chrome";
import { ProjectReferencesSection } from "./ProjectReferencesSection";

type UpdateItem = (update: (current: ItemDraft) => ItemDraft) => void;
type UpdateReferences = (update: (current: ReferencesDraft) => ReferencesDraft) => void;

export function ProjectItemSection({
  item,
  references,
  onItem,
  onReferences,
  onBack,
  onContinue,
  issues = [],
}: {
  item: ItemDraft;
  references: ReferencesDraft;
  onItem: UpdateItem;
  onReferences: UpdateReferences;
  onBack: () => void;
  onContinue: () => void;
  issues?: ProjectIssue[];
}) {
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
                onItem(() => ({ categoryState: "automatic_unknown", department: null, category: null, subcategory: null }));
                return;
              }
              onItem(() => ({
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
              onItem((current) => ({
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
              onItem((current) => ({ ...current, categoryState: "specified", subcategory }));
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

      <ProjectReferencesSection references={references} onReferences={onReferences} />

      <StepFooter
        onBack={onBack}
        onContinue={onContinue}
        continueLabel="Choose the outcomes"
        continueDisabled={issues.length > 0}
        showMoreOptions={false}
      />
    </div>
  );
}
