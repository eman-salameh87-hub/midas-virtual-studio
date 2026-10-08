import { GlobalWindow } from "happy-dom";
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { MidasProductDialog, MidasSelectionList } from "./components/references/MidasProductPicker";
import { prepareProjectSubmission } from "./contract/submitPreparedProject";
import { loadMidasCatalogue, searchMidasProducts, type MidasProduct } from "./data/midasCatalogue";
import { projectReviewFacts } from "./lib/projectBrief";
import { applyMidasSelection, selectionFromProduct } from "./lib/midasSelection";
import { normalizeDraft } from "./normalization/normalizeDraft";
import { createEmptyBriefItem, createEmptyDraft } from "./state/emptyDraft";
import type { ReferencesDraft } from "./types/draft";

const dom = new GlobalWindow({ url: "http://localhost/" });
Object.assign(globalThis, {
  window: dom,
  document: dom.document,
  HTMLElement: dom.HTMLElement,
  Element: dom.Element,
  Node: dom.Node,
  SVGElement: dom.SVGElement,
  DocumentFragment: dom.DocumentFragment,
  MutationObserver: dom.MutationObserver,
  getComputedStyle: dom.getComputedStyle.bind(dom),
  requestAnimationFrame: dom.requestAnimationFrame.bind(dom),
  cancelAnimationFrame: dom.cancelAnimationFrame.bind(dom),
  URL: dom.URL,
  IS_REACT_ACT_ENVIRONMENT: true,
});

const { createElement, useState } = await import("react");
const { createRoot } = await import("react-dom/client");
const { act } = await import("react");
const { ClientFirstPage } = await import("./pages/ClientFirstPage");

const catalogue = await loadMidasCatalogue();
const sidewinder = catalogue.find((product) => product.sku === "111675");
const abali = catalogue.find((product) => product.sku === "165931");
assert.ok(sidewinder);
assert.ok(abali);

async function mount(node: ReturnType<typeof createElement>) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(node);
  });
  return {
    host,
    async unmount() {
      await act(async () => {
        root.unmount();
      });
      host.remove();
    },
  };
}

function buttonNamed(host: ParentNode, name: string) {
  const found = [...host.querySelectorAll("button")].find((button) => {
    const label = `${button.getAttribute("aria-label") ?? ""} ${button.textContent ?? ""}`.replace(/\s+/g, " ");
    return label.includes(name);
  });
  assert.ok(found, `Missing button ${name}`);
  return found;
}

async function click(host: ParentNode, name: string) {
  await act(async () => {
    buttonNamed(host, name).dispatchEvent(new dom.MouseEvent("click", { bubbles: true }) as unknown as MouseEvent);
  });
}

async function typeSearch(host: ParentNode, value: string) {
  const input = host.querySelector("#midas-search");
  assert.ok(input);
  const setter = Object.getOwnPropertyDescriptor(dom.HTMLInputElement.prototype, "value")?.set;
  await act(async () => {
    setter?.call(input, value);
    input.dispatchEvent(new dom.Event("input", { bubbles: true }) as unknown as Event);
  });
}

function emptyReferences(): ReferencesDraft {
  return createEmptyBriefItem().references;
}

function PickerHarness({
  sink,
  products,
  status = "ready",
  startOpen = true,
}: {
  sink: { references: ReferencesDraft };
  products: readonly MidasProduct[];
  status?: "loading" | "ready" | "error";
  startOpen?: boolean;
}) {
  const [references, setReferences] = useState(sink.references);
  const [open, setOpen] = useState(startOpen);
  sink.references = references;
  return createElement(
    "div",
    null,
    createElement("button", { type: "button", onClick: () => setOpen(true) }, "Choose from Midas"),
    createElement(MidasProductDialog, {
      open,
      products,
      status,
      references,
      onClose: () => setOpen(false),
      onCommit: setReferences,
    }),
    createElement(MidasSelectionList, { references, products, onReferences: setReferences }),
  );
}

describe("Midas product selector", () => {
  it("loads the scraped catalogue and searches by name and sku", () => {
    assert.ok(catalogue.length > 1000);
    assert.equal(sidewinder.name, "SIDEWINDER CHAIR - BROWN");
    assert.match(sidewinder.productUrl, /^https:\/\/midasfurniture\.com\/qtr_en\//);
    assert.equal(sidewinder.productUrl, sidewinder.sourceUrl);
    assert.equal(catalogue.some((product) => product.id === "midas-white-sweep"), false);
    assert.deepEqual(searchMidasProducts(catalogue, "sidewinder chair").map((product) => product.sku).includes("111675"), true);
    assert.deepEqual(searchMidasProducts(catalogue, "111675").some((product) => product.sku === "111675"), true);
    assert.equal(searchMidasProducts(catalogue, "zzzz-not-a-real-product-qqq").length, 0);
  });

  it("selects several products, keeps them across search, and commits them", async () => {
    const sink = { references: emptyReferences() };
    const view = await mount(createElement(PickerHarness, { sink, products: catalogue }));
    await typeSearch(view.host, "111675");
    assert.match(view.host.textContent ?? "", /SIDEWINDER CHAIR - BROWN/);
    assert.match(view.host.textContent ?? "", /SKU 111675/);
    const source = view.host.querySelector("a");
    assert.equal(source?.getAttribute("href"), sidewinder.productUrl);
    await click(view.host, "Add reference +");
    assert.match(buttonNamed(view.host, "Selected").textContent ?? "", /Selected/);
    assert.match(view.host.textContent ?? "", /Use 1 selection →/);
    await typeSearch(view.host, "165931");
    assert.equal((view.host.textContent ?? "").includes("SIDEWINDER CHAIR - BROWN"), false);
    await click(view.host, "Add reference +");
    assert.match(view.host.textContent ?? "", /Use 2 selections →/);
    await typeSearch(view.host, "111675");
    assert.match(view.host.textContent ?? "", /Selected/);
    await click(view.host, "Use 2 selections");
    assert.equal(view.host.querySelector("[role='dialog']"), null);
    assert.match(view.host.textContent ?? "", /Your Midas selections/);
    assert.match(view.host.textContent ?? "", /SIDEWINDER CHAIR - BROWN/);
    assert.match(view.host.textContent ?? "", /ABALI DINING TABLE- WHITE/);
    assert.equal(sink.references.items.length, 2);
    assert.ok(sink.references.items.every((item) => item.type === "midas" && item.source === "midas_library" && item.role === "midas_reference"));
    assert.deepEqual(
      sink.references.items.map((item) => item.asset?.libraryKey).sort(),
      ["111675", "165931"],
    );
    await view.unmount();
  });

  it("changes hero and secondary, removes a product, and restores selection when reopened", async () => {
    const sink = { references: emptyReferences() };
    const view = await mount(createElement(PickerHarness, { sink, products: [sidewinder, abali] }));
    await click(view.host, "Add reference +");
    await typeSearch(view.host, "165931");
    await click(view.host, "Add reference +");
    await click(view.host, "Use 2 selections");
    const role = view.host.querySelector("select");
    assert.ok(role);
    await act(async () => {
      role.value = "hero";
      role.dispatchEvent(new dom.Event("change", { bubbles: true }) as unknown as Event);
    });
    const hero = sink.references.items.find((item) => item.asset?.libraryKey === sidewinder.sku);
    assert.equal(hero?.relationship, "same_product");
    assert.equal(hero?.productGroupId, sink.references.primaryProductGroupId);
    await click(view.host, "Remove ABALI");
    assert.equal(sink.references.items.length, 1);
    await click(view.host, "Choose from Midas");
    assert.equal(view.host.querySelector("[data-selected='true']")?.textContent?.includes("SIDEWINDER"), true);
    await click(view.host, "Add reference +");
    await click(view.host, "Close");
    assert.equal(sink.references.items.length, 1);
    await view.unmount();
  });

  it("shows an empty search and a catalogue failure without fake products", async () => {
    const sink = { references: emptyReferences() };
    const view = await mount(createElement(PickerHarness, { sink, products: catalogue }));
    await typeSearch(view.host, "zzzz-not-a-real-product-qqq");
    assert.match(view.host.textContent ?? "", /No products found\./);
    assert.equal((view.host.textContent ?? "").includes("Studio white sweep"), false);
    await view.unmount();
    const empty = renderToStaticMarkup(
      <MidasProductDialog
        open
        products={catalogue}
        status="ready"
        references={emptyReferences()}
        onClose={() => {}}
        onCommit={() => {}}
      />,
    );
    assert.equal(empty.includes("Studio white sweep"), false);
    const failed = renderToStaticMarkup(
      <MidasProductDialog open products={[]} status="error" references={emptyReferences()} onClose={() => {}} onCommit={() => {}} />,
    );
    assert.match(failed, /The Midas catalogue is unavailable/);
    assert.equal(failed.includes("ABALI"), false);
    assert.equal(failed.includes("Studio white sweep"), false);
  });

  it("opens the local catalogue immediately without a refresh request", async () => {
    const calls: string[] = [];
    const previous = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      calls.push(String(input));
      throw new Error("unexpected network");
    }) as typeof fetch;
    try {
      const view = await mount(createElement(ClientFirstPage));
      await click(view.host, "Projects");
      await click(view.host, "Continue to the item");
      await click(view.host, "Choose from Midas");
      assert.ok(view.host.querySelector("#midas-search"));
      assert.equal((view.host.textContent ?? "").includes("Loading Midas products"), false);
      assert.match(view.host.textContent ?? "", /ABALI DINING TABLE- WHITE/);
      assert.equal(calls.some((url) => url.includes("/api/midas/catalogue") || url.includes("midasfurniture.com/graphql")), false);
      await view.unmount();
    } finally {
      globalThis.fetch = previous;
    }
  });

  it("keeps Projects and Manual selections apart and carries them into review and submission", async () => {
    const calls: string[] = [];
    const previous = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      calls.push(String(input));
      return previous(input);
    }) as typeof fetch;
    try {
    const view = await mount(createElement(ClientFirstPage));
    await click(view.host, "Projects");
    await click(view.host, "Continue to the item");
    await click(view.host, "Choose from Midas");
    for (let attempt = 0; attempt < 20 && !view.host.querySelector("#midas-search"); attempt += 1) {
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 20));
      });
    }
    assert.ok(view.host.querySelector("#midas-search"));
    await typeSearch(view.host, "111675");
    await click(view.host, "Add reference +");
    await click(view.host, "Use 1 selection");
    assert.match(view.host.textContent ?? "", /SIDEWINDER CHAIR - BROWN/);
    await click(view.host, "Manual");
    await click(view.host, "Batch");
    await click(view.host, "Continue to the item");
    assert.equal((view.host.textContent ?? "").includes("SIDEWINDER CHAIR - BROWN"), false);
    await click(view.host, "Choose from Midas");
    for (let attempt = 0; attempt < 20 && !view.host.querySelector("#midas-search"); attempt += 1) {
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 20));
      });
    }
    await typeSearch(view.host, "165931");
    await click(view.host, "Add reference +");
    await click(view.host, "Use 1 selection");
    assert.match(view.host.textContent ?? "", /ABALI DINING TABLE- WHITE/);
    assert.equal((view.host.textContent ?? "").includes("SIDEWINDER CHAIR - BROWN"), false);
    await view.unmount();

    const references = applyMidasSelection(emptyReferences(), [selectionFromProduct(sidewinder, "secondary")]);
    const review = JSON.stringify(projectReviewFacts({
      start: "product_or_collection",
      existingRoom: "",
      newStyledSpace: "",
      item: createEmptyBriefItem().item,
      references,
      outputs: [],
    }));
    assert.match(review, /SIDEWINDER CHAIR - BROWN/);
    const prepared = prepareProjectSubmission({
      start: "product_or_collection",
      existingRoom: "",
      newStyledSpace: "",
      item: { categoryState: "automatic_unknown", department: null, category: null, subcategory: null },
      references,
      outputs: [{ id: "out", concept: "lifestyle", otherLabel: "", variationAspects: [] }],
    }, "key");
    const submitted = prepared.submission.references[0];
    assert.equal(submitted?.evidence?.fileName, "SIDEWINDER CHAIR - BROWN");
    assert.equal(submitted?.evidence?.libraryKey, "111675");
    assert.equal(submitted?.evidence?.mediaKind, "image");
    assert.equal(submitted?.evidence?.sizeBytes, null);
    assert.equal(submitted?.role, "midas_reference");
    assert.equal(submitted?.relationship, "supporting_context");
    assert.equal(JSON.stringify(prepared.submission).includes(sidewinder.productUrl), false);

    const draft = createEmptyDraft();
    draft.items[0].references = applyMidasSelection(draft.items[0].references, [selectionFromProduct(abali, "hero")]);
    const normalized = normalizeDraft(draft).items[0]?.references[0];
    assert.equal(normalized?.evidence?.fileName, "ABALI DINING TABLE- WHITE");
    assert.equal(normalized?.evidence?.libraryKey, "165931");
    assert.equal(normalized?.relationship, "same_product");
    assert.equal(normalized?.productGroupId, draft.items[0].references.primaryProductGroupId);
    assert.equal(calls.some((url) => url.includes("/api/midas/catalogue") || url.includes("midasfurniture.com/graphql")), false);
    } finally {
      globalThis.fetch = previous;
    }
  });
});
