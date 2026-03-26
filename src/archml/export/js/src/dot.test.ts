// Copyright 2026 ArchML Contributors
// SPDX-License-Identifier: Apache-2.0

// Golden-file tests: JS buildDot output must match the same .dot snapshots
// checked by the Python test suite (test_dot_sync.py).  If these tests fail
// while the Python tests pass, the two implementations have drifted.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { buildDot } from "./dot";
import { defaultLayoutConfig, type VizDiagram } from "./types";

const FIXTURES_DIR = resolve(
  fileURLToPath(new URL(".", import.meta.url)),
  "../../../../../tests/dot_sync",
);

const SCENARIOS = ["flat", "with_terminals", "nested"] as const;

describe("buildDot golden files", () => {
  for (const name of SCENARIOS) {
    it(`matches snapshot: ${name}`, () => {
      const diagram = JSON.parse(
        readFileSync(resolve(FIXTURES_DIR, `${name}.viz.json`), "utf-8"),
      ) as VizDiagram;

      const actual = buildDot(diagram, defaultLayoutConfig());
      const expected = readFileSync(resolve(FIXTURES_DIR, `${name}.dot`), "utf-8");

      expect(actual).toBe(expected);
    });
  }
});
