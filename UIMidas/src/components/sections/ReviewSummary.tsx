import type { ReactNode } from "react";
import { buildClientReview, type ReviewFact, type ReviewGroup, type ReviewSectionView } from "../../lib/reviewModel";
import type { ClientJobDraft, SectionId } from "../../types/draft";

export function ReviewSummary({
  draft,
  activeItemId,
  onEdit,
}: {
  draft: ClientJobDraft;
  activeItemId: string;
  onEdit: (section: SectionId, itemId?: string) => void;
}) {
  const review = buildClientReview(draft, activeItemId);
  const severalItems = review.sections.find((section) => section.id === "item")?.groups.length ?? 0;

  return (
    <div className="summary">
      {review.sections.map((section) => (
        <SummaryCard
          key={section.id}
          section={section}
          quiet={section.id === "advanced"}
          onEdit={() => onEdit(section.id)}
        >
          {section.groups.map((group, index) => (
            <ReviewGroupView
              key={group.itemId ?? `${section.id}-${index}`}
              group={group}
              allowItemEdit={severalItems > 1 && group.itemId !== null && (section.id === "item" || section.id === "references" || section.id === "scope")}
              onEditItem={group.itemId ? () => onEdit(section.id, group.itemId ?? undefined) : undefined}
            />
          ))}
        </SummaryCard>
      ))}
    </div>
  );
}

function SummaryCard({
  section,
  quiet,
  onEdit,
  children,
}: {
  section: ReviewSectionView;
  quiet: boolean;
  onEdit: () => void;
  children: ReactNode;
}) {
  return (
    <section className={quiet ? "summary__card summary__card--quiet" : "summary__card"} aria-labelledby={`review-${section.id}`}>
      <div className="summary__head">
        <h2 id={`review-${section.id}`}>{section.title}</h2>
        <button type="button" className="btn btn--ghost" aria-label={`Edit ${section.title.toLowerCase()}`} onClick={onEdit}>
          Edit
        </button>
      </div>
      {children}
    </section>
  );
}

function ReviewGroupView({
  group,
  allowItemEdit,
  onEditItem,
}: {
  group: ReviewGroup;
  allowItemEdit: boolean;
  onEditItem?: () => void;
}) {
  const labeled = group.facts.filter((fact) => fact.label);
  const prose = group.facts.filter((fact) => !fact.label);

  return (
    <div className="summary__group">
      {group.title ? (
        <div className="summary__group-head">
          <h3>{group.title}</h3>
          {allowItemEdit && onEditItem ? (
            <button type="button" className="btn btn--ghost" aria-label={`Edit ${group.title}`} onClick={onEditItem}>
              Edit
            </button>
          ) : null}
        </div>
      ) : null}
      {prose.map((fact, index) => (
        <FactLine key={`${fact.text}-${index}`} fact={fact} />
      ))}
      {labeled.length > 0 ? (
        <dl>
          {labeled.map((fact) => (
            <div className="fact" key={`${fact.label}-${fact.text}`}>
              <dt>{fact.label}</dt>
              <dd>{fact.text}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {group.outputs.map((output, index) => (
        <div className="summary__output" key={`${output.name}-${index}`}>
          <h3>{output.name}</h3>
          {output.details.length > 0 ? (
            <dl>
              {output.details.map((detail) => (
                <div className="fact" key={`${output.name}-${detail.label}`}>
                  <dt>{detail.label}</dt>
                  <dd>{detail.text}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function FactLine({ fact }: { fact: ReviewFact }) {
  return <p className={fact.tone === "kicker" ? "summary__kicker" : undefined}>{fact.text}</p>;
}
