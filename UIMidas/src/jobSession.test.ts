import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { GlobalWindow } from "happy-dom";
import { clearJobSession, loadJobSession, saveJobSession, sessionExecutions } from "./lib/jobSession";
import { emptyExecutionDraft, executionFieldsFromDraft } from "./config/phase0Execution";

const dom = new GlobalWindow({ url: "http://localhost/" });
Object.assign(globalThis, { localStorage: dom.localStorage });

describe("job session pointer", () => {
  it("round-trips a brief and job pointer through localStorage", () => {
    clearJobSession();
    saveJobSession({
      briefId: "brief-1",
      ownerId: "owner-1",
      contractId: "contract-1",
      revision: 1,
      jobId: "job-1",
      mappingIssues: [],
      preGenerationApproved: false,
    });
    const loaded = loadJobSession();
    assert.equal(loaded?.briefId, "brief-1");
    assert.equal(loaded?.jobId, "job-1");
    assert.equal(sessionExecutions(loaded!).length, 1);
    assert.equal(sessionExecutions(loaded!)[0]?.jobId, "job-1");
    clearJobSession();
    assert.equal(loadJobSession(), null);
  });

  it("round-trips every execution from a multi-job prepare", () => {
    clearJobSession();
    saveJobSession({
      briefId: "brief-1",
      ownerId: "owner-1",
      contractId: "contract-1",
      revision: 1,
      jobId: "job-front",
      mappingIssues: [],
      executions: [
        {
          jobId: "job-front",
          requestedView: "front",
          imageProportions: "1:1",
          resolution: "2k",
          requestedOutcomes: ["lifestyle"],
        },
        {
          jobId: "job-side",
          requestedView: "side",
          imageProportions: "1:1",
          resolution: "2k",
          requestedOutcomes: ["lifestyle"],
        },
      ],
    });
    const loaded = loadJobSession();
    assert.equal(sessionExecutions(loaded!).length, 2);
    assert.equal(sessionExecutions(loaded!)[1]?.jobId, "job-side");
    assert.equal(sessionExecutions(loaded!)[1]?.requestedView, "side");
    clearJobSession();
  });
});

describe("Phase-0 execution fields", () => {
  it("does not invent mappings from an empty draft", () => {
    assert.equal(executionFieldsFromDraft(emptyExecutionDraft()), null);
  });

  it("returns caller-supplied Phase-0 fields only when every required decision is present", () => {
    const fields = executionFieldsFromDraft({
      inputCondition: "clean pack shot",
      productRole: "hero",
      packageMembers: ["lifestyle"],
      policyMode: "fidelity-locked",
      protectedIdentity: "product identity",
      allowedChanges: "",
    });
    assert.equal(fields?.product_role, "hero");
    assert.deepEqual(fields?.package_members, ["lifestyle"]);
    assert.deepEqual(fields?.changes.protected_identity, ["product identity"]);
  });
});
