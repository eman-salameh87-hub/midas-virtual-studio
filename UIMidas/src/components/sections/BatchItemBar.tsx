import { itemDisplayName } from "../../lib/itemLabel";
import { isBatchJob } from "../../lib/requestItems";
import { useBatchItems, useClientJobDraft } from "../../state/DraftProvider";
import { ToggleChip } from "../ui/controls";

export function BatchItemBar({
  addLabel = "Add item",
  note = "Each item keeps its own references and requested package.",
}: {
  addLabel?: string;
  note?: string;
}) {
  const draft = useClientJobDraft();
  const { items, activeItemId, setActiveItemId, addItem, removeItem } = useBatchItems();
  if (!isBatchJob(draft)) return null;

  return (
    <div className="batch-bar">
      <p className="note">{note}</p>
      <div className="chip-row" role="group" aria-label="Items in this batch">
        {items.map((item, index) => (
          <ToggleChip key={item.id} pressed={item.id === activeItemId} onClick={() => setActiveItemId(item.id)}>
            {itemDisplayName(item, index)}
          </ToggleChip>
        ))}
        <button type="button" className="btn btn--secondary" onClick={addItem}>
          {addLabel}
        </button>
      </div>
      {items.length > 1 ? (
        <button type="button" className="btn btn--ghost align-start" onClick={() => removeItem(activeItemId)}>
          Remove this item
        </button>
      ) : null}
    </div>
  );
}
