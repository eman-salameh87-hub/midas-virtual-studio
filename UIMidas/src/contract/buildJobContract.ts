import type { NormalizedClientBrief, NormalizedPackageOutput } from "../normalization/normalizeDraft";
import { normalizeDraft } from "../normalization/normalizeDraft";
import type { ClientJobDraft, SingleItemRole } from "../types/draft";

export const PROPOSED_JOBS_ENDPOINT = "POST /api/studio/v2/jobs" as const;

/** Draft contract version. This is not a production release marker. */
export const CONTRACT_VERSION = "studio-jobs-v2-draft" as const;

export interface DevelopmentPlaceholder {
  status: "development-placeholder";
  value: null;
  note: string;
}

export interface ProposedPackage {
  itemId: string;
  productGroupId: string;
  outputs: NormalizedPackageOutput[];
}

/**
 * Proposed body for a future POST /api/studio/v2/jobs.
 * ownerIdentity, fileIds, and limits are placeholders until those systems exist.
 */
export interface ProposedJobContract {
  endpoint: typeof PROPOSED_JOBS_ENDPOINT;
  contractVersion: typeof CONTRACT_VERSION;
  idempotencyKey: string;
  ownerIdentity: DevelopmentPlaceholder;
  fileIds: DevelopmentPlaceholder;
  limits: DevelopmentPlaceholder;
  category: string | null;
  role: SingleItemRole | null;
  package: ProposedPackage[];
  brief: NormalizedClientBrief;
}

function sharedCategory(brief: NormalizedClientBrief): string | null {
  const categories = brief.items.map((item) => (item.categoryState === "specified" ? item.category ?? null : null));
  const first = categories[0];
  if (!first) return null;
  return categories.every((category) => category === first) ? first : null;
}

export function buildJobContract(
  draft: ClientJobDraft,
  idempotencyKey: string,
  activeItemId?: string,
): ProposedJobContract {
  const brief = normalizeDraft(draft, activeItemId);
  return {
    endpoint: PROPOSED_JOBS_ENDPOINT,
    contractVersion: CONTRACT_VERSION,
    idempotencyKey,
    ownerIdentity: {
      status: "development-placeholder",
      value: null,
      note: "Production owner identity is not available in this client.",
    },
    fileIds: {
      status: "development-placeholder",
      value: null,
      note: "Local files have no production file ids yet. Names stay on the brief evidence.",
    },
    limits: {
      status: "development-placeholder",
      value: null,
      note: "File and generation limits are not defined.",
    },
    category: sharedCategory(brief),
    role: draft.job.kind === "single_item" ? draft.job.singleItemRole : null,
    package: brief.items.map((item) => ({
      itemId: item.id,
      productGroupId: item.productGroupId,
      outputs: item.requestedPackage,
    })),
    brief,
  };
}
