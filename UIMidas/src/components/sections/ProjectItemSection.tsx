import type { ProjectIssue } from "../../lib/projectBrief";
import { referenceBlocksContinue } from "../../lib/referenceAnalysis";
import type { ItemDraft, ReferencesDraft } from "../../types/draft";
import { StepFooter } from "../ui/chrome";
import { ItemTaxonomyFields } from "./ItemTaxonomyFields";
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
  const blocked = issues.length > 0 || references.items.some((reference) => referenceBlocksContinue(reference));

  return (
    <div className="stack item">
      <h2 className="item__title" id="section-title" tabIndex={-1}>
        Add your item.
      </h2>

      <ProjectReferencesSection references={references} onReferences={onReferences} onItem={onItem} />
      <ItemTaxonomyFields item={item} onItem={onItem} />

      <StepFooter
        onBack={onBack}
        onContinue={onContinue}
        continueLabel="Choose the outcomes"
        continueDisabled={blocked}
        showMoreOptions={false}
      />
    </div>
  );
}
