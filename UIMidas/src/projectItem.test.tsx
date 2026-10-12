import { GlobalWindow } from "happy-dom";
import assert from "node:assert/strict";
import { after, describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { ItemSection } from "./components/sections/ItemSection";
import { ProjectItemSection } from "./components/sections/ProjectItemSection";
import { DraftProvider } from "./state/DraftProvider";
import { createEmptyBriefItem } from "./state/emptyDraft";
import type { ReferenceIntakeResult } from "./adapters/analyzeReferenceIntake";
import { installAnalyzeStub } from "./testAnalyzeStub";

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

type ItemSink = {
  item: ReturnType<typeof createEmptyBriefItem>["item"];
  references: ReturnType<typeof createEmptyBriefItem>["references"];
};

function emptyPiece() {
  const created = createEmptyBriefItem();
  return { item: created.item, references: created.references };
}

function ProjectItemHarness({ sink }: { sink: ItemSink }) {
  const initial = emptyPiece();
  const [item, setItem] = useState(initial.item);
  const [references, setReferences] = useState(initial.references);
  sink.item = item;
  sink.references = references;
  return createElement(ProjectItemSection, {
    item,
    references,
    onItem: setItem,
    onReferences: setReferences,
    onBack: () => {},
    onContinue: () => {},
  });
}

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
  const found = [...host.querySelectorAll("button")].find((button) => button.textContent?.replace(/\s+/g, " ").includes(name));
  assert.ok(found, `Missing button ${name}`);
  return found;
}

async function click(host: ParentNode, name: string) {
  const button = buttonNamed(host, name);
  await act(async () => {
    button.dispatchEvent(new dom.MouseEvent("click", { bubbles: true }) as unknown as MouseEvent);
  });
}

function fieldSelect(host: ParentNode, label: string) {
  const found = [...host.querySelectorAll("label")].find((entry) => entry.querySelector("span")?.textContent === label);
  const select = found?.querySelector("select");
  assert.ok(select, `Missing select ${label}`);
  return select;
}

async function choose(select: HTMLSelectElement, value: string) {
  await act(async () => {
    select.value = value;
    select.dispatchEvent(new dom.Event("change", { bubbles: true }) as unknown as Event);
  });
}

async function addFiles(host: ParentNode, files: File[]) {
  const input = host.querySelector('input[type="file"]') as HTMLInputElement | null;
  assert.ok(input);
  const transfer = new dom.DataTransfer();
  for (const file of files) transfer.items.add(file as unknown as InstanceType<typeof dom.File>);
  await act(async () => {
    input.files = transfer.files as unknown as FileList;
    input.dispatchEvent(new dom.Event("change", { bubbles: true }) as unknown as Event);
  });
}

function imageFile(name: string): File {
  return new dom.File([Uint8Array.from([1, 2, 3, 4])], name, { type: "image/jpeg" }) as unknown as File;
}

describe("project flow step 02", () => {
  const restoreFetch = installAnalyzeStub();
  after(restoreFetch);
  it("renders the same item screen as Manual", () => {
    const piece = emptyPiece();
    const manual = renderToStaticMarkup(
      createElement(DraftProvider, null, createElement(ItemSection, { onBack: () => {}, onContinue: () => {} })),
    );
    const projects = renderToStaticMarkup(
      createElement(ProjectItemSection, {
        item: piece.item,
        references: piece.references,
        onItem: () => {},
        onReferences: () => {},
        onBack: () => {},
        onContinue: () => {},
      }),
    );
    assert.equal(projects.includes("More options"), false);
    assert.match(manual, /More options/);
    assert.equal(projects, manual.replace('<details class="more-options"><summary>More options</summary></details>', ""));
  });

  it("opens Projects The Item, then Projects Scope", async () => {
    const view = await mount(createElement(ClientFirstPage));
    await click(view.host, "Projects");
    assert.match(view.host.querySelector("nav")?.textContent ?? "", /01\s*Project/);
    assert.match(view.host.querySelector("nav")?.textContent ?? "", /02\s*The Item/);
    assert.match(view.host.querySelector("nav")?.textContent ?? "", /03\s*Scope/);
    await click(view.host, "Continue to the item");
    assert.match(view.host.textContent ?? "", /Add your item\./);
    assert.match(view.host.querySelector("[aria-current='step']")?.textContent ?? "", /The Item/);
    assert.equal(view.host.textContent?.includes("What would you like to create?"), false);
    await click(view.host, "Choose the outcomes");
    assert.match(view.host.querySelector("[aria-current='step']")?.textContent ?? "", /Scope/);
    assert.match(view.host.textContent ?? "", /What would you like to create\?/);
    assert.equal(view.host.textContent?.includes("Add your item."), false);
    assert.equal(view.host.textContent?.includes("View & delivery"), false);
    assert.equal(view.host.textContent?.includes("Where would you like to begin?"), false);
    await view.unmount();
  });

  it("keeps Manual navigation on The Job, The Item, and Scope", async () => {
    const view = await mount(createElement(ClientFirstPage));
    assert.match(view.host.textContent ?? "", /What would you like to do\?/);
    await click(view.host, "Batch");
    await click(view.host, "Continue to the item");
    assert.match(view.host.textContent ?? "", /Add your item\./);
    assert.match(view.host.querySelector("[aria-current='step']")?.textContent ?? "", /The Item/);
    await click(view.host, "Choose the outcomes");
    assert.match(view.host.textContent ?? "", /What would you like to create\?/);
    assert.match(view.host.querySelector("[aria-current='step']")?.textContent ?? "", /Scope/);
    await view.unmount();
  });

  it("keeps Projects item choices apart from Manual item choices", async () => {
    const view = await mount(createElement(ClientFirstPage));
    await click(view.host, "Projects");
    await click(view.host, "Continue to the item");
    await choose(fieldSelect(view.host, "Department"), "home-furniture");
    await choose(fieldSelect(view.host, "Category"), "home-furniture/living-rooms");
    await click(view.host, "Manual");
    await click(view.host, "Batch");
    await click(view.host, "Continue to the item");
    assert.equal(fieldSelect(view.host, "Department").value, "");
    await choose(fieldSelect(view.host, "Department"), "office-furniture");
    await click(view.host, "Projects");
    assert.equal(fieldSelect(view.host, "Department").value, "home-furniture");
    assert.equal(fieldSelect(view.host, "Category").value, "home-furniture/living-rooms");
    await click(view.host, "Manual");
    assert.equal(fieldSelect(view.host, "Department").value, "office-furniture");
    await view.unmount();
  });

  it("selects department, category, sub-category, and Automatic from references", async () => {
    const sink: ItemSink = emptyPiece();
    const view = await mount(createElement(ProjectItemHarness, { sink }));
    const department = fieldSelect(view.host, "Department");
    assert.equal(department.value, "");
    assert.equal(department.disabled, false);
    await choose(department, "home-furniture");
    assert.equal(sink.item.department, "home-furniture");
    assert.equal(sink.item.categoryState, "specified");
    const category = fieldSelect(view.host, "Category");
    assert.match(category.innerHTML, /Living Rooms/);
    await choose(category, "home-furniture/living-rooms");
    const subcategory = fieldSelect(view.host, "Sub-category");
    assert.match(subcategory.innerHTML, /Sofas \/ Sectional Sofas/);
    await choose(subcategory, "home-furniture/living-rooms/sofa/sectional-sofa");
    assert.equal(sink.item.subcategory, "home-furniture/living-rooms/sofa/sectional-sofa");
    await choose(fieldSelect(view.host, "Department"), "");
    assert.equal(sink.item.categoryState, "automatic_unknown");
    assert.equal(sink.item.department, null);
    assert.equal(sink.item.category, null);
    assert.equal(sink.item.subcategory, null);
    assert.equal(fieldSelect(view.host, "Department").disabled, true);
    assert.equal(fieldSelect(view.host, "Category").disabled, true);
    assert.equal(fieldSelect(view.host, "Sub-category").disabled, true);
    await view.unmount();
  });

  it("uploads a product image, groups it, and keeps a room reference separate", async () => {
    const sink: ItemSink = emptyPiece();
    const view = await mount(createElement(ProjectItemHarness, { sink }));
    await addFiles(view.host, [imageFile("sofa.jpg"), imageFile("sofa-side.jpg")]);
    assert.match(view.host.textContent ?? "", /sofa\.jpg/);
    assert.match(view.host.textContent ?? "", /sofa-side\.jpg/);
    assert.match(view.host.textContent ?? "", /Product \/ vendor reference/);
    assert.equal(view.host.querySelectorAll(".file-list .select-field--type").length, 2);
    const groupId = sink.references.primaryProductGroupId;
    assert.equal(sink.references.items.length, 2);
    assert.ok(sink.references.items.every((entry) => entry.productGroupId === groupId && entry.relationship === "same_product"));
    await choose(fieldSelect(view.host, "What are you adding?"), "room_image");
    await addFiles(view.host, [imageFile("room.jpg")]);
    const room = sink.references.items.find((entry) => entry.asset?.fileName === "room.jpg");
    assert.equal(room?.relationship, "supporting_context");
    assert.equal(room?.productGroupId, null);
    assert.match(view.host.textContent ?? "", /Room \/ target space/);
    await view.unmount();
  });

  it("populates department, category, and sub-category from a mocked classify response", async () => {
    const restore = installAnalyzeStub({
      status: "accepted",
      relevant: true,
      needs_confirmation: false,
      suggested_reference_type: "Product / vendor reference" as ReferenceIntakeResult["suggested_reference_type"],
      department: "Home Furniture",
      category: "Living Rooms",
      subcategory: "Sofas",
      message: "Classified as a sofa product photograph.",
    });
    try {
      const view = await mount(
        createElement(DraftProvider, null, createElement(ItemSection, { onBack: () => {}, onContinue: () => {} })),
      );
      await addFiles(view.host, [imageFile("sofa.jpg")]);
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 20));
      });
      await act(async () => {
        await Promise.resolve();
      });
      assert.equal(fieldSelect(view.host, "Department").value, "home-furniture");
      assert.equal(fieldSelect(view.host, "Category").value, "home-furniture/living-rooms");
      assert.equal(fieldSelect(view.host, "Sub-category").value, "home-furniture/living-rooms/sofa");
      assert.equal(fieldSelect(view.host, "Department").disabled, false);
      assert.match(view.host.textContent ?? "", /Classified as a sofa product photograph/);
      const typeLabels = [...view.host.querySelectorAll("label")].filter(
        (entry) => entry.querySelector("span")?.textContent === "Reference type",
      );
      const addLabels = [...view.host.querySelectorAll("label")].filter(
        (entry) => entry.querySelector("span")?.textContent === "What are you adding?",
      );
      assert.equal(typeLabels.length, 1);
      assert.equal(addLabels.length, 0);
      await view.unmount();
    } finally {
      restore();
    }
  });

  it("reports file errors for an empty upload", async () => {
    const sink: ItemSink = emptyPiece();
    const view = await mount(createElement(ProjectItemHarness, { sink }));
    await choose(fieldSelect(view.host, "What are you adding?"), "product");
    await addFiles(view.host, [new dom.File([], "empty.jpg", { type: "image/jpeg" }) as unknown as File]);
    assert.match(view.host.textContent ?? "", /This file is empty\./);
    assert.equal(sink.references.items.find((entry) => entry.asset?.fileName === "empty.jpg")?.localStatus, "error");
    await addFiles(view.host, [imageFile("ready.jpg")]);
    await act(async () => {
      await Promise.resolve();
    });
    const ready = sink.references.items.find((entry) => entry.asset?.fileName === "ready.jpg");
    assert.equal(ready?.localStatus, "ready");
    await view.unmount();
  });
});
