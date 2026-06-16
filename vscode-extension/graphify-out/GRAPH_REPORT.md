# Graph Report - vscode-extension  (2026-06-16)

## Corpus Check
- 5 files · ~734 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 99 nodes · 103 edges · 8 communities (7 shown, 1 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `4857b0fc`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]

## God Nodes (most connected - your core abstractions)
1. `repository` - 12 edges
2. `compilerOptions` - 8 edges
3. `ArchmlFoldingRangeProvider` - 4 edges
4. `1` - 4 edges
5. `2` - 4 edges
6. `entity-keyword` - 4 edges
7. `variant` - 4 edges
8. `generic-type` - 4 edges
9. `port-ref` - 4 edges
10. `captures` - 4 edges

## Surprising Connections (you probably didn't know these)
- None detected - all connections are within the same source files.

## Import Cycles
- None detected.

## Communities (8 total, 1 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (23): activationEvents, categories, contributes, grammars, languages, dependencies, @vscode/vsce, description (+15 more)

### Community 1 - "Community 1"
Cohesion: 0.10
Nodes (21): match, name, match, name, match, name, match, name (+13 more)

### Community 2 - "Community 2"
Cohesion: 0.13
Nodes (17): name, name, name, captures, match, 1, 2, 3 (+9 more)

### Community 3 - "Community 3"
Cohesion: 0.22
Nodes (10): name, 0, begin, beginCaptures, end, endCaptures, name, patterns (+2 more)

### Community 4 - "Community 4"
Cohesion: 0.20
Nodes (9): compilerOptions, lib, module, outDir, rootDir, sourceMap, strict, target (+1 more)

### Community 6 - "Community 6"
Cohesion: 0.33
Nodes (5): fileTypes, name, patterns, $schema, scopeName

### Community 7 - "Community 7"
Cohesion: 0.67
Nodes (3): match, name, control-keyword

## Knowledge Gaps
- **59 isolated node(s):** `name`, `displayName`, `description`, `repository`, `license` (+54 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `repository` connect `Community 1` to `Community 2`, `Community 3`, `Community 6`, `Community 7`?**
  _High betweenness centrality (0.283) - this node is a cross-community bridge._
- **Why does `description` connect `Community 3` to `Community 1`?**
  _High betweenness centrality (0.095) - this node is a cross-community bridge._
- **Why does `port-ref` connect `Community 2` to `Community 1`?**
  _High betweenness centrality (0.060) - this node is a cross-community bridge._
- **What connects `name`, `displayName`, `description` to the rest of the system?**
  _59 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.08333333333333333 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.09523809523809523 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.1323529411764706 - nodes in this community are weakly interconnected._