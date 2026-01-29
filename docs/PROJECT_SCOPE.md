# ArchML - Project Scope

## Problem Statement

Software architects struggle to keep architecture documentation current. Frequent tool switches (ArchiMate, Enterprise Architect, etc.) create friction, and visual-only tools disconnect architecture from the codebase. The result: architecture docs decay, teams lose context, and architects lose oversight of progress.

## Vision

A text-based DSL that lets architects define high-level architecture in files that live alongside code. The tooling reads these definitions, validates consistency, and produces navigable visual views — accessible via a web browser or embedded in Sphinx documentation.

The DSL covers the range from high-level context down to the point where detailed design is better served by UML diagrams. It is not a replacement for UML, but a complement that fills the gap between informal diagrams and detailed design.

## Architecture Domains

### 1. Functional Architecture

Hierarchical decomposition of the system, inspired by the C4 model:

- **Contexts** — bounded domains or business capabilities
- **Systems** — independently deployable units within a context
- **Components** — internal building blocks of a system
- **Interfaces** — contracts between components or systems (APIs, events, protocols)

### 2. Behavioral Architecture

Control flow and interaction between components at runtime:

- Sequences of calls or messages between components
- Triggering conditions and data flow direction
- Abstracted behavioral views (not full UML sequence diagrams, but enough to show how parts interact)

### 3. Deployment Architecture

Mapping of logical components to technology and infrastructure:

- Deployment nodes (servers, containers, cloud services)
- Component-to-node assignment
- Technology annotations (language, framework, runtime)

## Key Design Principles

| Principle | Description |
|---|---|
| **Text-first** | Architecture is defined in plain text files (`.archml` or similar) stored in the repository next to code and documentation. |
| **Model-based** | A single model produces multiple views. Define once, visualize from many angles. |
| **Consistency checking** | The tooling validates the model: dangling references, missing interfaces, orphaned components. |
| **Navigable views** | Visual output supports drill-down (full system to subsystem), filtering, and aspect-focused views. |
| **Web-based viewer** | A browser-based interface for interactive exploration of the architecture. |
| **Sphinx integration** | Optional embedding of architecture views into Sphinx documentation. |
| **Framework-agnostic** | The DSL and tooling are not tied to a specific programming language or framework. |

## Landscape Analysis

Three open-source projects address overlapping aspects of this problem space.

### Structurizr (C4 DSL)

- **What it is**: The reference tooling for the C4 model. A custom DSL defines a workspace containing a model and views. Multiple visualization levels (System Landscape, System Context, Container, Component) are generated from a single model.
- **Strengths**: Purpose-built for architecture-as-code. First-class support for dynamic views (behavioral) and deployment views. Manual layout control in the web UI. Export to PlantUML, Mermaid, and other formats. Sphinx integration via Kroki or CLI export pipeline. Mature (~2016), active maintenance.
- **Limitations**: Fixed to C4 vocabulary (no custom element types). Strict naming uniqueness constraints. Lite edition is single-user only. Export fidelity is inconsistent across formats. No nested groups.
- **Relevance to ArchML**: Structurizr validates the core idea — model-based, text-first architecture works. Its limitations (rigid vocabulary, no custom types, export gaps) point to where ArchML can differentiate.

### Mermaid

- **What it is**: A general-purpose diagramming tool using text syntax. Supports flowcharts, sequence diagrams, state diagrams, ER diagrams, Gantt charts, and an experimental `architecture-beta` diagram type.
- **Strengths**: Massive adoption (~76k GitHub stars). Native rendering in GitHub, GitLab, Notion, Confluence. Excellent Sphinx integration via `sphinxcontrib-mermaid`. Zero-setup for Markdown-based documentation.
- **Limitations**: No model abstraction — each diagram is standalone. No drill-down or multi-level views from a shared model. Architecture diagram support is beta and limited. Auto-layout only, no manual positioning. Not architecture-specific.
- **Relevance to ArchML**: Mermaid is a strong rendering target (export ArchML views to Mermaid syntax for embedding) but not a substitute for a model-based architecture tool. Its ubiquity in documentation toolchains makes it a valuable integration point.

### LikeC4

- **What it is**: A modern, C4-inspired architecture-as-code tool with a custom DSL. Unlike Structurizr, it allows user-defined element types and arbitrary nesting depth.
- **Strengths**: Customizable vocabulary (define your own element kinds). Real-time hot-reload dev server. Click-through drill-down between views. React/Web Component embedding for custom sites. Dynamic views in both diagram and sequence style. First-class deployment model. MIT licensed.
- **Limitations**: No SVG export (PNG only). Auto-layout only. Younger ecosystem with fewer integrations. No built-in documentation embedding. No direct Sphinx plugin.
- **Relevance to ArchML**: LikeC4 is the closest existing project to the ArchML vision. Its customizable vocabulary and flexible nesting are directly aligned with what ArchML aims for. Key gaps (no Sphinx integration, limited export) represent opportunities.

### Comparative Matrix

| Capability | Structurizr | Mermaid | LikeC4 | ArchML (Target) |
|---|---|---|---|---|
| Model-based (one model, many views) | Yes | No | Yes | Yes |
| Custom element types | No | No | Yes | Yes |
| Functional decomposition | C4 fixed levels | Manual | Any depth | Any depth |
| Behavioral views | Dynamic views | Sequence diagrams | Dynamic + sequence | Control flow views |
| Deployment views | First-class | Beta | First-class | First-class |
| Web-based viewer | Yes | Via renderers | Yes (dev server) | Yes |
| Drill-down navigation | Yes | No | Yes | Yes |
| Sphinx integration | Via Kroki/export | Native plugin | Export only | Native (goal) |
| Consistency checking | Partial | No | Partial | First-class (goal) |
| Lives next to code | Yes | Yes | Yes | Yes |

## Feasibility Assessment

**The project is feasible.** The landscape confirms strong demand for text-based architecture tooling, and existing tools validate the core approach. The specific combination of goals — custom vocabulary, consistency checking, web viewer, and native Sphinx integration — is not fully served by any single existing tool.

### What existing tools prove works

- Text-based DSLs for architecture are practical and adopted (Structurizr, LikeC4)
- Model-based multi-view generation is the right abstraction (vs. Mermaid's diagram-per-file)
- Web-based interactive viewers with drill-down are achievable (Structurizr Lite, LikeC4 dev server)
- Sphinx integration is viable through export pipelines or rendering services (Kroki, sphinxcontrib-mermaid)

### Where ArchML can differentiate

1. **First-class consistency checking** — Go beyond basic validation. Check for dangling references, unused interfaces, components without deployment targets, and architectural constraint violations.
2. **Native Sphinx integration** — Not an afterthought export pipeline, but a Sphinx extension that reads `.archml` files directly and renders views inline.
3. **Flexible vocabulary with constraints** — Allow custom element types (like LikeC4) but add the ability to define structural rules (e.g., "a microservice must expose at least one interface").
4. **Unified three-domain model** — Functional, behavioral, and deployment architecture in a single coherent model with cross-domain traceability.

### Risks and open questions

| Risk | Mitigation |
|---|---|
| DSL design is hard to get right | Start with a minimal subset. Iterate based on real usage. Study Structurizr and LikeC4 DSL designs. |
| Web viewer is a large engineering effort | Consider building on existing rendering libraries (D3, ELK layout engine, React Flow) or generating output for existing renderers (Mermaid, Graphviz). |
| Sphinx integration complexity | Prototype early. A minimal Sphinx directive that renders a single view from a model is a good first milestone. |
| Competing with established tools | Focus on the combination of features no single tool offers. Interoperability (export to Structurizr/Mermaid) reduces lock-in concerns. |
| Scope creep toward full UML | Explicitly define the boundary: ArchML handles high-level architecture. Detailed design stays in UML tools. |

## Suggested Next Steps

1. **Define the DSL grammar** — Start with functional architecture (contexts, systems, components, interfaces). Keep it minimal.
2. **Build a parser and semantic model** — Read `.archml` files, construct an in-memory model, run consistency checks.
3. **Generate a basic web view** — Render the functional hierarchy as an interactive diagram.
4. **Add behavioral and deployment domains** — Extend the DSL and model incrementally.
5. **Prototype Sphinx integration** — A directive that renders a named view from the model.
