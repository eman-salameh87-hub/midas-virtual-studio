import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  approvePreGeneration,
  resetCritiqueGuardsForTests,
  runCritiqueForGeneration,
  shouldAutoCritique,
  startGeneration,
  startRepair,
} from "./adapters/jobWorkflow";

describe("job workflow adapter", () => {
  it("posts pre-generation approval without starting generate", async () => {
    const originalFetch = globalThis.fetch;
    const urls: string[] = [];
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      urls.push(`${init?.method ?? "GET"} ${String(input)}`);
      return new Response(JSON.stringify({ compile_available: true, generation_available: false }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;
    try {
      await approvePreGeneration("job-1", "owner-1", 1);
      assert.equal(urls[0], "POST /api/v1/jobs/job-1/generate/approve?owner_id=owner-1&revision=1");
      assert.equal(urls.some((entry) => entry.includes("/generate?") || entry.endsWith("/generate")), false);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("posts generate with the compiled model id after approval", async () => {
    const originalFetch = globalThis.fetch;
    let body: unknown;
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      body = JSON.parse(String(init?.body));
      assert.match(String(input), /\/api\/v1\/jobs\/job-1\/generate\?/);
      return new Response(JSON.stringify({ generation_available: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;
    try {
      await startGeneration("job-1", "owner-1", 1, "google/gemini-3.1-flash-image");
      assert.deepEqual(body, { model_id: "google/gemini-3.1-flash-image" });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("auto-critiques a completed generation with an available output", () => {
    resetCritiqueGuardsForTests();
    assert.equal(
      shouldAutoCritique(
        {
          state: "generated",
          generation_output_available: true,
          generation_output_id: "gen-1",
          critique_matches_generation: false,
        },
        "job-1",
      ),
      true,
    );
  });

  it("does not auto-critique failed generations, missing outputs, or a current critique", () => {
    resetCritiqueGuardsForTests();
    assert.equal(
      shouldAutoCritique(
        {
          state: "failed",
          generation_output_available: true,
          generation_output_id: "gen-1",
          critique_matches_generation: false,
        },
        "job-1",
      ),
      false,
    );
    assert.equal(
      shouldAutoCritique(
        {
          state: "generated",
          generation_output_available: false,
          generation_output_id: "gen-1",
          critique_matches_generation: false,
        },
        "job-1",
      ),
      false,
    );
    assert.equal(
      shouldAutoCritique(
        {
          state: "generated",
          generation_output_available: true,
          generation_output_id: "gen-1",
          critique_matches_generation: true,
        },
        "job-1",
      ),
      false,
    );
  });

  it("coalesces duplicate critique posts for the same generation", async () => {
    resetCritiqueGuardsForTests();
    const originalFetch = globalThis.fetch;
    let posts = 0;
    globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "POST") {
        posts += 1;
        await new Promise((resolve) => setTimeout(resolve, 20));
      }
      return new Response(JSON.stringify({ critique: { assessment: { overall_result: "pass" } } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;
    try {
      await Promise.all([
        runCritiqueForGeneration("job-1", "owner-1", 1, "gen-1"),
        runCritiqueForGeneration("job-1", "owner-1", 1, "gen-1"),
      ]);
      assert.equal(posts, 1);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("posts repair with the compiled model id", async () => {
    const originalFetch = globalThis.fetch;
    let body: unknown;
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      body = JSON.parse(String(init?.body));
      assert.match(String(input), /\/api\/v1\/jobs\/job-1\/repair\?/);
      return new Response(JSON.stringify({ repair: { status: "completed" } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;
    try {
      await startRepair("job-1", "owner-1", 1, "google/gemini-3.1-flash-image");
      assert.deepEqual(body, { model_id: "google/gemini-3.1-flash-image" });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
