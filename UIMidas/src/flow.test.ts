import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { primaryFlow, projectFlow } from "./flow";

describe("client first navigation", () => {
  it("uses the five demo steps and keeps references inside the item", () => {
    assert.deepEqual(
      primaryFlow.map((step) => step.label),
      ["The Job", "The Item", "Scope", "Preferences", "Suggestions"],
    );
    assert.deepEqual(
      primaryFlow.map((step) => step.id),
      ["job", "item", "scope", "preferences", "suggestions"],
    );
    assert.equal(primaryFlow.some((step) => step.id === "references"), false);
  });

  it("uses three steps for the project flow", () => {
    assert.deepEqual(
      projectFlow.map((step) => `${step.index} ${step.label}`),
      ["01 Project", "02 The Item", "03 Scope"],
    );
  });
});
