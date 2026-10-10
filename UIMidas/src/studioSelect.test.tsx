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
});
