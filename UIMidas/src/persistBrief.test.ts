import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { collectReferenceFiles, parsePreparedExecutions, persistAndPrepareJob } from "./adapters/prepareJobFromBrief";
import { rememberLocalFile } from "./lib/references";
import { persistClientBrief, retrieveClientBrief, shouldUseMockSubmit } from "./adapters/persistClientBrief";
import { resolveJobSubmitAdapter } from "./adapters/resolveSubmitAdapter";
import { CONTRACT_VERSION } from "./contract/buildJobContract";
import { submitPreparedJob } from "./contract/submitPreparedJob";
import { mockSubmitJob } from "./adapters/mockSubmitJob";
import { createEmptyBriefItem, createEmptyDraft } from "./state/emptyDraft";
import type { ClientJobDraft, ClientReference } from "./types/draft";

function reference(groupId: string): ClientReference {
  return {
    id: "front",
    type: "product_image",
    source: "local_file",
    asset: {
      id: "front-asset",
      fileName: "front.jpg",
      mediaKind: "image",
      sizeBytes: 1200,
      localPreviewUrl: "blob:http://local/preview",
      libraryKey: null,
    },
    role: "product",
    relationship: "same_product",
    productGroupId: groupId,
    localStatus: "ready",
  };
}

function readyDraft(): ClientJobDraft {
  const draft = createEmptyDraft();
  draft.job = { kind: "new_project", newProjectMode: "one_by_one", editMode: null, savedItemId: null, singleItemRole: null };
  const item = draft.items[0] ?? createEmptyBriefItem();
  item.item = { categoryState: "automatic_unknown", department: null, category: null, subcategory: null };
  item.references.items = [reference(item.references.primaryProductGroupId)];
  item.scope.outputs = [
    { id: "life", concept: "lifestyle", otherLabel: "", views: [], proportion: null, resolution: null, variationCount: null },
  ];
  draft.items[0] = item;
  return draft;
}

const savedView = {
  brief_id: "brief-persist-1",
  owner_id: "dev-owner",
  contract_id: "dev-contract",
  revision: 1,
  brief_hash: "abc123",
  client_brief: { contractVersion: CONTRACT_VERSION },
};

describe("persist-only UIMidas submit", () => {
  it("posts only the envelope and retrieves the saved brief", async () => {
    const draft = readyDraft();
    const urls: string[] = [];
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      urls.push(`${init?.method ?? "GET"} ${url}`);
      if (init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as { client_brief?: unknown; owner_id?: unknown };
        assert.equal("owner_id" in body, false);
        assert.equal("contract_id" in body, false);
        assert.equal("revision" in body, false);
        const envelope = body.client_brief as { ownerIdentity: { value: null } };
        assert.equal(envelope.ownerIdentity.value, null);
        return new Response(JSON.stringify({ ...savedView, client_brief: body.client_brief }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify(savedView), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;
    try {
      const result = await submitPreparedJob(draft, "dev-idem-persist", draft.items[0].id, persistClientBrief);
      assert.equal(result.ok, true);
      if (!result.ok) return;
      assert.equal(result.response.mock, false);
      if (result.response.mock) return;
      assert.equal(result.response.briefId, "brief-persist-1");
      assert.equal(result.response.persisted, true);
      assert.equal(urls.some((entry) => entry.includes("/api/v1/jobs")), false);
      assert.equal(urls[0]?.startsWith("POST /api/v1/client-briefs"), true);
      assert.equal(urls[1]?.startsWith("GET /api/v1/client-briefs/brief-persist-1"), true);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("shows an actionable error and keeps the draft when identity is missing", async () => {
    const draft = readyDraft();
    const before = JSON.stringify(draft);
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response(
        JSON.stringify({
          error: {
            code: "IDENTITY_NOT_CONFIGURED",
            message: "Set MIDAS_DEV_OWNER_ID and MIDAS_DEV_CONTRACT_ID on the backend.",
            details: {},
          },
        }),
        { status: 503, headers: { "Content-Type": "application/json" } },
      )) as typeof fetch;
    try {
      const result = await submitPreparedJob(draft, "dev-idem-identity", draft.items[0].id, persistClientBrief);
      assert.equal(result.ok, false);
      if (result.ok || result.reason !== "persist-failed") throw new Error("expected persist-failed");
      assert.equal(result.code, "IDENTITY_NOT_CONFIGURED");
      assert.match(result.message, /MIDAS_DEV_OWNER_ID/);
      assert.match(result.message, /draft is unchanged/);
      assert.equal(JSON.stringify(draft), before);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("retrieveClientBrief GETs the saved brief", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      assert.equal(String(input), "/api/v1/client-briefs/brief-persist-1?owner_id=dev-owner");
      return new Response(JSON.stringify(savedView), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;
    try {
      const retrieved = await retrieveClientBrief("brief-persist-1", "dev-owner");
      assert.equal(retrieved.briefId, "brief-persist-1");
      assert.equal(retrieved.mock, false);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("keeps the mock adapter when VITE_USE_MOCK_SUBMIT is true", () => {
    assert.equal(shouldUseMockSubmit({ VITE_USE_MOCK_SUBMIT: "true" }), true);
    assert.equal(resolveJobSubmitAdapter({ VITE_USE_MOCK_SUBMIT: "true" }), mockSubmitJob);
    assert.equal(shouldUseMockSubmit({}), false);
  });

  it("does not treat persist network failure as a successful mock job", async () => {
    const draft = readyDraft();
    const before = JSON.stringify(draft);
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async () => {
      throw new TypeError("Failed to fetch");
    }) as typeof fetch;
    try {
      const result = await submitPreparedJob(draft, "dev-idem-down", draft.items[0].id, persistClientBrief);
      assert.equal(result.ok, false);
      if (result.ok || result.reason !== "persist-failed") throw new Error("expected persist-failed");
      assert.match(result.message, /Could not reach the backend/);
      assert.equal(JSON.stringify(draft), before);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("keeps the saved brief when Phase-0 mapping is unresolved", async () => {
    const draft = readyDraft();
    const before = JSON.stringify(draft);
    const originalFetch = globalThis.fetch;
    const urls: string[] = [];
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      urls.push(`${init?.method ?? "GET"} ${url}`);
      if (url.includes("/jobs") && !url.includes("client-briefs")) {
        throw new Error("must not create a Phase-0 job via POST /api/v1/jobs");
      }
      if (init?.method === "POST" && url.includes("/client-briefs/") && url.includes("/jobs")) {
        return new Response(
          JSON.stringify({
            error: {
              code: "BRIEF_MAPPING_UNRESOLVED",
              message: "unmapped",
              details: {
                brief_id: "brief-persist-1",
                issues: [
                  {
                    code: "UNRESOLVED_SOURCE_CONDITION",
                    field: "source_condition",
                    message: "UIMidas does not collect input condition.",
                  },
                ],
              },
            },
          }),
          { status: 422, headers: { "Content-Type": "application/json" } },
        );
      }
      if (init?.method === "POST") {
        return new Response(JSON.stringify({ ...savedView, client_brief: JSON.parse(String(init.body)).client_brief }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify(savedView), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;
    try {
      const contractResult = await submitPreparedJob(draft, "dev-idem-map", draft.items[0].id, persistClientBrief);
      assert.equal(contractResult.ok, true);
      if (!contractResult.ok) return;
      const prepared = await persistAndPrepareJob(contractResult.contract, draft, draft.items[0].id);
      assert.equal(prepared.persist.briefId, "brief-persist-1");
      assert.equal(prepared.job, null);
      assert.equal(prepared.mappingIssues[0]?.code, "UNRESOLVED_SOURCE_CONDITION");
      assert.equal(JSON.stringify(draft), before);
      assert.equal(urls.some((entry) => entry === "POST /api/v1/jobs"), false);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("prepares a job from the UIMidas brief without Phase-0 form fields", async () => {
    const draft = readyDraft();
    const png = Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
      "base64",
    );
    rememberLocalFile("front", new File([png], "front.jpg", { type: "image/jpeg" }));
    const originalFetch = globalThis.fetch;
    const prepareBodies: unknown[] = [];
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "POST" && url.includes("/client-briefs/") && url.includes("/jobs")) {
        prepareBodies.push(JSON.parse(String(init.body)));
        return new Response(JSON.stringify({ job_id: "job-1", generation_started: false, pre_generation_approved: false }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/jobs/job-1/status")) {
        return new Response(
          JSON.stringify({
            compile_available: true,
            generation_available: false,
            critique_available: false,
            eye_available: true,
            brain_available: true,
            stylist_available: true,
            stage: "compile",
            state: "compiled",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/jobs/job-1/compile")) {
        return new Response(JSON.stringify({ engine: { model_id: "google/gemini-3.1-flash-image", compile: {} } }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (init?.method === "POST") {
        return new Response(JSON.stringify({ ...savedView, client_brief: JSON.parse(String(init.body)).client_brief }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify(savedView), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;
    try {
      const contractResult = await submitPreparedJob(draft, "dev-idem-phase0", draft.items[0].id, persistClientBrief);
      assert.equal(contractResult.ok, true);
      if (!contractResult.ok) return;
      const prepared = await persistAndPrepareJob(contractResult.contract, draft, draft.items[0].id);
      assert.equal(prepared.job?.jobId, "job-1");
      assert.equal(prepared.executions.length, 1);
      assert.equal(prepared.executions[0]?.jobId, "job-1");
      assert.equal(prepared.mappingIssues.length, 0);
      const body = prepareBodies[0] as {
        phase0_fields_not_in_brief?: unknown;
        reference_files: { reference_id: string; media_type: string; content_base64: string }[];
      };
      assert.equal("phase0_fields_not_in_brief" in body, false);
      assert.equal(body.reference_files[0]?.reference_id, "front");
      assert.equal(body.reference_files[0]?.media_type, "PNG");
      assert.ok(body.reference_files[0]?.content_base64);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("keeps every execution from a multi-job prepare response", async () => {
    const draft = readyDraft();
    const originalFetch = globalThis.fetch;
    const statusUrls: string[] = [];
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "POST" && url.includes("/client-briefs/") && url.includes("/jobs")) {
        return new Response(
          JSON.stringify({
            job_id: "job-front",
            job_ids: ["job-front", "job-side"],
            executions: [
              {
                job_id: "job-front",
                requested_view: "front",
                image_proportions: "1:1",
                resolution: "2k",
                requested_outcomes: ["lifestyle"],
              },
              {
                job_id: "job-side",
                requested_view: "side",
                image_proportions: "1:1",
                resolution: "2k",
                requested_outcomes: ["lifestyle"],
              },
            ],
            generation_started: false,
            pre_generation_approved: false,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/status")) {
        statusUrls.push(url);
        return new Response(
          JSON.stringify({
            compile_available: true,
            generation_available: false,
            critique_available: false,
            eye_available: true,
            brain_available: true,
            stylist_available: true,
            stage: "compile",
            state: "compiled",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/compile")) {
        return new Response(JSON.stringify({ engine: { compile: {} } }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (init?.method === "POST") {
        return new Response(JSON.stringify({ ...savedView, client_brief: JSON.parse(String(init.body)).client_brief }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify(savedView), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;
    try {
      const contractResult = await submitPreparedJob(draft, "dev-idem-multi", draft.items[0].id, persistClientBrief);
      assert.equal(contractResult.ok, true);
      if (!contractResult.ok) return;
      const prepared = await persistAndPrepareJob(contractResult.contract, draft, draft.items[0].id);
      assert.equal(prepared.job?.jobId, "job-front");
      assert.equal(prepared.executions.length, 2);
      assert.equal(prepared.executions[1]?.jobId, "job-side");
      assert.equal(prepared.executions[1]?.requestedView, "side");
      assert.equal(statusUrls.every((url) => url.includes("job-front")), true);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

describe("reference bytes for prepare", () => {
  it("sends sniffed PNG bytes and skips a GIF that is not a Phase-0 image", async () => {
    const draft = readyDraft();
    const png = Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
      "base64",
    );
    rememberLocalFile("front", new File([png], "front.png", { type: "image/png" }));
    rememberLocalFile("gif", new File([Buffer.from("GIF89a")], "shot.gif", { type: "image/gif" }));
    draft.items[0].references.items.push({
      id: "gif",
      type: "product_image",
      source: "local_file",
      asset: {
        id: "gif-asset",
        fileName: "shot.gif",
        mediaKind: "image",
        sizeBytes: 6,
        localPreviewUrl: null,
        libraryKey: null,
      },
      role: "product",
      relationship: "same_product",
      productGroupId: draft.items[0].references.primaryProductGroupId,
      localStatus: "ready",
    });
    const files = await collectReferenceFiles(draft, draft.items[0].id);
    assert.equal(files.length, 1);
    assert.equal(files[0]?.reference_id, "front");
    assert.equal(files[0]?.media_type, "PNG");
    assert.ok(files[0]?.content_base64);
  });
});

describe("prepare response executions", () => {
  it("falls back to a single job_id when executions are omitted", () => {
    const parsed = parsePreparedExecutions({ job_id: "job-1" });
    assert.deepEqual(parsed, [
      { jobId: "job-1", requestedView: "", imageProportions: "", resolution: "", requestedOutcomes: [] },
    ]);
  });

  it("uses job_ids when executions are omitted", () => {
    const parsed = parsePreparedExecutions({ job_id: "job-1", job_ids: ["job-1", "job-2"] });
    assert.equal(parsed.map((row) => row.jobId).join(","), "job-1,job-2");
  });
});
