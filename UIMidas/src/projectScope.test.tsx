import { GlobalWindow } from "happy-dom";
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { ProjectScopeSection } from "./components/sections/ProjectScopeSection";
import { ScopeSection } from "./components/sections/ScopeSection";
import { DraftProvider } from "./state/DraftProvider";
import type { ProjectScopeOutput } from "./lib/projectBrief";

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

const outputLabels = [
  "White BK",
  "Lifestyle",
  "Website",
  "New Composition",
  "Variations",
  "Create with this item",
  "Others",
];

function ScopeHarness({ sink }: { sink: { outputs: ProjectScopeOutput[] } }) {
  const [outputs, setOutputs] = useState<ProjectScopeOutput[]>([]);
  sink.outputs = outputs;
  return createElement(ProjectScopeSection, {
    outputs,
    onOutputs: setOutputs,
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

function buttonText(button: Element) {
  return button.textContent?.replace(/\s+/g, " ").trim() ?? "";
}

async function click(host: ParentNode, name: string) {
  const buttons = [...host.querySelectorAll("button")];
  const button = buttons.find((entry) => buttonText(entry) === name) ?? buttons.find((entry) => buttonText(entry).includes(name));
  assert.ok(button, name);
  await act(async () => {
    button.dispatchEvent(new dom.MouseEvent("click", { bubbles: true }) as unknown as MouseEvent);
  });
}

async function clickStep(host: ParentNode, label: string) {
  const button = [...host.querySelectorAll("nav.steps button")].find((entry) => buttonText(entry).endsWith(label));
  assert.ok(button, label);
  await act(async () => {
    button.dispatchEvent(new dom.MouseEvent("click", { bubbles: true }) as unknown as MouseEvent);
  });
}

async function toggleChoice(host: ParentNode, label: string) {
  const choice = [...host.querySelectorAll("label.choice")].find((entry) => entry.textContent?.includes(label));
  const input = choice?.querySelector("input");
  assert.ok(input, label);
  await act(async () => {
    input.dispatchEvent(new dom.MouseEvent("click", { bubbles: true }) as unknown as MouseEvent);
  });
}

async function setControl(control: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement, value: string) {
  const prototype = control.tagName === "TEXTAREA" ? dom.HTMLTextAreaElement.prototype : dom.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
  await act(async () => {
    if (control.tagName === "SELECT") control.value = value;
    else setter?.call(control, value);
    control.dispatchEvent(new dom.Event("input", { bubbles: true }) as unknown as Event);
    control.dispatchEvent(new dom.Event("change", { bubbles: true }) as unknown as Event);
  });
}

async function addImage(host: ParentNode, name: string) {
  const input = host.querySelector('input[type="file"]') as HTMLInputElement | null;
  assert.ok(input);
  const transfer = new dom.DataTransfer();
  transfer.items.add(new dom.File([Uint8Array.from([1, 2, 3, 4])], name, { type: "image/jpeg" }));
  await act(async () => {
    input.files = transfer.files as unknown as FileList;
    input.dispatchEvent(new dom.Event("change", { bubbles: true }) as unknown as Event);
  });
}

async function addEmptyImage(host: ParentNode) {
  const input = host.querySelector('input[type="file"]') as HTMLInputElement | null;
  assert.ok(input);
  const transfer = new dom.DataTransfer();
  transfer.items.add(new dom.File([], "empty.jpg", { type: "image/jpeg" }));
  await act(async () => {
    input.files = transfer.files as unknown as FileList;
    input.dispatchEvent(new dom.Event("change", { bubbles: true }) as unknown as Event);
  });
}

function checkedValues(host: ParentNode, name: string) {
  return [...host.querySelectorAll(`input[name="${name}"]`)]
    .filter((input) => (input as HTMLInputElement).checked)
    .map((input) => (input as HTMLInputElement).value);
}

describe("project flow step 03", () => {
  it("renders the seven outputs and leaves out View & delivery", () => {
    const projects = renderToStaticMarkup(
      createElement(ProjectScopeSection, {
        outputs: [],
        onOutputs: () => {},
        onBack: () => {},
        onContinue: () => {},
      }),
    );
    const manual = renderToStaticMarkup(
      createElement(DraftProvider, null, createElement(ScopeSection, { onBack: () => {}, onContinue: () => {} })),
    );
    assert.match(projects, /What would you like to create\?/);
    assert.match(projects, /Select one or more\./);
    for (const label of outputLabels) assert.match(projects, new RegExp(label));
    assert.match(projects, /Clean catalogue imagery/);
    assert.match(projects, /Review choices/);
    assert.equal(projects.includes("Count"), false);
    assert.equal(projects.includes('type="number"'), false);
    assert.equal(projects.includes("View &amp; delivery"), false);
    assert.equal(projects.includes("Image proportions"), false);
    assert.equal(projects.includes("Submit job"), false);
    assert.equal(projects.includes("More options"), false);
    assert.match(manual, /View &amp; delivery/);
    assert.match(manual, /More options/);
  });

  it("selects several outputs, keeps variation choices, and keeps the other outcome", async () => {
    const sink = { outputs: [] as ProjectScopeOutput[] };
    const view = await mount(createElement(ScopeHarness, { sink }));
    await toggleChoice(view.host, "Lifestyle");
    await toggleChoice(view.host, "Variations");
    assert.deepEqual(checkedValues(view.host, "project-scope-output").sort(), ["lifestyle", "variations"]);
    assert.match(view.host.textContent ?? "", /What should vary\?/);
    await toggleChoice(view.host, "Lighting");
    await toggleChoice(view.host, "Camera view");
    assert.equal(view.host.querySelector('input[type="number"]'), null);
    assert.equal(view.host.textContent?.includes("Count"), false);
    await toggleChoice(view.host, "Others");
    const area = view.host.querySelector("textarea");
    assert.ok(area);
    assert.equal(area.placeholder, "What would you like to receive?");
    await setControl(area, "A styled corner");
    await toggleChoice(view.host, "Lifestyle");
    await toggleChoice(view.host, "Lifestyle");
    const variations = sink.outputs.find((output) => output.concept === "variations");
    const others = sink.outputs.find((output) => output.concept === "others");
    assert.deepEqual(variations?.variationAspects, ["lighting", "camera_view"]);
    assert.equal(others?.otherLabel, "A styled corner");
    assert.equal(view.host.textContent?.includes("View & delivery"), false);
    await view.unmount();
  });

  it("carries project, item, and scope choices into review and keeps them apart from Manual", async () => {
    const view = await mount(createElement(ClientFirstPage));
    await click(view.host, "Projects");
    await click(view.host, "Existing room");
    const note = view.host.querySelector("textarea");
    assert.ok(note);
    await setControl(note, "Keep the windows and floor.");
    await click(view.host, "Continue to the item");
    assert.equal(view.host.textContent?.includes("More options"), false);
    const department = [...view.host.querySelectorAll("label")].find((entry) => entry.querySelector("span")?.textContent === "Department")?.querySelector("select");
    assert.ok(department);
    await act(async () => {
      department.value = "home-furniture";
      department.dispatchEvent(new dom.Event("change", { bubbles: true }) as unknown as Event);
    });
    const category = [...view.host.querySelectorAll("label")].find((entry) => entry.querySelector("span")?.textContent === "Category")?.querySelector("select");
    assert.ok(category);
    await act(async () => {
      category.value = "home-furniture/living-rooms";
      category.dispatchEvent(new dom.Event("change", { bubbles: true }) as unknown as Event);
    });
    await addImage(view.host, "sofa.jpg");
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 320));
    });
    await click(view.host, "Choose the outcomes");
    assert.match(view.host.textContent ?? "", /What would you like to create\?/);
    assert.equal(view.host.textContent?.includes("View & delivery"), false);
    assert.equal(view.host.textContent?.includes("Submit job"), false);
    assert.equal(view.host.textContent?.includes("More options"), false);
    await click(view.host, "Back");
    assert.match(view.host.textContent ?? "", /Add your item\./);
    await click(view.host, "Choose the outcomes");
    await toggleChoice(view.host, "Lifestyle");
    await toggleChoice(view.host, "Variations");
    await toggleChoice(view.host, "Styling");
    assert.equal(view.host.querySelector('input[type="number"]'), null);
    await toggleChoice(view.host, "Others");
    const other = view.host.querySelector("textarea");
    assert.ok(other);
    await setControl(other, "A styled corner");
    await click(view.host, "Review choices");
    const review = view.host.textContent ?? "";
    assert.match(review, /Check the brief/);
    assert.match(review, /Existing room/);
    assert.match(review, /Keep the windows and floor\./);
    assert.match(review, /Home Furniture/);
    assert.match(review, /Living Rooms/);
    assert.match(review, /sofa\.jpg/);
    assert.match(review, /Lifestyle/);
    assert.match(review, /Styling/);
    assert.match(review, /A styled corner/);
    assert.equal(review.includes("Count"), false);
    assert.equal(review.includes("View & delivery"), false);
    assert.equal(review.includes("Job created"), false);
    const submit = [...view.host.querySelectorAll("button")].find((button) => button.textContent === "Submit job") as HTMLButtonElement;
    assert.ok(submit);
    assert.equal(submit.disabled, false);

    await click(view.host, "Manual");
    await click(view.host, "Batch");
    await click(view.host, "Continue to the item");
    await click(view.host, "Choose the outcomes");
    assert.match(view.host.textContent ?? "", /View & delivery/);
    assert.deepEqual(checkedValues(view.host, "scope-output"), []);
    await click(view.host, "Projects");
    assert.match(view.host.textContent ?? "", /Styling/);
    await view.unmount();
  });

  it("blocks submit until the project note, item, and other outcome are present", async () => {
    const view = await mount(createElement(ClientFirstPage));
    await click(view.host, "Projects");
    await click(view.host, "Continue to the item");
    assert.equal(view.host.querySelector(".issues"), null);
    await click(view.host, "Choose the outcomes");
    assert.equal(view.host.querySelector(".issues"), null);
    assert.equal(view.host.textContent?.includes("Choose a department, or mark the category as unknown."), false);
    assert.equal(view.host.textContent?.includes("No product references yet."), false);
    assert.equal(view.host.textContent?.includes("Choose at least one output."), false);
    await click(view.host, "Review choices");
    assert.match(view.host.textContent ?? "", /Check the brief/);
    assert.ok(view.host.querySelector(".issues"));
    assert.match(view.host.textContent ?? "", /No product references yet\./);
    assert.match(view.host.textContent ?? "", /Choose a department, or mark the category as unknown\./);
    assert.match(view.host.textContent ?? "", /Choose at least one output\./);
    await click(view.host, "Submit job");
    await act(async () => {
      await Promise.resolve();
    });
    assert.equal(view.host.textContent?.includes("Job created"), false);

    await clickStep(view.host, "Project");
    await click(view.host, "Existing room");
    await click(view.host, "Continue to the item");
    const department = [...view.host.querySelectorAll("label")].find((entry) => entry.querySelector("span")?.textContent === "Department")?.querySelector("select");
    assert.ok(department);
    await act(async () => {
      department.value = "";
      department.dispatchEvent(new dom.Event("change", { bubbles: true }) as unknown as Event);
    });
    await click(view.host, "Choose the outcomes");
    await toggleChoice(view.host, "Others");
    assert.equal(view.host.querySelector(".issues"), null);
    await click(view.host, "Review choices");
    assert.match(view.host.textContent ?? "", /Check the brief/);
    assert.match(view.host.textContent ?? "", /What should stay or change\?/);
    assert.match(view.host.textContent ?? "", /Name the other output\./);
    assert.match(view.host.textContent ?? "", /No product references yet\./);
    await click(view.host, "Submit job");
    await act(async () => {
      await Promise.resolve();
    });
    assert.equal(view.host.textContent?.includes("Job created"), false);
    await view.unmount();
  });

  it("reaches review and submit only after a ready reference and a selected output", async () => {
    const view = await mount(createElement(ClientFirstPage));
    await click(view.host, "Projects");
    await click(view.host, "Continue to the item");
    const department = [...view.host.querySelectorAll("label")].find((entry) => entry.querySelector("span")?.textContent === "Department")?.querySelector("select");
    assert.ok(department);
    await act(async () => {
      department.value = "home-furniture";
      department.dispatchEvent(new dom.Event("change", { bubbles: true }) as unknown as Event);
    });
    const category = [...view.host.querySelectorAll("label")].find((entry) => entry.querySelector("span")?.textContent === "Category")?.querySelector("select");
    assert.ok(category);
    await act(async () => {
      category.value = "home-furniture/living-rooms";
      category.dispatchEvent(new dom.Event("change", { bubbles: true }) as unknown as Event);
    });
    await addImage(view.host, "catalogue.jpg");
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 320));
    });
    await click(view.host, "Choose the outcomes");
    await toggleChoice(view.host, "White BK");
    await click(view.host, "Review choices");
    assert.match(view.host.textContent ?? "", /catalogue\.jpg/);
    assert.match(view.host.textContent ?? "", /White BK/);
    await click(view.host, "Submit job");
    await act(async () => {
      await Promise.resolve();
    });
    assert.match(view.host.textContent ?? "", /Job created/);
    await view.unmount();
  });

  it("keeps an uploading or failed reference from opening review", async () => {
    const uploading = await mount(createElement(ClientFirstPage));
    await click(uploading.host, "Projects");
    await click(uploading.host, "Continue to the item");
    await addImage(uploading.host, "pending.jpg");
    assert.match(uploading.host.textContent ?? "", /pending\.jpg/);
    assert.equal(uploading.host.querySelector(".issues"), null);
    assert.equal(uploading.host.textContent?.includes("A file is still being added."), false);
    await click(uploading.host, "Choose the outcomes");
    assert.match(uploading.host.textContent ?? "", /Add your item\./);
    assert.equal(uploading.host.textContent?.includes("Submit job"), false);
    await uploading.unmount();

    const failed = await mount(createElement(ClientFirstPage));
    await click(failed.host, "Projects");
    await click(failed.host, "Continue to the item");
    await addEmptyImage(failed.host);
    assert.match(failed.host.textContent ?? "", /This file is empty\./);
    await click(failed.host, "Choose the outcomes");
    assert.match(failed.host.textContent ?? "", /Add your item\./);
    assert.equal(failed.host.textContent?.includes("Submit job"), false);
    await failed.unmount();
  });

  it("keeps Manual validation on Check the brief", async () => {
    const view = await mount(createElement(ClientFirstPage));
    await click(view.host, "Batch");
    await click(view.host, "Continue to the item");
    assert.equal(view.host.querySelector(".issues"), null);
    assert.equal(view.host.textContent?.includes("Choose a department, or mark the category as unknown."), false);
    await click(view.host, "Choose the outcomes");
    assert.equal(view.host.querySelector(".issues"), null);
    assert.equal(view.host.textContent?.includes("Choose at least one output."), false);
    await click(view.host, "Continue");
    assert.equal(view.host.querySelector(".issues"), null);
    await click(view.host, "Continue");
    assert.equal(view.host.querySelector(".issues"), null);
    await click(view.host, "Review choices");
    assert.match(view.host.textContent ?? "", /Check the brief/);
    const issues = view.host.querySelector(".issues");
    assert.ok(issues);
    assert.match(issues.textContent ?? "", /The Item/);
    assert.match(issues.textContent ?? "", /Choose a department, or mark the category as unknown\./);
    assert.match(issues.textContent ?? "", /Scope/);
    assert.match(issues.textContent ?? "", /Choose at least one output\./);
    await click(view.host, "Submit job");
    await act(async () => {
      await Promise.resolve();
    });
    assert.equal(view.host.textContent?.includes("Job created"), false);
    await view.unmount();
  });
});
