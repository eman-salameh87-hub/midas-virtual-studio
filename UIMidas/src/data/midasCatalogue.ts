export interface MidasProduct {
  id: string;
  name: string;
  sku: string;
  imageUrl: string | null;
  productUrl: string;
  sourceUrl: string;
}

export function parseMidasCatalogue(value: unknown): MidasProduct[] {
  if (!Array.isArray(value)) throw new Error("Midas catalogue is unavailable.");
  const products: MidasProduct[] = [];
  const seen = new Set<string>();
  for (const entry of value) {
    const product = parseProduct(entry);
    if (!product || seen.has(product.id)) continue;
    seen.add(product.id);
    products.push(product);
  }
  if (products.length === 0) throw new Error("Midas catalogue is unavailable.");
  return products;
}

export async function loadMidasCatalogue(): Promise<MidasProduct[]> {
  const imported = (await import("./midasProducts.json")) as { default?: unknown };
  return parseMidasCatalogue(imported.default ?? imported);
}

export function searchMidasProducts(products: readonly MidasProduct[], query: string): MidasProduct[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return [...products];
  return products.filter((product) => product.name.toLowerCase().includes(needle) || product.sku.toLowerCase().includes(needle));
}

export function safeMidasUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || url.hostname !== "midasfurniture.com") return null;
    return url.toString();
  } catch {
    return null;
  }
}

function parseProduct(value: unknown): MidasProduct | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const id = text(record.id);
  const name = text(record.name);
  const sku = text(record.sku);
  const productUrl = safeMidasUrl(text(record.productUrl));
  const sourceUrl = safeMidasUrl(text(record.sourceUrl));
  if (!id || !name || !sku || id !== sku || !productUrl || !sourceUrl) return null;
  return {
    id,
    name,
    sku,
    imageUrl: safeMidasUrl(typeof record.imageUrl === "string" ? record.imageUrl : null),
    productUrl,
    sourceUrl,
  };
}

function text(value: unknown): string {
  return typeof value === "string" ? value.replace(/<[^>]*>/g, "").trim() : "";
}
