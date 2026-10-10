import { itemTaxonomy, itemTaxonomyGroups } from "../../config/options";
import type { ProjectIssue } from "../../lib/projectBrief";
import type { ItemDraft, ReferencesDraft } from "../../types/draft";
import { StepFooter } from "../ui/chrome";
import { StudioSelect } from "../ui/StudioSelect";
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
              onItem((current) => ({
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
              onItem((current) => ({ ...current, categoryState: "specified", subcategory: subcategory || null }));
            }}
          />
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
