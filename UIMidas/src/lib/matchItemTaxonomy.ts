import { itemTaxonomyGroups, type TaxonomyDepartment } from "../config/options";

export interface TaxonomyMatch {
  department: string | null;
  category: string | null;
  subcategory: string | null;
}

const visibleTaxonomy: TaxonomyDepartment[] = itemTaxonomyGroups.flatMap((group) => group.options);

export function constrainTaxonomy(match: TaxonomyMatch): TaxonomyMatch {
  const department = visibleTaxonomy.find((entry) => entry.id === match.department) ?? null;
  const category = department?.categories.find((entry) => entry.id === match.category) ?? null;
  const subcategory = category?.subcategories.find((entry) => entry.id === match.subcategory) ?? null;
  return {
    department: department?.id ?? null,
    category: category?.id ?? null,
    subcategory: subcategory?.id ?? null,
  };
}

function fieldEquals(value: string | null | undefined, id: string, label: string): boolean {
  if (!value) return false;
  const raw = value.trim();
  return raw === id || raw.toLowerCase() === label.toLowerCase();
}

export function resolveTaxonomy(match: TaxonomyMatch): TaxonomyMatch {
  const byId = constrainTaxonomy(match);
  if (byId.department) return byId;
  const department =
    visibleTaxonomy.find((entry) => fieldEquals(match.department, entry.id, entry.label) && entry.type === "department") ??
    visibleTaxonomy.find((entry) => fieldEquals(match.department, entry.id, entry.label)) ??
    null;
  let resolvedDepartment = department;
  let resolvedCategory = department?.categories.find((entry) => fieldEquals(match.category, entry.id, entry.label)) ?? null;
  if (!resolvedDepartment && match.category) {
    for (const dept of visibleTaxonomy) {
      const found = dept.categories.find((entry) => fieldEquals(match.category, entry.id, entry.label));
      if (!found) continue;
      if (!resolvedDepartment || dept.type === "department") {
        resolvedDepartment = dept;
        resolvedCategory = found;
        if (dept.type === "department") break;
      }
    }
  }
  const subcategory =
    resolvedCategory?.subcategories.find((entry) => fieldEquals(match.subcategory, entry.id, entry.label)) ?? null;
  const resolved = constrainTaxonomy({
    department: resolvedDepartment?.id ?? null,
    category: resolvedCategory?.id ?? null,
    subcategory: subcategory?.id ?? null,
  });
  if (resolved.department) return resolved;
  const hay = [match.department, match.category, match.subcategory].filter(Boolean).join(" ");
  return hay ? matchItemTaxonomy(hay) : { department: null, category: null, subcategory: null };
}

export function matchItemTaxonomy(name: string, productUrl = ""): TaxonomyMatch {
  const hay = `${name} ${productUrl}`.toLowerCase();
    let best: { score: number } & TaxonomyMatch = { score: 0, department: null, category: null, subcategory: null };
  for (const dept of visibleTaxonomy) {
    const kindBonus = dept.type === "department" ? 1000 : 0;
    for (const category of dept.categories) {
      for (const sub of category.subcategories) {
        if (labelHits(hay, sub.label, sub.id)) {
          const score = kindBonus + 300 + sub.label.length;
          if (score > best.score) best = { score, department: dept.id, category: category.id, subcategory: sub.id };
        }
      }
      if (labelHits(hay, category.label, category.id)) {
        const score = kindBonus + 200 + category.label.length;
        if (score > best.score) best = { score, department: dept.id, category: category.id, subcategory: null };
      }
    }
    if (labelHits(hay, dept.label, dept.id)) {
      const score = kindBonus + 100 + dept.label.length;
      if (score > best.score) best = { score, department: dept.id, category: null, subcategory: null };
    }
  }
  return constrainTaxonomy(best);
}

function labelHits(hay: string, label: string, nodeId: string): boolean {
  const text = label.toLowerCase().trim();
  if (text.length < 4) return false;
  if (hay.includes(text)) return true;
  const slug = nodeId.split("/").pop()?.replaceAll("-", " ") ?? "";
  return slug.length >= 4 && hay.replaceAll("-", " ").includes(slug);
}
