import { GlobalWindow } from "happy-dom";
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { MockSubmitFailure } from "./adapters/mockSubmitJob";
import { prepareProjectSubmission, submitPreparedProject } from "./contract/submitPreparedProject";
import { projectIssues } from "./lib/projectBrief";
import { sameSubmitKey } from "./contract/submitPreparedJob";
import type { ProjectBrief, ProjectScopeOutput } from "./lib/projectBrief";
import { createEmptyBriefItem } from "./state/emptyDraft";
import type { ClientReference } from "./types/draft";

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

const { createElement, useState } = await import("react");
const { createRoot } = await import("react-dom/client");
const { act } = await import("react");
const { ProjectReviewSection } = await import("./components/sections/ProjectReviewSection");

function output(concept: ProjectScopeOutput["concept"], extra: Partial<ProjectScopeOutput> = {}): ProjectScopeOutput {
  return { id: concept, concept, otherLabel: "", variationAspects: [], ...extra };
}

function brief(patch: Partial<ProjectBrief> = {}): ProjectBrief {
  const empty = createEmptyBriefItem();
  return {
    start: "product_or_collection",
    existingRoom: "",
    newStyledSpace: "",
    item: { categoryState: "automatic_unknown", department: null, category: null, subcategory: null },
    references: empty.references,
    outputs: [output("lifestyle")],
    ...patch,
  };
}

function readyReference(groupId: string, fileName: string): ClientReference {
  return {
    id: `ref-${fileName}`,
    type: "product_image",
    source: "local_file",
    asset: {
      id: `asset-${fileName}`,
      fileName,
      mediaKind: "image",
      sizeBytes: 12,
      localPreviewUrl: "blob:preview",
      libraryKey: null,
    },
    role: "product",
    relationship: "same_product",
    productGroupId: groupId,
    localStatus: "ready",
    localStatusMessage: null,
  };
}

function complete(): ProjectBrief {
  const base = brief({
    start: "existing_room",
    existingRoom: "Keep the windows and floor.",
    newStyledSpace: "A relaxed living room",
    item: {
      categoryState: "specified",
      department: "home-furniture",
      category: "home-furniture/living-rooms",
      subcategory: "home-furniture/living-rooms/sofa/sectional-sofa",
    },
    outputs: [
      output("lifestyle"),
      output("variations", { variationAspects: ["lighting", "styling"] }),
      output("others", { otherLabel: "A styled corner" }),
    ],
  });
  base.references.items = [readyReference(base.references.primaryProductGroupId, "sofa.jpg")];
  return base;
}

describe("projects submit preparation", () => {
  it("requires one ready reference and blocks uploading, failed, and missing item choices", async () => {
    const missing = projectIssues(brief());
    assert.ok(missing.some((issue) => issue.message === "No product references yet."));
    const uploading = brief();
    uploading.references.items = [{ ...readyReference(uploading.references.primaryProductGroupId, "pending.jpg"), localStatus: "uploading" }];
    const failed = brief();
    failed.references.items = [
      {
        ...readyReference(failed.references.primaryProductGroupId, "empty.jpg"),
        localStatus: "error",
        localStatusMessage: "This file is empty.",
      },
    ];
    const departmentOnly = brief({
      item: { categoryState: "specified", department: "home-furniture", category: null, subcategory: null },
    });
    departmentOnly.references.items = [readyReference(departmentOnly.references.primaryProductGroupId, "sofa.jpg")];
    assert.ok(projectIssues(uploading).some((issue) => issue.message === "A file is still being added."));
    assert.ok(projectIssues(failed).some((issue) => issue.message === "This file is empty."));
    assert.ok(projectIssues(departmentOnly).some((issue) => issue.message === "Choose a category, or mark the category as unknown."));
    assert.equal(projectIssues(uploading).some((issue) => issue.message.includes("Count")), false);

    const automatic = brief();
    automatic.references.items = [readyReference(automatic.references.primaryProductGroupId, "auto.jpg")];
    assert.equal(projectIssues(automatic).length, 0);

    const variations = complete();
    variations.outputs = [output("variations")];
    assert.equal(projectIssues(variations).some((issue) => issue.message.toLowerCase().includes("count")), false);
    assert.equal(projectIssues(variations).length, 0);

    let called = false;
    const blocked = await submitPreparedProject(brief(), "dev-idem-empty", async () => {
      called = true;
      throw new Error("should not submit");
    });
    assert.equal(blocked.ok, false);
    assert.equal(called, false);
  });

  it("refuses an incomplete brief without calling submit", async () => {
    let called = false;
    const result = await submitPreparedProject(brief({ outputs: [] }), "dev-idem-1", async () => {
      called = true;
      throw new Error("should not submit");
    });
    assert.equal(result.ok, false);
    if (!result.ok) assert.equal(result.reason, "invalid");
    assert.equal(called, false);
  });

  it("requires the Existing room and New styled space notes, and Others text", async () => {
    const room = await submitPreparedProject(brief({ start: "existing_room", existingRoom: "  " }), "dev-idem-room");
    const space = await submitPreparedProject(brief({ start: "new_styled_space", newStyledSpace: "" }), "dev-idem-space");
    const others = await submitPreparedProject(brief({ outputs: [output("others")] }), "dev-idem-others");
    const saved = await submitPreparedProject(brief({ start: "saved_project" }), "dev-idem-saved");
    assert.equal(room.ok, false);
    assert.equal(space.ok, false);
    assert.equal(others.ok, false);
    assert.equal(saved.ok, false);
    if (!room.ok && room.reason === "invalid") assert.ok(room.issues.some((issue) => issue.message === "What should stay or change?"));
    if (!space.ok && space.reason === "invalid") assert.ok(space.issues.some((issue) => issue.message === "Describe the space to create"));
    if (!others.ok && others.reason === "invalid") assert.ok(others.issues.some((issue) => issue.message === "Name the other output."));
  });

  it("allows Variations without a count and keeps Projects values beside the supported payload", async () => {
    const source = complete();
    const key = sameSubmitKey(null);
    const prepared = prepareProjectSubmission(source, key);
    const body = JSON.stringify(prepared.submission);
    assert.equal(prepared.submission.department, "home-furniture");
    assert.equal(prepared.submission.category, "home-furniture/living-rooms");
    assert.equal(prepared.submission.subcategory, "home-furniture/living-rooms/sofa/sectional-sofa");
    assert.equal(prepared.submission.productGroupId, source.references.primaryProductGroupId);
    assert.equal(prepared.submission.references[0]?.evidence?.fileName, "sofa.jpg");
    assert.equal(body.includes("blob:preview"), false);
    assert.deepEqual(
      prepared.submission.outputs.map((output) => output.concept),
      ["lifestyle", "variations", "others"],
    );
    assert.equal(prepared.submission.outputs.find((output) => output.concept === "others")?.otherLabel, "A styled corner");
    assert.equal("variationCount" in (prepared.submission.outputs[1] ?? {}), false);
    assert.equal(body.includes("variationAspects"), false);
    assert.equal(body.includes("existingRoom"), false);
    assert.equal(body.includes("newStyledSpace"), false);
    assert.equal("start" in prepared.submission, false);
    assert.equal("job" in prepared.submission, false);
    assert.equal(prepared.gaps.start, "existing_room");
    assert.equal(prepared.gaps.existingRoom, "Keep the windows and floor.");
    assert.equal(prepared.gaps.newStyledSpace, "A relaxed living room");
    assert.deepEqual(prepared.gaps.variationAspects[0]?.aspects, ["lighting", "styling"]);

    const seen: string[] = [];
    const result = await submitPreparedProject(source, key, async (submission) => {
      seen.push(submission.idempotencyKey);
      return {
        jobId: "dev-job-project",
        contractVersion: "studio-jobs-v2-draft",
        idempotencyKey: submission.idempotencyKey,
        mock: true,
      };
    });
    assert.equal(result.ok, true);
    if (result.ok) {
      assert.equal(result.response.jobId, "dev-job-project");
      assert.equal(result.prepared.gaps.start, "existing_room");
    }
    assert.deepEqual(seen, [key]);
  });

  it("reuses one idempotency key when a failed Projects submit is retried", async () => {
    const source = complete();
    const key = sameSubmitKey(null);
    let attempts = 0;
    const adapter = async (submission: { idempotencyKey: string }) => {
      attempts += 1;
      if (attempts === 1) throw new MockSubmitFailure("try again");
      return {
        jobId: "dev-job-retry",
        contractVersion: "studio-jobs-v2-draft" as const,
        idempotencyKey: submission.idempotencyKey,
        mock: true as const,
      };
    };
    const failed = await submitPreparedProject(source, key, adapter);
    assert.equal(failed.ok, false);
    if (!failed.ok) assert.equal(failed.reason, "mock-failed");
    const retryKey = sameSubmitKey(key);
    assert.equal(retryKey, key);
    const retried = await submitPreparedProject(source, retryKey, adapter);
    assert.equal(retried.ok, true);
    if (retried.ok) assert.equal(retried.response.idempotencyKey, key);
    assert.equal(attempts, 2);
  });
});

function ReviewHarness({
  source,
  adapter,
}: {
  source: ProjectBrief;
  adapter: Parameters<typeof submitPreparedProject>[2];
}) {
  const [value] = useState(source);
  return createElement(ProjectReviewSection, {
    brief: value,
    onBack: () => {},
    onEdit: () => {},
    onStartOver: () => {},
    submitAdapter: adapter,
  });
}

async function mount(node: ReturnType<typeof createElement>) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(node);
  });
  return host;
}

async function clickSubmit(host: ParentNode) {
  const button = [...host.querySelectorAll("button")].find((entry) => entry.textContent === "Submit job" || entry.textContent === "Retry");
  assert.ok(button);
  await act(async () => {
    button.dispatchEvent(new dom.MouseEvent("click", { bubbles: true }) as unknown as MouseEvent);
  });
}

describe("projects submit lifecycle", () => {
  it("shows preparing, then the development job result", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const host = await mount(
      createElement(ReviewHarness, {
        source: complete(),
        adapter: async (submission) => {
          await gate;
          return {
            jobId: "dev-job-ready",
            contractVersion: "studio-jobs-v2-draft",
            idempotencyKey: submission.idempotencyKey,
            mock: true,
          };
        },
      }),
    );
    await clickSubmit(host);
    assert.match(host.textContent ?? "", /Preparing job/);
    await act(async () => {
      release();
      await gate;
    });
    assert.match(host.textContent ?? "", /Job created/);
    assert.match(host.textContent ?? "", /dev-job-ready/);
    assert.match(host.textContent ?? "", /studio-jobs-v2-draft/);
    assert.equal(host.textContent?.includes("Submit job"), false);
  });

  it("shows the error and retries with the same key", async () => {
    const keys: string[] = [];
    let attempts = 0;
    const host = await mount(
      createElement(ReviewHarness, {
        source: complete(),
        adapter: async (submission) => {
          attempts += 1;
          keys.push(submission.idempotencyKey);
          if (attempts === 1) throw new MockSubmitFailure("try again");
          return {
            jobId: "dev-job-after-retry",
            contractVersion: "studio-jobs-v2-draft",
            idempotencyKey: submission.idempotencyKey,
            mock: true,
          };
        },
      }),
    );
    await clickSubmit(host);
    await act(async () => {
      await Promise.resolve();
    });
    assert.match(host.textContent ?? "", /Unable to submit job/);
    await clickSubmit(host);
    await act(async () => {
      await Promise.resolve();
    });
    assert.match(host.textContent ?? "", /Job created/);
    assert.match(host.textContent ?? "", /dev-job-after-retry/);
    assert.equal(keys[0], keys[1]);
  });
});
