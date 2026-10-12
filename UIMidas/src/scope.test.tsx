import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { ScopeSection } from "./components/sections/ScopeSection";
import { DraftProvider } from "./state/DraftProvider";
import { createEmptyDraft } from "./state/emptyDraft";
import type { ScopeDraft } from "./types/draft";

function renderScope(scope?: ScopeDraft) {
  const draft = createEmptyDraft();
  if (scope) draft.items[0].scope = scope;
  return renderToStaticMarkup(
    <DraftProvider initialDraft={draft}>
      <ScopeSection onBack={() => {}} onContinue={() => {}} />
    </DraftProvider>,
  );
}

describe("scope conditional ui", () => {
  it("shows View & delivery and hides the conditional sections when nothing is selected", () => {
    const html = renderScope();
    assert.match(html, /View &amp; delivery/);
    assert.match(html, /Views/);
    assert.match(html, /Image proportions/);
    assert.match(html, /Resolution/);
    assert.equal(html.includes("What should vary?"), false);
    assert.equal(html.includes("Describe the other outcome"), false);
    assert.equal(html.includes("What would you like to receive?"), false);
  });

  it("shows Lighting, Styling, and Camera view while Variations is selected", () => {
    const html = renderScope({
      outputs: [
        {
          id: "vars",
          concept: "variations",
          otherLabel: "",
          views: [],
          proportion: null,
          resolution: null,
          variationCount: null,
          variationAspects: ["lighting", "camera_view"],
        },
      ],
    });
    assert.match(html, /What should vary\?/);
    assert.match(html, /Lighting/);
    assert.match(html, /Styling/);
    assert.match(html, /Camera view/);
    assert.match(html, /checked="" value="lighting"/);
    assert.match(html, /checked="" value="camera_view"/);
    assert.equal(html.includes('checked="" value="styling"'), false);
  });

  it("hides What should vary? when Variations is not selected", () => {
    const html = renderScope({
      outputs: [
        {
          id: "white",
          concept: "white_bk",
          otherLabel: "",
          views: [],
          proportion: null,
          resolution: null,
          variationCount: null,
        },
      ],
    });
    assert.equal(html.includes("What should vary?"), false);
    assert.match(html, /View &amp; delivery/);
  });

  it("shows the Others textarea only while Others is selected", () => {
    const selected = renderScope({
      outputs: [
        {
          id: "other",
          concept: "others",
          otherLabel: "A room set",
          views: [],
          proportion: null,
          resolution: null,
          variationCount: null,
        },
      ],
    });
    assert.match(selected, /Describe the other outcome/);
    assert.match(selected, /What would you like to receive\?/);
    assert.match(selected, /A room set/);

    const hidden = renderScope();
    assert.equal(hidden.includes("Describe the other outcome"), false);
    assert.equal(hidden.includes("<textarea"), false);
  });

  it("shows the Midas view, proportion, and resolution options", () => {
    const html = renderScope();
    const views = html.slice(html.indexOf(">Views<"), html.indexOf(">Image proportions<"));
    const proportions = html.slice(html.indexOf(">Image proportions<"), html.indexOf(">Resolution<"));
    const resolution = html.slice(html.indexOf(">Resolution<"), html.indexOf("step-footer"));
    assert.match(
      views,
      /Category template.*Wide view.*Close-up.*Wide view \+ close-up.*3\/4 Angle View.*Front View.*Side View.*Top View/,
    );
    assert.match(proportions, /Standard for category.*Square · 1:1.*Portrait · 4:5.*Landscape · 16:9/);
    assert.match(resolution, /Standard for category.*2K.*4K/);
    assert.match(views, /value="category_template" selected=""/);
    assert.match(proportions, /value="standard_for_category" selected=""/);
    assert.match(resolution, /value="standard_for_category" selected=""/);
    assert.equal(views.includes(">Front<"), false);
    assert.equal(proportions.includes(">1:1<"), false);
    assert.equal(resolution.includes(">Web<"), false);

    const chosen = renderScope({
      outputs: [],
      deliveryView: "wide_view",
      deliveryProportion: "1:1",
      deliveryResolution: "2k",
    });
    assert.match(chosen, /value="wide_view" selected=""/);
    assert.match(chosen, /value="1:1" selected=""/);
    assert.match(chosen, /value="2k" selected=""/);

    for (const [value, label] of [
      ["three_quarter", "3/4 Angle View"],
      ["front", "Front View"],
      ["side", "Side View"],
      ["top", "Top View"],
    ] as const) {
      const html = renderScope({ outputs: [], deliveryView: value, deliveryProportion: "1:1", deliveryResolution: "2k" });
      assert.match(html, new RegExp(`value="${value}" selected=""`));
      assert.match(html, new RegExp(`>${label}<`));
    }
  });

  it("shows stored variation choices and other text when the scope screen is opened again", () => {
    const html = renderScope({
      outputs: [
        {
          id: "vars",
          concept: "variations",
          otherLabel: "",
          views: ["close_up"],
          proportion: "4:5",
          resolution: "4k",
          variationCount: 2,
          variationAspects: ["styling"],
        },
        {
          id: "other",
          concept: "others",
          otherLabel: "Keep this note",
          views: ["close_up"],
          proportion: "4:5",
          resolution: "4k",
          variationCount: null,
        },
      ],
    });
    assert.match(html, /checked="" value="styling"/);
    assert.match(html, /Keep this note/);
    assert.match(html, /value="close_up" selected=""/);
    assert.match(html, /value="4:5" selected=""/);
    assert.match(html, /value="4k" selected=""/);
    assert.match(html, /View &amp; delivery/);
  });
});
