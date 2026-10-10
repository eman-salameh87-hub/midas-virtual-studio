import { GlobalWindow } from "happy-dom";
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { SavedBriefChoices } from "./components/sections/JobSection";
import { jobKindOptions } from "./config/options";
import { primaryFlow } from "./flow";
import { buildClientReview } from "./lib/reviewModel";
import { normalizeDraft } from "./normalization/normalizeDraft";
import { createEmptyDraft } from "./state/emptyDraft";

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

const { createElement } = await import("react");
const { createRoot } = await import("react-dom/client");
const { act } = await import("react");
const { ClientFirstPage } = await import("./pages/ClientFirstPage");

const editSupport = jobKindOptions.find((option) => option.value === "edit")?.description ?? "";
const emptySavedProjects = "No saved projects are currently available. Select New item to continue.";
const mockSavedLabels = ["Lounge chair", "Ceramic table lamp", "Linen sofa"];

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

describe("manual job edit state", () => {
  it("shows the existing Edit supporting text and start choices", async () => {
    const view = await mount(createElement(ClientFirstPage));
    await click(view.host, "Edit");
    assert.match(view.host.textContent ?? "", new RegExp(editSupport));
    assert.equal(editSupport, "Change an existing piece of work.");
    assert.match(view.host.textContent ?? "", /Start from/);
    assert.ok(buttonNamed(view.host, "Choose from saving"));
    assert.ok(buttonNamed(view.host, "New item"));
    assert.equal((view.host.textContent ?? "").includes("Use an existing Midas item"), false);
    assert.equal((view.host.textContent ?? "").includes("Upload an item"), false);
    await view.unmount();
  });

  it("shows the empty saved-project message and hides the mock briefs", async () => {
    const view = await mount(createElement(ClientFirstPage));
    await click(view.host, "Edit");
    await click(view.host, "Choose from saving");
    const text = view.host.textContent ?? "";
    assert.match(text, /No saved projects are currently available\. Select New item to continue\./);
    assert.ok(buttonNamed(view.host, "Choose from saving"));
    assert.ok(buttonNamed(view.host, "New item"));
    for (const label of mockSavedLabels) assert.equal(text.includes(label), false);
    await view.unmount();
  });

  it("shows the formal empty state when no saved projects are supplied", () => {
    const html = renderToStaticMarkup(<SavedBriefChoices briefs={[]} selectedId={null} onSelect={() => {}} />);
    assert.match(html, /No saved projects are currently available\. Select New item to continue\./);
    for (const label of mockSavedLabels) assert.equal(html.includes(label), false);
  });

  it("continues from New item through the existing item step", async () => {
    const view = await mount(createElement(ClientFirstPage));
    await click(view.host, "Edit");
    await click(view.host, "Choose from saving");
    await click(view.host, "New item");
    assert.equal((view.host.textContent ?? "").includes(emptySavedProjects), false);
    assert.match(view.host.textContent ?? "", /Start from/);
    const continueButton = buttonNamed(view.host, "Continue to the item");
    assert.equal(continueButton.hasAttribute("disabled"), false);
    await click(view.host, "Continue to the item");
    assert.match(view.host.textContent ?? "", /Add your item\./);
    await view.unmount();
  });

  it("leaves New Project, Single item, and the manual steps unchanged", async () => {
    const view = await mount(createElement(ClientFirstPage));
    await click(view.host, "Edit");
    await click(view.host, "New Project");
    assert.match(view.host.textContent ?? "", /Work on/);
    assert.ok(buttonNamed(view.host, "Batch"));
    assert.ok(buttonNamed(view.host, "One by one"));
    assert.equal((view.host.textContent ?? "").includes(editSupport), false);
    assert.equal((view.host.textContent ?? "").includes("Choose from saving"), false);
    assert.equal(view.host.querySelector("[aria-labelledby='saved-brief-label']"), null);

    await click(view.host, "Single item");
    assert.match(view.host.textContent ?? "", /Item role/);
    assert.ok(buttonNamed(view.host, "Hero"));
    assert.ok(buttonNamed(view.host, "Secondary"));
    assert.equal((view.host.textContent ?? "").includes("Start from"), false);
    assert.equal(view.host.querySelector("[aria-labelledby='saved-brief-label']"), null);

    const steps = view.host.querySelector("nav.steps")?.textContent ?? "";
    for (const step of primaryFlow) assert.match(steps, new RegExp(step.label));
    assert.match(view.host.textContent ?? "", /Start creating\./);
    assert.match(view.host.textContent ?? "", /What would you like to do\?/);
    await view.unmount();
  });

  it("keeps review and submit resolution for a stored saved-brief id", () => {
    const draft = createEmptyDraft();
    draft.job = {
      kind: "edit",
      newProjectMode: null,
      editMode: "choose_from_saving",
      savedItemId: "saving-lounge-chair",
      singleItemRole: null,
    };
    const review = JSON.stringify(buildClientReview(draft));
    assert.match(review, /Saved brief/);
    assert.match(review, /Lounge chair/);
    assert.equal(normalizeDraft(draft).job.savedItemId, "saving-lounge-chair");
  });
});
