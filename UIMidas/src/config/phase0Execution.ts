/** Phase-0 literals from app/contracts/job.py. Not inferred from the UIMidas brief. */

export const inputConditionOptions = [
  "clean pack shot",
  "scene",
  "partial object",
  "annotated multi-view sheet",
  "low resolution",
  "technical document",
  "spreadsheet",
  "mixed batch",
] as const;

export const productRoleOptions = ["hero", "supporting"] as const;

export const packageMemberOptions = [
  "catalogue",
  "lifestyle",
  "alternative view",
  "detail",
  "upscale",
] as const;

export const policyModeOptions = ["fidelity-locked", "creative-room"] as const;

export type InputConditionOption = (typeof inputConditionOptions)[number];
export type ProductRoleOption = (typeof productRoleOptions)[number];
export type PackageMemberOption = (typeof packageMemberOptions)[number];
export type PolicyModeOption = (typeof policyModeOptions)[number];

export interface Phase0ExecutionFields {
  source_condition: { input_condition: InputConditionOption };
  changes: {
    policy_mode: PolicyModeOption;
    allowed_changes: string[];
    protected_identity: string[];
    room_locks: string[];
    creative_variables: string[];
  };
  product_role: ProductRoleOption;
  package_members: PackageMemberOption[];
}

export function emptyExecutionDraft(): {
  inputCondition: InputConditionOption | "";
  productRole: ProductRoleOption | "";
  packageMembers: PackageMemberOption[];
  policyMode: PolicyModeOption | "";
  protectedIdentity: string;
  allowedChanges: string;
} {
  return {
    inputCondition: "",
    productRole: "",
    packageMembers: [],
    policyMode: "",
    protectedIdentity: "",
    allowedChanges: "",
  };
}

export function executionFieldsFromDraft(
  draft: ReturnType<typeof emptyExecutionDraft>,
): Phase0ExecutionFields | null {
  if (!draft.inputCondition || !draft.productRole || !draft.policyMode) return null;
  if (draft.packageMembers.length === 0) return null;
  const protectedIdentity = draft.protectedIdentity
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (protectedIdentity.length === 0) return null;
  const allowed = draft.allowedChanges
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  return {
    source_condition: { input_condition: draft.inputCondition },
    changes: {
      policy_mode: draft.policyMode,
      allowed_changes: allowed,
      protected_identity: protectedIdentity,
      room_locks: [],
      creative_variables: [],
    },
    product_role: draft.productRole,
    package_members: draft.packageMembers,
  };
}
