import { categoryById, departmentById } from "../config/options";
import type { BriefItem } from "../types/draft";

export function itemDisplayName(briefItem: BriefItem, index: number): string {
  const fallback = `Item ${index + 1}`;
  if (briefItem.item.categoryState === "automatic_unknown") return fallback;
  const department = departmentById(briefItem.item.department);
  const category = categoryById(briefItem.item.department, briefItem.item.category);
  const subcategory = category?.subcategories.find((entry) => entry.id === briefItem.item.subcategory);
  return subcategory?.label ?? category?.label ?? department?.label ?? fallback;
}
