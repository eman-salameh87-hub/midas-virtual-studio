import { apiBaseUrl, readSubmitEnv, type EnvReader } from "./persistClientBrief";
import type { ReferenceType } from "../types/draft";

export interface ReferenceIntakeResult {
  status: "accepted" | "rejected" | "uncertain" | "skipped";
  relevant: boolean;
  needs_confirmation: boolean;
  suggested_reference_type: Exclude<ReferenceType, "midas" | "detail"> | "detail" | null;
  department: string | null;
  category: string | null;
  subcategory: string | null;
  message: string;
}

export class AnalyzeReferenceFailure extends Error {
  readonly code: string | undefined;

  constructor(message: string, code?: string) {
    super(message);
    this.name = "AnalyzeReferenceFailure";
    this.code = code;
  }
}

export async function analyzeReferenceIntake(
  body: { libraryKey?: string | null; file?: File | null; intendedKind?: string | null },
  env: EnvReader = readSubmitEnv(),
): Promise<ReferenceIntakeResult> {
  const payload: Record<string, string | null> = {
    library_key: body.libraryKey?.trim() || null,
    content_base64: null,
    media_type: null,
    intended_kind: body.intendedKind ?? null,
  };
  if (body.file && !payload.library_key) {
    payload.content_base64 = await fileToBase64(body.file);
    payload.media_type = body.file.type || null;
  }
  const response = await fetch(`${apiBaseUrl(env)}/api/v1/reference-intake/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
  const parsed = (await response.json().catch(() => null)) as
    | { result?: ReferenceIntakeResult; error?: { code?: string; message?: string } }
    | null;
  if (!response.ok || !parsed?.result) {
    throw new AnalyzeReferenceFailure(
      parsed?.error?.message || "Image analysis failed. Retry or replace the image. It was not marked valid.",
      parsed?.error?.code,
    );
  }
  return parsed.result;
}

async function fileToBase64(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}
