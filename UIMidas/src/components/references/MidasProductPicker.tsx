import { useEffect, useMemo, useRef, useState } from "react";
import { searchMidasProducts, type MidasProduct } from "../../data/midasCatalogue";
import {
  applyMidasSelection,
  isMidasReference,
  midasRole,
  selectionFromProduct,
  type MidasSelection,
} from "../../lib/midasSelection";
import type { ReferencesDraft, SingleItemRole } from "../../types/draft";
import { StudioSelect } from "../ui/StudioSelect";

const pageSize = 24;

export function useMidasCatalogue(load: () => Promise<MidasProduct[]>) {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [products, setProducts] = useState<MidasProduct[]>([]);

  useEffect(() => {
    let live = true;
    load().then(
      (next) => {
        if (!live) return;
        setProducts(next);
        setStatus("ready");
      },
      () => {
        if (!live) return;
        setProducts([]);
        setStatus("error");
      },
    );
    return () => {
      live = false;
    };
  }, [load]);

  return { status, products };
}

export function MidasProductDialog({
  open,
  products,
  status,
  references,
  onClose,
  onCommit,
}: {
  open: boolean;
  products: readonly MidasProduct[];
  status: "loading" | "ready" | "error";
  references: ReferencesDraft;
  onClose: () => void;
  onCommit: (next: ReferencesDraft) => void;
}) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [draft, setDraft] = useState<Map<string, SingleItemRole>>(() => new Map());
  const wasOpen = useRef(false);

  useEffect(() => {
    if (open && !wasOpen.current) {
      setQuery("");
      setPage(0);
      setDraft(rolesFromReferences(references));
    }
    wasOpen.current = open;
  }, [open, references]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const matches = useMemo(() => searchMidasProducts(products, query), [products, query]);
  const pages = Math.max(1, Math.ceil(matches.length / pageSize));
  const currentPage = Math.min(page, pages - 1);
  const visible = matches.slice(currentPage * pageSize, currentPage * pageSize + pageSize);
  const count = draft.size;

  if (!open) return null;

  function toggle(product: MidasProduct) {
    setDraft((current) => {
      const next = new Map(current);
      if (next.has(product.id)) next.delete(product.id);
      else {
        const hasHero = [...current.values()].includes("hero");
        next.set(product.id, hasHero ? "secondary" : "hero");
      }
      return next;
    });
  }

  function confirm() {
    const selected: MidasSelection[] = [];
    for (const [id, role] of draft) {
      const product = products.find((item) => item.id === id);
      if (product) {
        selected.push(selectionFromProduct(product, role));
        continue;
      }
      const existing = references.items.find((item) => isMidasReference(item) && item.asset?.libraryKey === id);
      if (!existing?.asset) continue;
      selected.push({ id, name: existing.asset.fileName, imageUrl: existing.asset.localPreviewUrl, role });
    }
    onCommit(applyMidasSelection(references, selected));
    onClose();
  }

  return (
    <div className="midas-modal" onMouseDown={onClose}>
      <div
        className="midas-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="midas-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="midas-dialog__head">
          <div>
            <h2 id="midas-dialog-title">Midas product references</h2>
            <p>Search the Midas catalogue and choose the products to use as references.</p>
          </div>
          <button type="button" className="midas-dialog__close" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="midas-dialog__body">
          <label className="select-field" htmlFor="midas-search">
            <span>Search products</span>
            <input
              id="midas-search"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setPage(0);
              }}
            />
          </label>
          {status === "loading" ? <p className="midas-note">Loading Midas products…</p> : null}
          {status === "error" ? <p className="midas-note">The Midas catalogue is unavailable.</p> : null}
          {status === "ready" && matches.length === 0 ? <p className="midas-note">No products found.</p> : null}
          {status === "ready" && visible.length > 0 ? (
            <div className="midas-grid">
              {visible.map((product) => {
                const selected = draft.has(product.id);
                return (
                  <article key={product.id} className="midas-card" data-selected={selected ? "true" : "false"}>
                    {product.imageUrl ? <img src={product.imageUrl} alt="" /> : <span className="midas-card__fallback">Midas</span>}
                    <div className="midas-card__body">
                      <h3>{product.name}</h3>
                      <p>SKU {product.sku}</p>
                      <a href={product.productUrl} target="_blank" rel="noopener noreferrer">
                        View Midas source ↗
                      </a>
                      <button
                        type="button"
                        aria-pressed={selected}
                        onClick={() => toggle(product)}
                      >
                        {selected ? "Selected" : "Add reference +"}
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : null}
          {status === "ready" && matches.length > pageSize ? (
            <div className="midas-pager">
              <button type="button" disabled={currentPage === 0} onClick={() => setPage((value) => Math.max(0, value - 1))}>
                Previous
              </button>
              <span>
                {currentPage + 1} / {pages}
              </span>
              <button type="button" disabled={currentPage >= pages - 1} onClick={() => setPage((value) => value + 1)}>
                Next
              </button>
            </div>
          ) : null}
        </div>
        <footer className="midas-dialog__foot">
          <button type="button" className="btn btn--primary" onClick={confirm}>
            {selectionLabel(count)}
          </button>
        </footer>
      </div>
    </div>
  );
}

export function MidasSelectionList({
  references,
  products,
  onReferences,
}: {
  references: ReferencesDraft;
  products: readonly MidasProduct[];
  onReferences: (next: ReferencesDraft) => void;
}) {
  const selected = references.items.filter(isMidasReference);
  if (selected.length === 0) return null;
  const byId = new Map(products.map((product) => [product.id, product]));

  function setRole(id: string, role: SingleItemRole) {
    onReferences(
      applyMidasSelection(
        references,
        selected.map((reference) => {
          const key = reference.asset?.libraryKey ?? reference.id;
          const product = byId.get(key);
          return {
            id: key,
            name: product?.name ?? reference.asset?.fileName ?? key,
            imageUrl: product?.imageUrl ?? reference.asset?.localPreviewUrl ?? null,
            role: key === id ? role : midasRole(reference),
          };
        }),
      ),
    );
  }

  function remove(id: string) {
    onReferences({
      ...references,
      items: references.items.filter((reference) => reference.id !== id),
    });
  }

  return (
    <section className="midas-picks">
      <ul className="midas-picks__grid">
        {selected.map((reference) => {
          const key = reference.asset?.libraryKey ?? "";
          const product = byId.get(key);
          const name = reference.asset?.fileName ?? product?.name ?? "Midas reference";
          const href = product?.productUrl;
          const image = product?.imageUrl ?? reference.asset?.localPreviewUrl;
          return (
            <li key={reference.id} className="midas-pick pick-card">
              <div className="pick-card__media">
                {image ? <img src={image} alt="" /> : <span className="midas-card__fallback">Midas</span>}
                <button type="button" className="pick-card__remove" aria-label={`Remove ${name}`} onClick={() => remove(reference.id)}>
                  <span aria-hidden="true">×</span>
                </button>
              </div>
              <div className="pick-card__copy">
                <span className="pick-card__origin">Midas</span>
                <strong>{name}</strong>
                {href ? (
                  <a href={href} target="_blank" rel="noopener noreferrer">
                    Midas source <span aria-hidden="true">↗</span>
                  </a>
                ) : null}
              </div>
              <StudioSelect
                aria-label={`Role for ${name}`}
                value={midasRole(reference)}
                options={[
                  { value: "hero", label: "Hero" },
                  { value: "secondary", label: "Secondary" },
                ]}
                onChange={(role) => setRole(key, role as SingleItemRole)}
              />
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function rolesFromReferences(references: ReferencesDraft): Map<string, SingleItemRole> {
  const roles = new Map<string, SingleItemRole>();
  for (const reference of references.items) {
    const key = reference.asset?.libraryKey;
    if (isMidasReference(reference) && key) roles.set(key, midasRole(reference));
  }
  return roles;
}

function selectionLabel(count: number): string {
  return `Use ${count} ${count === 1 ? "selection" : "selections"} →`;
}
