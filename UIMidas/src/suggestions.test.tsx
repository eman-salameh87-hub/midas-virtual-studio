import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { GlobalWindow } from "happy-dom";
import { SuggestionsSection } from "./components/sections/SuggestionsSection";
import { buildClientReview } from "./lib/reviewModel";
import { normalizeDraft } from "./normalization/normalizeDraft";
import { DraftProvider, useClientJobDraft } from "./state/DraftProvider";
import { createEmptyDraft } from "./state/emptyDraft";
import type { ClientJobDraft, MoodVibe } from "./types/draft";

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

function renderSuggestions(draft = createEmptyDraft()) {
  return renderToStaticMarkup(
    <DraftProvider initialDraft={draft}>
      <SuggestionsSection onBack={() => {}} onContinue={() => {}} />
    </DraftProvider>,
  );
}

function withMood(mood: MoodVibe): ClientJobDraft {
  const draft = createEmptyDraft();
  draft.suggestions = { ...draft.suggestions, mood };
  return draft;
}

function Probe() {
  const draft = useClientJobDraft();
  return createElement("pre", { "data-probe": "suggestions" }, JSON.stringify(draft.suggestions));
}

describe("suggestions mood", () => {
  it("shows Automatic and stores automatic on a fresh draft", () => {
    const draft = createEmptyDraft();
    assert.equal(draft.suggestions.mood, "automatic");
    const html = renderSuggestions(draft);
    assert.match(html, /value="automatic" selected="">Automatic/);
    assert.equal(html.includes(">Select<"), false);
  });

  it("keeps Plants and Human as selectable finish cards without Suggest or Leave out buttons", () => {
    const html = renderSuggestions();
    assert.equal((html.match(/class="finish"/g) ?? []).length, 2);
    assert.match(html, /class="finish-grid"/);
    assert.match(html, /class="finish__switch"/);
    assert.equal(html.includes(">Suggest<"), false);
    assert.equal(html.includes(">Leave out<"), false);
  });

  it("keeps another mood in the dropdown and in review", () => {
    const draft = withMood("calm_natural");
    const html = renderSuggestions(draft);
    assert.match(html, /value="calm_natural" selected="">Calm &amp; natural/);
    const suggestions = buildClientReview(draft, draft.items[0].id).sections.find((section) => section.id === "suggestions");
    assert.equal(suggestions?.groups[0]?.facts.some((fact) => fact.text === "Calm & natural"), true);
  });
});

describe("suggestions card toggles", () => {
  it("toggles Plants and Human independently and maps selected to suggest", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(
        createElement(
          DraftProvider,
          null,
          createElement(SuggestionsSection, { onBack: () => {}, onContinue: () => {} }),
          createElement(Probe),
        ),
      );
    });
    const cards = [...host.querySelectorAll("button.finish")] as HTMLButtonElement[];
    assert.equal(cards.length, 2);
    assert.equal(cards[0]?.getAttribute("aria-pressed"), "false");
    assert.equal(cards[1]?.getAttribute("aria-pressed"), "false");

    await act(async () => {
      cards[0]?.click();
    });
    let state = JSON.parse(host.querySelector("[data-probe]")?.textContent ?? "{}") as ClientJobDraft["suggestions"];
    assert.equal(state.plants, "suggest");
    assert.equal(state.human, "unspecified");
    assert.equal(cards[0]?.getAttribute("aria-pressed"), "true");
    assert.equal(cards[1]?.getAttribute("aria-pressed"), "false");

    await act(async () => {
      cards[1]?.click();
    });
    state = JSON.parse(host.querySelector("[data-probe]")?.textContent ?? "{}") as ClientJobDraft["suggestions"];
    assert.equal(state.plants, "suggest");
    assert.equal(state.human, "suggest");
    assert.equal(cards[0]?.getAttribute("aria-pressed"), "true");
    assert.equal(cards[1]?.getAttribute("aria-pressed"), "true");

    const draft = createEmptyDraft();
    draft.suggestions = state;
    const brief = normalizeDraft(draft);
    assert.equal(brief.suggestions?.plants, "suggest");
    assert.equal(brief.suggestions?.human, "suggest");

    await act(async () => {
      cards[0]?.click();
    });
    state = JSON.parse(host.querySelector("[data-probe]")?.textContent ?? "{}") as ClientJobDraft["suggestions"];
    assert.equal(state.plants, "leave_out");
    assert.equal(state.human, "suggest");
    draft.suggestions = state;
    const after = normalizeDraft(draft);
    assert.equal(after.suggestions?.plants, "leave_out");
    assert.equal(after.suggestions?.human, "suggest");

    await act(async () => {
      root.unmount();
    });
    host.remove();
  });
});
