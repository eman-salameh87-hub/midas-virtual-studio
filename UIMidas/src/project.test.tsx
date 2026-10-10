import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StudioShell } from "./components/layout/StudioShell";
import { ProjectSection, type ProjectStart } from "./components/sections/ProjectSection";
import { primaryFlow, projectFlow } from "./flow";
import { ClientFirstPage } from "./pages/ClientFirstPage";

function projectScreen(start: ProjectStart, existingRoom = "", newStyledSpace = "") {
  return renderToStaticMarkup(
    <StudioShell mode="projects" onMode={() => {}} steps={projectFlow} section="project" onSection={() => {}}>
      <ProjectSection
        start={start}
        existingRoom={existingRoom}
        newStyledSpace={newStyledSpace}
        onStart={() => {}}
        onExistingRoom={() => {}}
        onNewStyledSpace={() => {}}
        onContinue={() => {}}
      />
    </StudioShell>,
  );
}

function selectedCards(html: string) {
  return html.match(/class="project-card" aria-pressed="true"/g) ?? [];
}

describe("project flow step 01", () => {
  it("keeps the manual flow on its five steps", () => {
    const html = renderToStaticMarkup(<ClientFirstPage />);
    assert.match(html, /aria-pressed="true">Manual/);
    assert.match(html, /What would you like to do\?/);
    for (const label of primaryFlow.map((step) => step.label)) assert.match(html, new RegExp(label));
    assert.equal(html.includes("Where would you like to begin?"), false);
  });

  it("shows the three project steps with Product or collection selected", () => {
    const html = projectScreen("product_or_collection");
    assert.match(html, /aria-pressed="true">Projects/);
    assert.match(html, /01/);
    assert.match(html, />Project</);
    assert.match(html, /The Item/);
    assert.match(html, />Scope</);
    assert.equal(html.includes("The Job"), false);
    assert.equal(html.includes("Preferences"), false);
    assert.equal(html.includes("Suggestions"), false);
    assert.match(html, /Where would you like to begin\?/);
    assert.match(html, /aria-pressed="true">[\s\S]*Product or collection/);
    assert.equal(selectedCards(html).length, 1);
    assert.equal(html.includes("<textarea"), false);
    assert.match(html, /Continue to the item/);
  });

  it("shows and keeps the Existing room note", () => {
    const html = projectScreen("existing_room", "Keep the windows and floor.", "A relaxed living room");
    assert.match(html, /What should stay or change\?/);
    assert.match(html, /Keep the windows and floor\. Replace the seating with the supplied set\./);
    assert.match(html, /Keep the windows and floor\./);
    assert.equal(html.includes("A relaxed living room"), false);
    assert.equal(html.includes("Describe the space to create"), false);
    assert.equal(selectedCards(html).length, 1);
  });

  it("shows and keeps the New styled space note", () => {
    const html = projectScreen("new_styled_space", "Keep the windows and floor.", "A relaxed living room");
    assert.match(html, /Describe the space to create/);
    assert.match(html, /A relaxed living room with the supplied sofa as the main subject\./);
    assert.match(html, /A relaxed living room/);
    assert.equal(html.includes("Keep the windows and floor."), false);
    assert.equal(html.includes("What should stay or change?"), false);
    assert.equal(selectedCards(html).length, 1);
  });

  it("shows the empty saved-project message", () => {
    const html = projectScreen("saved_project", "Keep the windows and floor.", "A relaxed living room");
    assert.match(html, /No saved projects yet\. Choose a different starting point/);
    assert.equal(html.includes("<textarea"), false);
    assert.equal(selectedCards(html).length, 1);
    assert.match(html, /Continue to the item/);
  });
});
