import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createElement, useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { GlobalWindow } from "happy-dom";
import { StudioSelect } from "./components/ui/StudioSelect";
import { SuggestionsSection } from "./components/sections/SuggestionsSection";
import { DraftProvider } from "./state/DraftProvider";

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
  IS_REACT_ACT_ENVIRONMENT: true,
});

const { createRoot } = await import("react-dom/client");
const { act } = await import("react");

const moodOptions = [
  { value: "automatic", label: "Automatic" },
  { value: "calm_natural", label: "Calm & natural" },
  { value: "warm_inviting", label: "Warm & inviting" },
];

function Harness({ initial = "automatic" }: { initial?: string }) {
  const [value, setValue] = useState(initial);
  return createElement(
    "div",
    { "data-value": value },
    createElement(StudioSelect, { value, options: moodOptions, onChange: setValue }),
  );
}

function selectedValue(host: HTMLElement) {
  return host.querySelector("[data-value]")?.getAttribute("data-value");
}

describe("studio select", () => {
  it("keeps native option values for existing payload tests", () => {
    const html = renderToStaticMarkup(
      <DraftProvider>
        <SuggestionsSection onBack={() => {}} onContinue={() => {}} />
      </DraftProvider>,
    );
    assert.match(html, /value="automatic" selected="">Automatic/);
    assert.match(html, /class="studio-select__trigger"/);
    assert.equal(html.includes("studio-select__menu"), false);
  });

  it("opens a custom listbox and keeps every option readable without hover", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(createElement(Harness));
    });
    const trigger = host.querySelector("button.studio-select__trigger") as HTMLButtonElement;
    assert.ok(trigger);
    assert.equal(trigger.getAttribute("role"), "combobox");
    assert.equal(trigger.getAttribute("aria-expanded"), "false");
    await act(async () => {
      trigger.click();
    });
    const options = [...document.querySelectorAll(".studio-select__option")];
    assert.equal(options.length, 3);
    assert.equal(options.every((option) => option.classList.contains("studio-select__option")), true);
    assert.equal(options[0]?.getAttribute("aria-selected"), "true");
    assert.equal(options[1]?.getAttribute("aria-selected"), "false");
    await act(async () => {
      root.unmount();
    });
    host.remove();
  });

  it("selects with pointer and keyboard without changing option values", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(createElement(Harness));
    });
    const trigger = host.querySelector("button.studio-select__trigger") as HTMLButtonElement;
    const native = host.querySelector("select") as HTMLSelectElement;
    await act(async () => {
      trigger.click();
    });
    const calm = [...document.querySelectorAll(".studio-select__option")].find((entry) => entry.textContent === "Calm & natural");
    await act(async () => {
      calm?.dispatchEvent(new dom.MouseEvent("click", { bubbles: true }) as unknown as MouseEvent);
    });
    assert.equal(selectedValue(host), "calm_natural");
    assert.equal(native.value, "calm_natural");

    await act(async () => {
      native.value = "warm_inviting";
      native.dispatchEvent(new dom.Event("change", { bubbles: true }) as unknown as Event);
    });
    assert.equal(selectedValue(host), "warm_inviting");

    await act(async () => {
      trigger.dispatchEvent(new dom.KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }) as unknown as KeyboardEvent);
    });
    await act(async () => {
      trigger.dispatchEvent(new dom.KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }) as unknown as KeyboardEvent);
    });
    await act(async () => {
      trigger.dispatchEvent(new dom.KeyboardEvent("keydown", { key: "Enter", bubbles: true }) as unknown as KeyboardEvent);
    });
    assert.equal(selectedValue(host), "automatic");

    await act(async () => {
      root.unmount();
    });
    host.remove();
  });

  it("opens upward near the bottom of the viewport and downward when there is room", async () => {
    const many = Array.from({ length: 8 }, (_, index) => ({ value: `view-${index}`, label: `View ${index + 1}` }));
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(createElement(StudioSelect, { value: "view-0", options: many, onChange: () => {} }));
    });
    const trigger = host.querySelector("button.studio-select__trigger") as HTMLButtonElement;
    const box = { top: 640, bottom: 688, left: 48, right: 288, width: 240, height: 48, x: 48, y: 640, toJSON() { return {}; } };
    trigger.getBoundingClientRect = () => box as DOMRect;
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 760 });
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1200 });

    await act(async () => {
      trigger.click();
    });
    const menu = document.querySelector(".studio-select__menu") as HTMLElement;
    assert.ok(menu);
    const upwardTop = Number.parseFloat(menu.style.top);
    const upwardHeight = Number.parseFloat(menu.style.maxHeight);
    assert.ok(upwardTop + upwardHeight <= box.top, "menu should sit above the trigger");
    assert.ok(upwardTop >= 8, "menu should stay inside the viewport");
    const options = [...document.querySelectorAll(".studio-select__option")];
    assert.equal(options[0]?.textContent, "View 1");
    assert.equal(options.at(-1)?.textContent, "View 8");

    await act(async () => {
      trigger.click();
    });
    box.top = 40;
    box.bottom = 88;
    box.y = 40;
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 900 });
    await act(async () => {
      trigger.click();
    });
    const downward = document.querySelector(".studio-select__menu") as HTMLElement;
    assert.ok(downward);
    const downwardTop = Number.parseFloat(downward.style.top);
    const downwardHeight = Number.parseFloat(downward.style.maxHeight);
    assert.ok(downwardTop >= box.bottom, "menu should open below the trigger");
    assert.ok(downwardTop + downwardHeight <= window.innerHeight - 8);

    box.top = 620;
    box.bottom = 668;
    box.y = 620;
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 740 });
    await act(async () => {
      window.dispatchEvent(new dom.Event("resize") as unknown as Event);
    });
    const resizedTop = Number.parseFloat(downward.style.top);
    const resizedHeight = Number.parseFloat(downward.style.maxHeight);
    assert.ok(
      resizedTop + resizedHeight <= box.top,
      `expected upward menu after resize, got top ${resizedTop} height ${resizedHeight} trigger ${box.top}`,
    );

    await act(async () => {
      root.unmount();
    });
    host.remove();
  });
});
