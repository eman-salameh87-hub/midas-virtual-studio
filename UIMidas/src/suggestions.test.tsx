import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { SuggestionsSection } from "./components/sections/SuggestionsSection";
import { buildClientReview } from "./lib/reviewModel";
import { DraftProvider } from "./state/DraftProvider";
import { createEmptyDraft } from "./state/emptyDraft";
import type { ClientJobDraft, MoodVibe } from "./types/draft";

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

describe("suggestions mood", () => {
  it("shows Automatic and stores automatic on a fresh draft", () => {
    const draft = createEmptyDraft();
    assert.equal(draft.suggestions.mood, "automatic");
    const html = renderSuggestions(draft);
    assert.match(html, /value="automatic" selected="">Automatic/);
    assert.equal(html.includes(">Select<"), false);
  });

  it("keeps another mood in the dropdown and in review", () => {
    const draft = withMood("calm_natural");
    const html = renderSuggestions(draft);
    assert.match(html, /value="calm_natural" selected="">Calm &amp; natural/);
    const suggestions = buildClientReview(draft, draft.items[0].id).sections.find((section) => section.id === "suggestions");
    assert.equal(suggestions?.groups[0]?.facts.some((fact) => fact.text === "Calm & natural"), true);
  });
});
