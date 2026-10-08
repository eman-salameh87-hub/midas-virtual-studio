/**
 * Refresh the local Midas Qatar catalogue.
 *
 * Run: npm run scrape:midas
 *
 * Reads the public English catalogue from https://midasfurniture.com/graphql
 * and writes product records whose pages live on https://midasfurniture.com/qtr_en/.
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const endpoint = "https://midasfurniture.com/graphql";
const storefront = "https://midasfurniture.com/qtr_en/";
const pageSize = 100;
const output = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src/data/midasProducts.json");

const query = `query Catalogue($page: Int!, $pageSize: Int!) {
  products(search: "", pageSize: $pageSize, currentPage: $page) {
    total_count
    items {
      sku
      name
      url_key
      url_suffix
      small_image { url }
    }
  }
}`;

const products = [];
const seen = new Set();
let page = 1;
let total = Infinity;

while ((page - 1) * pageSize < total) {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      Store: "en",
    },
    body: JSON.stringify({ query, variables: { page, pageSize } }),
  });
  if (!response.ok) throw new Error(`Midas catalogue request failed (${response.status}) on page ${page}.`);
  const body = await response.json();
  if (body.errors?.length) throw new Error(body.errors.map((error) => error.message).join("; "));
  const result = body.data?.products;
  if (!result || !Array.isArray(result.items)) throw new Error(`Midas catalogue page ${page} did not include products.`);
  total = result.total_count;
  if (!Number.isFinite(total) || total < 1) throw new Error("Midas catalogue did not report any products.");
  for (const item of result.items) {
    const product = toProduct(item);
    if (!product || seen.has(product.id)) continue;
    seen.add(product.id);
    products.push(product);
  }
  if (result.items.length === 0) break;
  page += 1;
}

products.sort((a, b) => a.name.localeCompare(b.name) || a.sku.localeCompare(b.sku));
await mkdir(path.dirname(output), { recursive: true });
await writeFile(output, `${JSON.stringify(products, null, 2)}\n`);
console.log(`Wrote ${products.length} products to ${output}`);

function toProduct(item) {
  const sku = clean(item?.sku);
  const name = clean(item?.name);
  const urlKey = clean(item?.url_key);
  if (!sku || !name || !urlKey) return null;
  const suffix = clean(item?.url_suffix) || ".html";
  const productUrl = safeUrl(`${storefront}${urlKey}${suffix}`);
  if (!productUrl) return null;
  return {
    id: sku,
    name,
    sku,
    imageUrl: safeUrl(item?.small_image?.url ?? null),
    productUrl,
    sourceUrl: productUrl,
  };
}

function clean(value) {
  if (typeof value !== "string") return "";
  return value.replace(/<[^>]*>/g, "").trim();
}

function safeUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(String(value).replace(/&amp;/g, "&"));
    if (url.protocol !== "https:" || url.hostname !== "midasfurniture.com") return null;
    return url.toString();
  } catch {
    return null;
  }
}
