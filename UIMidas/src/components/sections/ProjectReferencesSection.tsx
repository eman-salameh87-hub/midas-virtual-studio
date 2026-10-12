import type { ReactNode } from "react";
import type { ItemDraft, ReferencesDraft } from "../../types/draft";
import { ReferencesIntake } from "./ReferencesSection";

type UpdateReferences = (update: (current: ReferencesDraft) => ReferencesDraft) => void;
type UpdateItem = (update: (current: ItemDraft) => ItemDraft) => void;

export function ProjectReferencesSection({
  references,
  onReferences,
  onItem,
  children,
}: {
  references: ReferencesDraft;
  onReferences: UpdateReferences;
  onItem?: UpdateItem;
  children?: ReactNode;
}) {
  return (
    <ReferencesIntake references={references} onReferences={onReferences} onItem={onItem}>
      {children}
    </ReferencesIntake>
  );
}
