import { MockSubmitFailure, type MockSubmitResponse } from "../adapters/mockSubmitJob";
import { CONTRACT_VERSION } from "./buildJobContract";
import { createId } from "../lib/ids";
import { isReadyProjectReference, projectIssues, type ProjectBrief, type ProjectIssue } from "../lib/projectBrief";
import type { ClientReference, OutputConcept, VariationAspect } from "../types/draft";
import type { NormalizedReference } from "../normalization/normalizeDraft";

export interface PreparedProjectOutput {
  concept: OutputConcept;
  otherLabel?: string;
}

/** Fields that already exist on the current brief item and package output shapes. */
export interface PreparedProjectSubmission {
  idempotencyKey: string;
  categoryState: ProjectBrief["item"]["categoryState"];
  department?: string;
  category?: string;
  subcategory?: string;
  productGroupId: string;
  references: NormalizedReference[];
  outputs: PreparedProjectOutput[];
}

/** Projects values kept through Review. They are not part of the submission body. */
export interface ProjectSubmissionGaps {
  start: ProjectBrief["start"];
  existingRoom: string;
  newStyledSpace: string;
  variationAspects: { outputId: string; aspects: VariationAspect[] }[];
}

export interface PreparedProject {
  submission: PreparedProjectSubmission;
  gaps: ProjectSubmissionGaps;
}

export type ProjectSubmitAdapter = (submission: PreparedProjectSubmission) => Promise<MockSubmitResponse>;

export type ProjectSubmitOutcome =
  | { ok: true; response: MockSubmitResponse; prepared: PreparedProject }
  | { ok: false; reason: "invalid"; issues: ProjectIssue[] }
  | { ok: false; reason: "mock-failed"; message: string; prepared: PreparedProject };

export function prepareProjectSubmission(brief: ProjectBrief, idempotencyKey: string): PreparedProject {
  const submission: PreparedProjectSubmission = {
    idempotencyKey,
    categoryState: brief.item.categoryState,
    productGroupId: brief.references.primaryProductGroupId,
    references: brief.references.items.filter(isReadyProjectReference).map(normalizeReference),
    outputs: brief.outputs.map(normalizeOutput),
  };
  if (brief.item.department) submission.department = brief.item.department;
  if (brief.item.category) submission.category = brief.item.category;
  if (brief.item.subcategory) submission.subcategory = brief.item.subcategory;
  return {
    submission,
    gaps: {
      start: brief.start,
      existingRoom: brief.existingRoom,
      newStyledSpace: brief.newStyledSpace,
      variationAspects: brief.outputs
        .filter((output) => output.concept === "variations")
        .map((output) => ({ outputId: output.id, aspects: output.variationAspects })),
    },
  };
}

/**
 * Development stand-in for a future Projects submit.
 * It does not call the network or the Manual job endpoint.
 */
export async function mockSubmitProject(submission: PreparedProjectSubmission): Promise<MockSubmitResponse> {
  if (!submission.idempotencyKey) throw new MockSubmitFailure("The submit is missing an idempotency key.");
  return {
    jobId: `dev-job-${createId()}`,
    contractVersion: CONTRACT_VERSION,
    idempotencyKey: submission.idempotencyKey,
    mock: true,
  };
}

export async function submitPreparedProject(
  brief: ProjectBrief,
  idempotencyKey: string,
  adapter: ProjectSubmitAdapter = mockSubmitProject,
): Promise<ProjectSubmitOutcome> {
  const issues = projectIssues(brief);
  if (issues.length > 0) return { ok: false, reason: "invalid", issues };
  const prepared = prepareProjectSubmission(brief, idempotencyKey);
  try {
    const response = await adapter(prepared.submission);
    return { ok: true, response, prepared };
  } catch (error) {
    const message = error instanceof MockSubmitFailure || error instanceof Error ? error.message : "The mock submit did not complete.";
    return { ok: false, reason: "mock-failed", message, prepared };
  }
}

function normalizeReference(reference: ClientReference): NormalizedReference {
  const asset = reference.asset;
  return {
    id: reference.id,
    type: reference.type,
    source: reference.source,
    role: reference.role,
    relationship: reference.relationship,
    productGroupId: reference.productGroupId,
    evidence: asset
      ? {
          fileName: asset.fileName,
          mediaKind: asset.mediaKind,
          sizeBytes: asset.sizeBytes,
          libraryKey: asset.libraryKey,
        }
      : null,
  };
}

function normalizeOutput(output: ProjectBrief["outputs"][number]): PreparedProjectOutput {
  const normalized: PreparedProjectOutput = { concept: output.concept };
  const otherLabel = output.otherLabel.trim();
  if (otherLabel) normalized.otherLabel = otherLabel;
  return normalized;
}
