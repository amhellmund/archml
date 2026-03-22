#!/usr/bin/env node
// Copyright 2026 ArchML Contributors
// SPDX-License-Identifier: Apache-2.0
//
// ELK layout runner.
// Reads an ELK JSON graph from stdin, computes layout, writes result to stdout.
//
// Usage:  node elk_runner.js  < input.json  > output.json
//
// Requires elkjs:  npm install -g elkjs  (or local node_modules/elkjs)

"use strict";

let ELK;
try {
    ELK = require("elkjs");
} catch (_) {
    // Try common global npm locations
    const paths = [
        "/usr/lib/node_modules/elkjs",
        "/usr/local/lib/node_modules/elkjs",
    ];
    let found = false;
    for (const p of paths) {
        try { ELK = require(p); found = true; break; } catch (_2) { /* skip */ }
    }
    if (!found) {
        process.stderr.write(
            "elkjs not found. Install it with: npm install -g elkjs\n"
        );
        process.exit(1);
    }
}

const elk = new ELK();

let raw = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => { raw += chunk; });
process.stdin.on("end", () => {
    let graph;
    try {
        graph = JSON.parse(raw);
    } catch (e) {
        process.stderr.write("Failed to parse input JSON: " + e.message + "\n");
        process.exit(1);
    }
    elk.layout(graph)
        .then(result => { process.stdout.write(JSON.stringify(result)); })
        .catch(err => {
            process.stderr.write("ELK layout error: " + err.message + "\n");
            process.exit(1);
        });
});
