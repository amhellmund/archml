// Copyright 2026 ArchML Contributors
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";

import { renderTypeRef } from "./viewer";
import type {
  ArchFileJson,
  InterfaceDefJson,
  TypeDefJson,
  TypeRefJson,
} from "./types";

function typeDef(name: string, fields: TypeDefJson["fields"], description: string | null = null): TypeDefJson {
  return { name, fields, title: null, description, tags: [], line: 0 };
}

function ifaceDef(name: string, fields: InterfaceDefJson["fields"], description: string | null = null): InterfaceDefJson {
  return {
    name,
    version: null,
    fields,
    title: null,
    description,
    tags: [],
    variants: [],
    qualified_name: name,
    line: 0,
  };
}

function field(name: string, type: TypeRefJson) {
  return { name, type, description: null, schema_ref: null, line: 0 };
}

function emptyFile(): ArchFileJson {
  return {
    imports: [],
    enums: [],
    types: [],
    interfaces: [],
    components: [],
    systems: [],
    users: [],
    connects: [],
  };
}

describe("renderTypeRef — Url<Schema>", () => {
  it("renders a Url wrapper around a type schema with nested members", () => {
    const address = typeDef(
      "Address",
      [field("street", { kind: "primitive", primitive: "String" })],
      "A postal address resource.",
    );
    const files: Record<string, ArchFileJson> = { f: { ...emptyFile(), types: [address] } };

    const html = renderTypeRef({ kind: "url", schema_name: "Address" }, files, new Set());

    expect(html).toContain(">Url<");
    // Schema name is shown and navigable.
    expect(html).toContain("Address");
    // Nested members are rendered.
    expect(html).toContain("street");
    // Description is rendered.
    expect(html).toContain("A postal address resource.");
  });

  it("expands an interface schema with its members and description", () => {
    const profile = ifaceDef(
      "Profile",
      [field("name", { kind: "primitive", primitive: "String" })],
      "A public profile resource.",
    );
    const files: Record<string, ArchFileJson> = { f: { ...emptyFile(), interfaces: [profile] } };

    const html = renderTypeRef({ kind: "url", schema_name: "Profile" }, files, new Set());

    expect(html).toContain("Profile");
    // Interface schemas must show nested members, not just the bare name.
    expect(html).toContain("name");
    expect(html).toContain("A public profile resource.");
  });

  it("shows just the schema name when the schema is unresolved", () => {
    const html = renderTypeRef({ kind: "url", schema_name: "Missing" }, {}, new Set());
    expect(html).toContain("Missing");
    // No members can be resolved, so no field rows are rendered.
    expect(html).not.toContain("archml-type-field");
  });

  it("collapses recursive Url schemas via the visited set", () => {
    const node = typeDef("Node", [field("next", { kind: "url", schema_name: "Node" })]);
    const files: Record<string, ArchFileJson> = { f: { ...emptyFile(), types: [node] } };

    const html = renderTypeRef({ kind: "url", schema_name: "Node" }, files, new Set());

    expect(html).toContain("archml-type-recursive");
  });
});
