import type { ItemDraft, ReferencesDraft } from "../../types/draft";
import { ReferencesIntake } from "./ReferencesSection";

type UpdateReferences = (update: (current: ReferencesDraft) => ReferencesDraft) => void;
type UpdateItem = (update: (current: ItemDraft) => ItemDraft) => void;

export function ProjectReferencesSection({
  references,
  onReferences,
  onItem,
}: {
  references: ReferencesDraft;
  onReferences: UpdateReferences;
  onItem?: UpdateItem;
}) {
  return <ReferencesIntake references={references} onReferences={onReferences} onItem={onItem} />;
}
