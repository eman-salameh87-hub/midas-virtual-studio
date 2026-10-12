import { referenceBlocksContinue } from "../../lib/referenceAnalysis";
import { useItemDraft, useReferencesDraft } from "../../state/DraftProvider";
import { StepFooter } from "../ui/chrome";
import { ItemTaxonomyFields } from "./ItemTaxonomyFields";
import { ReferencesSection } from "./ReferencesSection";

export function ItemSection({ onBack, onContinue }: { onBack: () => void; onContinue: () => void }) {
  const [item, setItem] = useItemDraft();
  const [references] = useReferencesDraft();
  const blocked = references.items.some((reference) => referenceBlocksContinue(reference));

  return (
    <div className="stack item">
      <h2 className="item__title" id="section-title" tabIndex={-1}>
        Add your item.
      </h2>

      <ReferencesSection />
      <ItemTaxonomyFields item={item} onItem={setItem} />

      <StepFooter
        onBack={onBack}
        onContinue={onContinue}
        continueLabel="Choose the outcomes"
        continueDisabled={blocked}
      />
    </div>
  );
}
