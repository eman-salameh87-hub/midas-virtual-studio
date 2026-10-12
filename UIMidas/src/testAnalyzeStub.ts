import type { ReferenceIntakeResult } from "./adapters/analyzeReferenceIntake";

const accepted: ReferenceIntakeResult = {
  status: "accepted",
  relevant: true,
  needs_confirmation: false,
  suggested_reference_type: "product_image",
  department: "home-furniture",
  category: "home-furniture/living-rooms",
  subcategory: "home-furniture/living-rooms/sofa",
  message: "Recognized as furniture or interior product reference material.",
};

export function installAnalyzeStub(result: ReferenceIntakeResult = accepted): () => void {
  const original = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/api/v1/reference-intake/analyze")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ result }),
      } as Response;
    }
    if (typeof original === "function") return original(input, init);
    throw new Error(`unexpected fetch ${url}`);
  }) as typeof fetch;
  return () => {
    globalThis.fetch = original;
  };
}
