import { GlobalWindow } from "happy-dom";
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createElement } from "react";
import { resetCritiqueGuardsForTests } from "./adapters/jobWorkflow";
import { JobWorkspace } from "./components/jobs/JobWorkspace";

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
  URL: dom.URL,
  localStorage: dom.localStorage,
  IS_REACT_ACT_ENVIRONMENT: true,
});

const { createRoot } = await import("react-dom/client");
const { act } = await import("react");

async function mount(node: ReturnType<typeof createElement>) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(node);
  });
  return {
    host,
    async unmount() {
      await act(async () => {
        root.unmount();
      });
      host.remove();
    },
  };
}

function buttonNamed(host: ParentNode, name: string) {
  const found = [...host.querySelectorAll("button")].find((button) =>
    (button.textContent ?? "").replace(/\s+/g, " ").includes(name),
  );
  assert.ok(found, `Missing button ${name}`);
  return found as HTMLButtonElement;
}

describe("job workspace", () => {
  resetCritiqueGuardsForTests();
  it("shows mapping blockers and does not offer generate when no job exists", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response(
        JSON.stringify({
          brief_id: "brief-1",
          owner_id: "owner-1",
          contract_id: "contract-1",
          revision: 1,
          brief_hash: "hash-1",
          client_brief: {},
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      )) as typeof fetch;
    try {
      const view = await mount(
        createElement(JobWorkspace, {
          session: {
            briefId: "brief-1",
            ownerId: "owner-1",
            contractId: "contract-1",
            revision: 1,
            jobId: null,
            mappingIssues: [
              {
                code: "UNRESOLVED_SOURCE_CONDITION",
                field: "source_condition",
                message: "Choose an input condition.",
              },
            ],
          },
          onLeave: () => {},
        }),
      );
      assert.match(view.host.textContent ?? "", /UNRESOLVED_SOURCE_CONDITION/);
      assert.equal((view.host.textContent ?? "").includes("Generate image"), false);
      await view.unmount();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("keeps Generate image disabled until pre-generation approval", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/status")) {
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
            hold: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/compile")) {
        return new Response(
          JSON.stringify({ engine: { model_id: "google/gemini-3.1-flash-image", compile: { model_id: "google/gemini-3.1-flash-image" } } }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(
        JSON.stringify({
          brief_id: "brief-1",
          owner_id: "owner-1",
          contract_id: "contract-1",
          revision: 1,
          brief_hash: "hash-1",
          client_brief: {},
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }) as typeof fetch;
    try {
      const view = await mount(
        createElement(JobWorkspace, {
          session: {
            briefId: "brief-1",
            ownerId: "owner-1",
            contractId: "contract-1",
            revision: 1,
            jobId: "job-1",
            mappingIssues: [],
          },
          onLeave: () => {},
        }),
      );
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 20));
      });
      const generate = buttonNamed(view.host, "Generate image");
      assert.equal(generate.disabled, true);
      const approve = buttonNamed(view.host, "Approve generation");
      assert.equal(approve.disabled, false);
      await view.unmount();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("shows a panel for each execution", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/status") || url.includes("/compile")) {
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
            hold: null,
            engine: { model_id: "google/gemini-3.1-flash-image", compile: { model_id: "google/gemini-3.1-flash-image" } },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(
        JSON.stringify({
          brief_id: "brief-1",
          owner_id: "owner-1",
          contract_id: "contract-1",
          revision: 1,
          brief_hash: "hash-1",
          client_brief: {},
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }) as typeof fetch;
    try {
      const view = await mount(
        createElement(JobWorkspace, {
          session: {
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
          },
          onLeave: () => {},
        }),
      );
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 30));
      });
      assert.match(view.host.textContent ?? "", /job-front/);
      assert.match(view.host.textContent ?? "", /job-side/);
      assert.match(view.host.textContent ?? "", /front/);
      assert.match(view.host.textContent ?? "", /side/);
      const generateButtons = [...view.host.querySelectorAll("button")].filter((button) =>
        (button.textContent ?? "").includes("Generate image"),
      );
      assert.equal(generateButtons.length, 2);
      await view.unmount();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("keeps a healthy execution visible when another status poll fails", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/jobs/job-fail/status")) {
        return new Response(
          JSON.stringify({ error: { code: "JOB_NOT_FOUND", message: "Job status could not be loaded." } }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/status") || url.includes("/compile")) {
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
            hold: null,
            engine: { compile: {} },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(
        JSON.stringify({
          brief_id: "brief-1",
          owner_id: "owner-1",
          contract_id: "contract-1",
          revision: 1,
          brief_hash: "hash-1",
          client_brief: {},
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }) as typeof fetch;
    try {
      const view = await mount(
        createElement(JobWorkspace, {
          session: {
            briefId: "brief-1",
            ownerId: "owner-1",
            contractId: "contract-1",
            revision: 1,
            jobId: "job-ok",
            mappingIssues: [],
            executions: [
              {
                jobId: "job-ok",
                requestedView: "front",
                imageProportions: "1:1",
                resolution: "2k",
                requestedOutcomes: ["lifestyle"],
              },
              {
                jobId: "job-fail",
                requestedView: "side",
                imageProportions: "1:1",
                resolution: "2k",
                requestedOutcomes: ["lifestyle"],
              },
            ],
          },
          onLeave: () => {},
        }),
      );
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 40));
      });
      assert.match(view.host.textContent ?? "", /job-ok/);
      assert.match(view.host.textContent ?? "", /job-fail/);
      assert.match(view.host.textContent ?? "", /Job status could not be loaded/);
      const generateButtons = [...view.host.querySelectorAll("button")].filter((button) =>
        (button.textContent ?? "").includes("Generate image"),
      );
      assert.equal(generateButtons.length, 2);
      assert.equal(generateButtons[0]?.disabled, true);
      const approveButtons = [...view.host.querySelectorAll("button")].filter((button) =>
        (button.textContent ?? "").includes("Approve generation"),
      );
      assert.equal(approveButtons.some((button) => !button.disabled), true);
      await view.unmount();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("shows each execution image only after that job reports generation", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/jobs/job-front/status")) {
        return new Response(
          JSON.stringify({
            compile_available: true,
            generation_available: true,
            critique_available: false,
            eye_available: true,
            brain_available: true,
            stylist_available: true,
            stage: "generate",
            state: "generated",
            hold: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/jobs/job-side/status")) {
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
            hold: null,
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
      return new Response(
        JSON.stringify({
          brief_id: "brief-1",
          owner_id: "owner-1",
          contract_id: "contract-1",
          revision: 1,
          brief_hash: "hash-1",
          client_brief: {},
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }) as typeof fetch;
    try {
      const view = await mount(
        createElement(JobWorkspace, {
          session: {
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
                preGenerationApproved: true,
              },
              {
                jobId: "job-side",
                requestedView: "side",
                imageProportions: "1:1",
                resolution: "2k",
                requestedOutcomes: ["lifestyle"],
                preGenerationApproved: true,
              },
            ],
          },
          onLeave: () => {},
        }),
      );
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 40));
      });
      const images = [...view.host.querySelectorAll("img")];
      assert.equal(images.length, 1);
      assert.match(images[0]?.getAttribute("src") ?? "", /jobs\/job-front\/generate\/image/);
      assert.match(view.host.textContent ?? "", /not started/);
      await view.unmount();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  const generatedSession = {
    briefId: "brief-1",
    ownerId: "owner-1",
    contractId: "contract-1",
    revision: 1,
    jobId: "job-1",
    mappingIssues: [],
    executions: [
      {
        jobId: "job-1",
        requestedView: "front",
        imageProportions: "1:1",
        resolution: "2k",
        requestedOutcomes: ["lifestyle"],
        preGenerationApproved: true,
      },
    ],
  };

  function jsonOk(body: unknown) {
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }

  it("does not show Repair after a passing critique", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/status")) {
        return jsonOk({
          compile_available: true,
          generation_available: true,
          generation_output_available: true,
          critique_available: true,
          critique_overall_result: "pass",
          critique_matches_generation: true,
          repair_eligible: false,
          repair_available: false,
          repair_count: 0,
          repair_limit: 2,
          approved: false,
          stage: "critique",
          state: "review_pending",
          hold: null,
        });
      }
      if (url.includes("/critique")) {
        return jsonOk({
          critique: {
            assessment: { overall_result: "pass", summary: "locks preserved", findings: [] },
          },
        });
      }
      if (url.includes("/compile")) return jsonOk({ engine: { compile: {} } });
      return jsonOk({ brief_id: "brief-1", owner_id: "owner-1", contract_id: "contract-1", revision: 1, brief_hash: "h", client_brief: {} });
    }) as typeof fetch;
    try {
      const view = await mount(createElement(JobWorkspace, { session: generatedSession, onLeave: () => {} }));
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 40));
      });
      assert.match(view.host.textContent ?? "", /Critique passed/);
      assert.equal((view.host.textContent ?? "").includes("Repair required"), false);
      const repair = [...view.host.querySelectorAll("button")].find((button) =>
        (button.textContent ?? "").includes("Repair"),
      );
      assert.equal(repair, undefined);
      const approve = buttonNamed(view.host, "Approve candidate");
      assert.equal(approve.disabled, false);
      await view.unmount();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("shows Repair when the backend marks repair eligible", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/status")) {
        return jsonOk({
          compile_available: true,
          generation_available: true,
          generation_output_available: true,
          critique_available: true,
          critique_overall_result: "repair_required",
          critique_matches_generation: true,
          repair_eligible: true,
          repair_available: false,
          repair_count: 0,
          repair_limit: 2,
          approved: false,
          stage: "critique",
          state: "ready",
          hold: null,
        });
      }
      if (url.includes("/critique")) {
        return jsonOk({
          critique: {
            assessment: {
              overall_result: "repair_required",
              summary: "Geometry/construction failed; repair is required.",
              findings: [
                {
                  dimension: "geometry",
                  result: "fail",
                  observation: "visible construction does not match",
                  expected: "preserve geometry",
                },
              ],
            },
          },
        });
      }
      if (url.includes("/compile")) return jsonOk({ engine: { compile: {} } });
      return jsonOk({ brief_id: "brief-1", owner_id: "owner-1", contract_id: "contract-1", revision: 1, brief_hash: "h", client_brief: {} });
    }) as typeof fetch;
    try {
      const view = await mount(createElement(JobWorkspace, { session: generatedSession, onLeave: () => {} }));
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 40));
      });
      assert.match(view.host.textContent ?? "", /Repair required/);
      assert.match(view.host.textContent ?? "", /visible construction does not match/);
      const repair = buttonNamed(view.host, "Repair");
      assert.equal(repair.disabled, false);
      const approve = buttonNamed(view.host, "Approve candidate");
      assert.equal(approve.disabled, true);
      await view.unmount();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("posts repair then critique and shows the new image after success", async () => {
    resetCritiqueGuardsForTests();
    const originalFetch = globalThis.fetch;
    const calls: string[] = [];
    let repaired = false;
    let critiquedAfterRepair = false;
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push(`${method} ${url}`);
      if (method === "POST" && url.includes("/repair")) {
        repaired = true;
        return jsonOk({ repair: { status: "completed", plan: { action: "fresh_render", hold_reasons: [] } } });
      }
      if (method === "POST" && url.includes("/critique")) {
        critiquedAfterRepair = repaired;
        return jsonOk({
          critique: { assessment: { overall_result: "pass", summary: "locks preserved", findings: [] } },
        });
      }
      if (url.includes("/status")) {
        return jsonOk({
          compile_available: true,
          generation_available: true,
          generation_output_available: true,
          generation_output_id: repaired ? "gen-repair" : "gen-initial",
          generation_cost: repaired
            ? { output_id: "gen-repair", amount: 0.02, currency: "USD", status: "known" }
            : { output_id: "gen-initial", amount: 0.04, currency: "USD", status: "known" },
          initial_generation_cost: repaired
            ? { output_id: "gen-initial", amount: 0.04, currency: "USD", status: "known" }
            : null,
          repair_generation_cost: repaired
            ? { output_id: "gen-repair", amount: 0.02, currency: "USD", status: "known" }
            : null,
          generation_cost_total: repaired
            ? { output_id: null, amount: 0.06, currency: "USD", status: "known" }
            : null,
          critique_available: true,
          critique_overall_result: repaired && critiquedAfterRepair ? "pass" : "repair_required",
          critique_matches_generation: repaired ? critiquedAfterRepair : true,
          repair_eligible: !repaired,
          repair_available: repaired,
          repair_count: repaired ? 1 : 0,
          repair_limit: 2,
          approved: false,
          stage: "critique",
          state: "ready",
          hold: null,
        });
      }
      if (url.includes("/critique")) {
        return jsonOk({
          critique: {
            assessment: {
              overall_result: repaired ? "pass" : "repair_required",
              summary: repaired ? "locks preserved" : "needs repair",
              findings: repaired
                ? []
                : [{ dimension: "geometry", result: "fail", observation: "drift", expected: "lock" }],
            },
          },
        });
      }
      if (url.includes("/repair")) {
        return jsonOk({ repair: { status: repaired ? "completed" : "planned", plan: { hold_reasons: [] } } });
      }
      if (url.includes("/compile")) return jsonOk({ engine: { compile: { model_id: "google/gemini-3.1-flash-image" } } });
      return jsonOk({ brief_id: "brief-1", owner_id: "owner-1", contract_id: "contract-1", revision: 1, brief_hash: "h", client_brief: {} });
    }) as typeof fetch;
    try {
      const view = await mount(createElement(JobWorkspace, { session: generatedSession, onLeave: () => {} }));
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 40));
      });
      const repair = buttonNamed(view.host, "Repair");
      await act(async () => {
        repair.click();
        await new Promise((resolve) => setTimeout(resolve, 80));
      });
      assert.equal(calls.some((entry) => entry.startsWith("POST ") && entry.includes("/repair")), true);
      assert.equal(calls.some((entry) => entry.startsWith("POST ") && entry.includes("/critique")), true);
      const images = [...view.host.querySelectorAll("img")];
      assert.equal(images.length, 1);
      assert.match(images[0]?.getAttribute("src") ?? "", /jobs\/job-1\/generate\/image/);
      assert.match(view.host.textContent ?? "", /Generation cost: \$0\.02/);
      assert.match(view.host.textContent ?? "", /Original generation cost: \$0\.04/);
      assert.match(view.host.textContent ?? "", /Repair cost: \$0\.02/);
      await view.unmount();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("does not show a new image or success after a held repair", async () => {
    const originalFetch = globalThis.fetch;
    const calls: string[] = [];
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push(`${method} ${url}`);
      if (method === "POST" && url.includes("/repair")) {
        return jsonOk({
          repair: {
            status: "hold",
            plan: { action: "hold", hold_reasons: ["repair did not complete"] },
          },
        });
      }
      if (url.includes("/status")) {
        return jsonOk({
          compile_available: true,
          generation_available: true,
          generation_output_available: false,
          critique_available: true,
          critique_overall_result: "repair_required",
          critique_matches_generation: false,
          repair_eligible: false,
          repair_available: true,
          repair_count: 1,
          repair_limit: 2,
          approved: false,
          stage: "repair",
          state: "hold",
          hold: { status: "hold", reasons: ["repair did not complete"] },
        });
      }
      if (url.includes("/critique")) {
        return jsonOk({
          critique: {
            assessment: {
              overall_result: "repair_required",
              summary: "needs repair",
              findings: [{ dimension: "geometry", result: "fail", observation: "drift", expected: "lock" }],
            },
          },
        });
      }
      if (url.includes("/repair")) {
        return jsonOk({
          repair: { status: "hold", plan: { action: "hold", hold_reasons: ["repair did not complete"] } },
        });
      }
      if (url.includes("/compile")) return jsonOk({ engine: { compile: {} } });
      return jsonOk({ brief_id: "brief-1", owner_id: "owner-1", contract_id: "contract-1", revision: 1, brief_hash: "h", client_brief: {} });
    }) as typeof fetch;
    try {
      const view = await mount(createElement(JobWorkspace, { session: generatedSession, onLeave: () => {} }));
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 40));
      });
      assert.equal(view.host.querySelectorAll("img").length, 0);
      assert.match(view.host.textContent ?? "", /Repair hold/);
      assert.equal((view.host.textContent ?? "").includes("Critique passed"), false);
      assert.equal(calls.some((entry) => entry.startsWith("POST ") && entry.includes("/critique")), false);
      await view.unmount();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("hides Repair when the repair limit is exhausted", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/status")) {
        return jsonOk({
          compile_available: true,
          generation_available: true,
          generation_output_available: true,
          critique_available: true,
          critique_overall_result: "repair_required",
          critique_matches_generation: true,
          repair_eligible: false,
          repair_available: true,
          repair_count: 2,
          repair_limit: 2,
          approved: false,
          stage: "critique",
          state: "ready",
          hold: null,
        });
      }
      if (url.includes("/critique")) {
        return jsonOk({
          critique: {
            assessment: {
              overall_result: "repair_required",
              summary: "still failing",
              findings: [{ dimension: "geometry", result: "fail", observation: "drift", expected: "lock" }],
            },
          },
        });
      }
      if (url.includes("/repair")) {
        return jsonOk({ repair: { status: "completed", plan: { hold_reasons: [] } } });
      }
      if (url.includes("/compile")) return jsonOk({ engine: { compile: {} } });
      return jsonOk({ brief_id: "brief-1", owner_id: "owner-1", contract_id: "contract-1", revision: 1, brief_hash: "h", client_brief: {} });
    }) as typeof fetch;
    try {
      const view = await mount(createElement(JobWorkspace, { session: generatedSession, onLeave: () => {} }));
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 40));
      });
      assert.match(view.host.textContent ?? "", /limit reached/);
      const repair = [...view.host.querySelectorAll("button")].find((button) =>
        (button.textContent ?? "").trim() === "Repair",
      );
      assert.equal(repair, undefined);
      const approve = buttonNamed(view.host, "Approve candidate");
      assert.equal(approve.disabled, true);
      await view.unmount();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("keeps owner approval and release gated after critique pass", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/status")) {
        return jsonOk({
          compile_available: true,
          generation_available: true,
          generation_output_available: true,
          critique_available: true,
          critique_overall_result: "pass",
          critique_matches_generation: true,
          repair_eligible: false,
          approved: false,
          releasable: false,
          review_status: "review_pending",
          stage: "critique",
          state: "review_pending",
          hold: null,
        });
      }
      if (url.includes("/critique")) {
        return jsonOk({ critique: { assessment: { overall_result: "pass", summary: "ok", findings: [] } } });
      }
      if (url.includes("/compile")) return jsonOk({ engine: { compile: {} } });
      return jsonOk({ brief_id: "brief-1", owner_id: "owner-1", contract_id: "contract-1", revision: 1, brief_hash: "h", client_brief: {} });
    }) as typeof fetch;
    try {
      const view = await mount(createElement(JobWorkspace, { session: generatedSession, onLeave: () => {} }));
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 40));
      });
      const approve = buttonNamed(view.host, "Approve candidate");
      const release = buttonNamed(view.host, "Release");
      assert.equal(approve.disabled, false);
      assert.equal(release.disabled, true);
      await view.unmount();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("automatically posts critique after a successful generation", async () => {
    resetCritiqueGuardsForTests();
    const originalFetch = globalThis.fetch;
    const calls: string[] = [];
    let critiqued = false;
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push(`${method} ${url}`);
      if (method === "POST" && url.includes("/critique")) {
        critiqued = true;
        return jsonOk({
          critique: { assessment: { overall_result: "pass", summary: "locks preserved", findings: [] } },
        });
      }
      if (url.includes("/status")) {
        return jsonOk({
          compile_available: true,
          generation_available: true,
          generation_output_available: true,
          generation_output_id: "gen-1",
          generation_cost: { output_id: "gen-1", amount: 0.101968, currency: "USD", status: "known" },
          critique_available: critiqued,
          critique_overall_result: critiqued ? "pass" : null,
          critique_matches_generation: critiqued,
          repair_eligible: false,
          approved: false,
          stage: critiqued ? "critique" : "generate",
          state: "ready",
          hold: null,
        });
      }
      if (url.includes("/critique")) {
        return jsonOk({
          critique: { assessment: { overall_result: "pass", summary: "locks preserved", findings: [] } },
        });
      }
      if (url.includes("/compile")) return jsonOk({ engine: { compile: {} } });
      return jsonOk({ brief_id: "brief-1", owner_id: "owner-1", contract_id: "contract-1", revision: 1, brief_hash: "h", client_brief: {} });
    }) as typeof fetch;
    try {
      const view = await mount(createElement(JobWorkspace, { session: generatedSession, onLeave: () => {} }));
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 80));
      });
      assert.equal(calls.filter((entry) => entry.startsWith("POST ") && entry.includes("/critique")).length, 1);
      assert.match(view.host.textContent ?? "", /Checking image|Critique passed|pass/);
      assert.match(view.host.textContent ?? "", /Generation cost: \$0\.101968/);
      assert.equal((view.host.textContent ?? "").includes("Run critique"), false);
      const approve = buttonNamed(view.host, "Approve candidate");
      assert.equal(approve.disabled, false);
      await view.unmount();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("does not post duplicate critique on remount while the same generation is current", async () => {
    resetCritiqueGuardsForTests();
    const originalFetch = globalThis.fetch;
    const posts: string[] = [];
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (method === "POST" && url.includes("/critique")) {
        posts.push(url);
        return jsonOk({
          critique: { assessment: { overall_result: "pass", summary: "ok", findings: [] } },
        });
      }
      if (url.includes("/status")) {
        return jsonOk({
          compile_available: true,
          generation_available: true,
          generation_output_available: true,
          generation_output_id: "gen-same",
          critique_available: false,
          critique_matches_generation: false,
          stage: "generate",
          state: "ready",
          hold: null,
        });
      }
      if (url.includes("/compile")) return jsonOk({ engine: { compile: {} } });
      return jsonOk({ brief_id: "brief-1", owner_id: "owner-1", contract_id: "contract-1", revision: 1, brief_hash: "h", client_brief: {} });
    }) as typeof fetch;
    try {
      const first = await mount(createElement(JobWorkspace, { session: generatedSession, onLeave: () => {} }));
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 80));
      });
      await first.unmount();
      const second = await mount(createElement(JobWorkspace, { session: generatedSession, onLeave: () => {} }));
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 80));
      });
      assert.equal(posts.length, 1);
      await second.unmount();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("posts critique for a newer generation when a stale critique exists", async () => {
    resetCritiqueGuardsForTests();
    const originalFetch = globalThis.fetch;
    const posts: string[] = [];
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (method === "POST" && url.includes("/critique")) {
        posts.push(url);
        return jsonOk({
          critique: { assessment: { overall_result: "pass", summary: "ok", findings: [] } },
        });
      }
      if (url.includes("/status")) {
        return jsonOk({
          compile_available: true,
          generation_available: true,
          generation_output_available: true,
          generation_output_id: "gen-new",
          critique_available: true,
          critique_overall_result: "repair_required",
          critique_matches_generation: false,
          stage: "generate",
          state: "ready",
          hold: null,
        });
      }
      if (url.includes("/critique")) {
        return jsonOk({
          critique: {
            assessment: {
              overall_result: "repair_required",
              generation_output_id: "gen-old",
              findings: [],
            },
          },
        });
      }
      if (url.includes("/compile")) return jsonOk({ engine: { compile: {} } });
      return jsonOk({ brief_id: "brief-1", owner_id: "owner-1", contract_id: "contract-1", revision: 1, brief_hash: "h", client_brief: {} });
    }) as typeof fetch;
    try {
      const view = await mount(createElement(JobWorkspace, { session: generatedSession, onLeave: () => {} }));
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 80));
      });
      assert.equal(posts.length, 1);
      await view.unmount();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("does not auto-critique a failed generation or a missing output", async () => {
    resetCritiqueGuardsForTests();
    const originalFetch = globalThis.fetch;
    const posts: string[] = [];
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (method === "POST") posts.push(`${method} ${url}`);
      if (url.includes("/jobs/job-fail/status")) {
        return jsonOk({
          compile_available: true,
          generation_available: true,
          generation_output_available: false,
          generation_output_id: null,
          state: "failed",
          stage: "generate",
          hold: null,
        });
      }
      if (url.includes("/jobs/job-1/status")) {
        return jsonOk({
          compile_available: true,
          generation_available: true,
          generation_output_available: false,
          generation_output_id: "gen-missing",
          critique_matches_generation: false,
          state: "generated",
          stage: "generate",
          hold: null,
        });
      }
      if (url.includes("/compile")) return jsonOk({ engine: { compile: {} } });
      return jsonOk({ brief_id: "brief-1", owner_id: "owner-1", contract_id: "contract-1", revision: 1, brief_hash: "h", client_brief: {} });
    }) as typeof fetch;
    try {
      const view = await mount(
        createElement(JobWorkspace, {
          session: {
            ...generatedSession,
            executions: [
              generatedSession.executions[0],
              { ...generatedSession.executions[0], jobId: "job-fail", requestedView: "side" },
            ],
          },
          onLeave: () => {},
        }),
      );
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 80));
      });
      assert.equal(posts.some((entry) => entry.includes("/critique")), false);
      assert.equal((view.host.textContent ?? "").includes("Checking image"), false);
      await view.unmount();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("keeps Approve candidate disabled until the current critique passes", async () => {
    resetCritiqueGuardsForTests();
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/status")) {
        return jsonOk({
          compile_available: true,
          generation_available: true,
          generation_output_available: true,
          generation_output_id: "gen-1",
          critique_available: true,
          critique_overall_result: "repair_required",
          critique_matches_generation: true,
          repair_eligible: true,
          approved: false,
          stage: "critique",
          state: "ready",
          hold: null,
        });
      }
      if (url.includes("/critique")) {
        return jsonOk({
          critique: {
            assessment: { overall_result: "repair_required", summary: "needs repair", findings: [] },
          },
        });
      }
      if (url.includes("/compile")) return jsonOk({ engine: { compile: {} } });
      return jsonOk({ brief_id: "brief-1", owner_id: "owner-1", contract_id: "contract-1", revision: 1, brief_hash: "h", client_brief: {} });
    }) as typeof fetch;
    try {
      const view = await mount(createElement(JobWorkspace, { session: generatedSession, onLeave: () => {} }));
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 40));
      });
      assert.equal(buttonNamed(view.host, "Approve candidate").disabled, true);
      await view.unmount();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("shows a recoverable critique error without an automatic retry loop", async () => {
    resetCritiqueGuardsForTests();
    const originalFetch = globalThis.fetch;
    let posts = 0;
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (method === "POST" && url.includes("/critique")) {
        posts += 1;
        return new Response(JSON.stringify({ error: { code: "CRITIQUE_FAILED", message: "provider failed" } }), {
          status: 502,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/status")) {
        return jsonOk({
          compile_available: true,
          generation_available: true,
          generation_output_available: true,
          generation_output_id: "gen-fail-critique",
          critique_available: false,
          critique_matches_generation: false,
          stage: "generate",
          state: "ready",
          hold: null,
        });
      }
      if (url.includes("/compile")) return jsonOk({ engine: { compile: {} } });
      return jsonOk({ brief_id: "brief-1", owner_id: "owner-1", contract_id: "contract-1", revision: 1, brief_hash: "h", client_brief: {} });
    }) as typeof fetch;
    try {
      const view = await mount(createElement(JobWorkspace, { session: generatedSession, onLeave: () => {} }));
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 120));
      });
      assert.equal(posts, 1);
      assert.match(view.host.textContent ?? "", /Critique could not be completed/);
      const retry = buttonNamed(view.host, "Retry critique");
      assert.equal(retry.disabled, false);
      await view.unmount();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("shows Cost unavailable when the backend did not record a generation cost", async () => {
    resetCritiqueGuardsForTests();
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/status")) {
        return jsonOk({
          compile_available: true,
          generation_available: true,
          generation_output_available: true,
          generation_output_id: "gen-1",
          generation_cost: { output_id: "gen-1", amount: null, currency: null, status: "not_recorded" },
          critique_available: true,
          critique_overall_result: "pass",
          critique_matches_generation: true,
          approved: false,
          stage: "critique",
          state: "ready",
          hold: null,
        });
      }
      if (url.includes("/critique")) {
        return jsonOk({ critique: { assessment: { overall_result: "pass", summary: "ok", findings: [] } } });
      }
      if (url.includes("/compile")) return jsonOk({ engine: { compile: {} } });
      return jsonOk({ brief_id: "brief-1", owner_id: "owner-1", contract_id: "contract-1", revision: 1, brief_hash: "h", client_brief: {} });
    }) as typeof fetch;
    try {
      const view = await mount(createElement(JobWorkspace, { session: generatedSession, onLeave: () => {} }));
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 40));
      });
      assert.match(view.host.textContent ?? "", /Cost unavailable/);
      assert.equal((view.host.textContent ?? "").includes("$0"), false);
      await view.unmount();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
