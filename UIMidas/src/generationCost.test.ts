import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { formatCostLine, isKnownRecordedCost } from "./lib/generationCost";

describe("recorded generation cost display", () => {
  it("formats the provider-recorded amount and currency", () => {
    assert.equal(
      formatCostLine("Generation cost", {
        output_id: "gen-1",
        amount: 0.101968,
        currency: "USD",
        status: "known",
      }),
      "Generation cost: $0.101968",
    );
  });

  it("does not treat missing cost as zero or infer an amount", () => {
    assert.equal(formatCostLine("Generation cost", null), "Cost unavailable");
    assert.equal(
      formatCostLine("Generation cost", { output_id: "gen-1", amount: null, currency: null, status: "not_recorded" }),
      "Cost unavailable",
    );
    assert.equal(
      formatCostLine("Generation cost", { output_id: "gen-1", amount: null, currency: null, status: "unknown" }),
      "Cost unavailable",
    );
    assert.equal(
      formatCostLine("Generation cost", { output_id: "gen-1", amount: 0, currency: "USD", status: "unknown" }),
      "Cost unavailable",
    );
    assert.equal(isKnownRecordedCost({ amount: 0, status: "not_recorded" }), false);
  });

  it("keeps a repaired generation's recorded cost separate from the original", () => {
    const original = formatCostLine("Original generation cost", {
      output_id: "gen-initial",
      amount: 0.04,
      currency: "USD",
      status: "known",
    });
    const repair = formatCostLine("Repair cost", {
      output_id: "gen-repair",
      amount: 0.02,
      currency: "USD",
      status: "known",
    });
    assert.equal(original, "Original generation cost: $0.04");
    assert.equal(repair, "Repair cost: $0.02");
    assert.notEqual(original, repair);
  });
});
