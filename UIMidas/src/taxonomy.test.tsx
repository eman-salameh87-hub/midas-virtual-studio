import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { ItemSection } from "./components/sections/ItemSection";
import { categoryById, departmentById, itemTaxonomy, itemTaxonomyGroups } from "./config/options";
import { DraftProvider } from "./state/DraftProvider";

function categoryLabels(rootLabel: string) {
  const root = itemTaxonomy.find((entry) => entry.label === rootLabel);
  assert.ok(root);
  return root.categories.map((category) => category.label);
}

function subcategoryLabels(rootLabel: string, categoryLabel: string) {
  const root = itemTaxonomy.find((entry) => entry.label === rootLabel);
  assert.ok(root);
  const category = root.categories.find((entry) => entry.label === categoryLabel);
  assert.ok(category);
  return category.subcategories.map((subcategory) => subcategory.label);
}

describe("extracted item taxonomy", () => {
  it("groups real departments apart from website sections", () => {
    assert.deepEqual(
      itemTaxonomyGroups.map((group) => group.label),
      ["Departments", "Other website sections"],
    );
    assert.deepEqual(
      itemTaxonomyGroups[0]?.options.map((option) => option.label),
      ["Home Furniture", "Office Furniture", "Accessories", "Outdoor Furniture"],
    );
    assert.equal(
      itemTaxonomyGroups[0]?.options.every((option) => option.type === "department"),
      true,
    );
    assert.equal(
      itemTaxonomyGroups[1]?.options.every((option) => option.type === "website_section"),
      true,
    );
    assert.equal(itemTaxonomyGroups[1]?.options.some((option) => option.label === "Home Furniture"), false);
  });

  it("keeps Home Furniture → Living Rooms as the extracted values", () => {
    assert.deepEqual(categoryLabels("Home Furniture"), [
      "Living Rooms",
      "Bedrooms",
      "Dining Rooms",
      "Mattresses",
      "Recliners",
      "Sauder",
      "Kids Room",
    ]);
    assert.deepEqual(subcategoryLabels("Home Furniture", "Living Rooms"), [
      "Bench and Ottoman",
      "TV Units",
      "Cabinets",
      "Chairs",
      "Chairs / Swivel Chairs",
      "Shelves",
      "Consoles",
      "Stands",
      "Shoe Cabinets",
      "Chaise Lounge",
      "Sofas",
      "Sofas / Sectional Sofas",
      "Sofas / Sofa Sets",
      "Sofas / Sofas and Love Seats",
      "Sofas / Sofa Bed",
      "Sofas / classic",
      "Sofas / 2-Seater Sofa",
      "Sofas / 3-Seater Sofa",
      "Sofas / Single Seater Sofa",
      "Sofas / 4-Seater Sofa",
      "Tables",
      "Tables / Table Sets",
      "Tables / Center Tables",
      "Tables / Side Table",
      "Tables / Nested Tables",
      "Privacy screen",
    ]);
  });

  it("keeps Home Furniture → Bedrooms, including wardrobe sets", () => {
    assert.deepEqual(subcategoryLabels("Home Furniture", "Bedrooms"), [
      "King Size Bedroom Sets",
      "King Size Bedroom Sets / Bedroom Set With Wardrobe",
      "King Size Bedroom Sets / Bedroom Set Without Wardrobe",
      "King Size Bedroom Sets / King Size Bedroom Sets without Chest",
      "Beds",
      "Night Stands",
      "Dressers",
      "Chest of Drawers",
      "Wardrobes",
      "Queen Size Bedroom Sets",
    ]);
  });

  it("keeps Office Furniture → Office Chairs", () => {
    assert.deepEqual(subcategoryLabels("Office Furniture", "Office Chairs"), [
      "Visitor Chairs",
      "Mesh Chairs",
      "Executive Office Chairs",
    ]);
  });

  it("keeps Accessories → Lighting", () => {
    assert.deepEqual(categoryLabels("Accessories"), [
      "Kitchen and Dining",
      "Soft Furnishings",
      "Bathroom",
      "Lighting",
      "Wall Decor",
      "Decor Accessories",
      "Table Accessories",
    ]);
    assert.deepEqual(subcategoryLabels("Accessories", "Lighting"), [
      "Table Lamps",
      "Hanging and Ceiling Lamps",
      "Floor Lamps",
      "Wall Lamps",
    ]);
  });

  it("keeps Ashley Homestore → Living Rooms", () => {
    assert.deepEqual(subcategoryLabels("Ashley Homestore", "Living Rooms"), [
      "Sofas",
      "Sofas / Sofa Sets",
      "Sofas / Sectional Sofas",
      "Sofas / Sofa Beds",
      "Sofas / 2 seater sofa",
      "Sofas / 3 seater sofa",
      "Sofas / Single Seater Sofa",
      "Chairs",
      "Console",
      "TV Units",
      "Recliners",
      "Bench and Ottoman",
      "Shelves",
      "Tables",
      "Tables / Center Tables",
      "Tables / End Tables",
      "Tables / Table Sets",
      "Tables / SIDE TABLEs",
    ]);
  });

  it("keeps New arrivals · category view → Home Furniture", () => {
    assert.deepEqual(subcategoryLabels("New arrivals · category view", "Home Furniture"), [
      "Living Rooms",
      "Bedrooms",
      "Dining Rooms",
      "Recliners",
      "Gaming Tables & Chairs",
    ]);
  });

  it("leaves an empty root without categories", () => {
    const root = departmentById("new-arrival");
    assert.equal(root?.label, "New Arrival");
    assert.equal(root?.type, "website_section");
    assert.deepEqual(root?.categories, []);
  });

  it("leaves an empty category without sub-categories", () => {
    const category = categoryById("office-furniture", "office-furniture/office-sofas");
    assert.equal(category?.label, "Office Sofas");
    assert.deepEqual(category?.subcategories, []);
  });

  it("still resolves the earlier stored Furniture sample", () => {
    const department = departmentById("furniture");
    const category = categoryById("furniture", "seating");
    assert.equal(department?.label, "Furniture");
    assert.equal(category?.label, "Seating");
    assert.equal(category?.subcategories.find((entry) => entry.id === "lounge-chairs")?.label, "Lounge chairs");
  });

  it("offers Automatic from references before the grouped roots", () => {
    const html = renderToStaticMarkup(
      <DraftProvider>
        <ItemSection onBack={() => {}} onContinue={() => {}} />
      </DraftProvider>,
    );
    const department = html.slice(html.indexOf(">Department<"), html.indexOf(">Category<"));
    assert.match(department, /<option value="" selected="">Automatic from references<\/option>/);
    assert.ok(department.indexOf("Automatic from references") < department.indexOf("Home Furniture"));
    assert.match(department, /<optgroup label="Departments">/);
    assert.match(department, /<optgroup label="Other website sections">/);
  });
});
