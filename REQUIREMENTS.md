# Requirements — archml

This document captures the requirements for **archml**, a Sphinx extension built on top of
[sphinx-needs](https://sphinx-needs.readthedocs.io/) that enables software engineers to design
and document software architecture directly within Sphinx documentation.

---

## 1. General

| ID | Requirement | Priority |
|----|-------------|----------|
| REQ-GEN-001 | archml SHALL be implemented as a Sphinx extension that integrates with sphinx-needs. | Must |
| REQ-GEN-002 | archml SHALL be installable as a Python package via pip. | Must |
| REQ-GEN-003 | archml SHALL support Python 3.10 and later. | Must |
| REQ-GEN-004 | archml SHALL provide clear error messages when the user's architecture definitions are invalid or incomplete. | Must |
| REQ-GEN-005 | archml SHALL be usable alongside other Sphinx extensions without conflicts. | Should |

---

## 2. Architecture Entities

archml provides pre-defined entity types that represent the building blocks of a software architecture.

| ID | Requirement | Priority |
|----|-------------|----------|
| REQ-ENT-001 | archml SHALL provide a **System** entity to represent a top-level software system or product. | Must |
| REQ-ENT-002 | archml SHALL provide a **Component** entity to represent a logical or physical module within a system. | Must |
| REQ-ENT-003 | archml SHALL provide an **Interface** entity to represent a contract or API exposed or consumed by a component. | Must |
| REQ-ENT-004 | archml SHALL provide a **Deployment** entity to represent a runtime deployment target (e.g. host, container, cloud service). | Must |
| REQ-ENT-005 | Each entity SHALL have a unique identifier that can be referenced from other entities and from prose text. | Must |
| REQ-ENT-006 | Each entity SHALL support a human-readable title and an optional description. | Must |
| REQ-ENT-007 | Each entity SHALL support user-defined key-value metadata (tags, status, owner, etc.). | Should |
| REQ-ENT-008 | archml SHALL allow components to be nested hierarchically to model sub-components. | Must |
| REQ-ENT-009 | archml SHALL allow associating components with the system they belong to. | Must |
| REQ-ENT-010 | archml SHALL allow associating interfaces with the component that provides or requires them. | Must |
| REQ-ENT-011 | archml SHALL allow mapping components to deployment entities to capture the deployment view. | Must |
| REQ-ENT-012 | archml SHOULD allow defining **Connector** or **Link** entities to model data flows or dependencies between components or interfaces. | Should |

---

## 3. Architecture Diagrams

archml supports embedding architecture diagrams into the generated Sphinx documentation.

| ID | Requirement | Priority |
|----|-------------|----------|
| REQ-DIA-001 | archml SHALL support generating architecture diagrams from the defined entities. | Must |
| REQ-DIA-002 | archml SHALL support a **System Context Diagram** showing the system and its external actors or neighboring systems. | Must |
| REQ-DIA-003 | archml SHALL support a **Component Diagram** showing the internal components of a system and their relationships. | Must |
| REQ-DIA-004 | archml SHALL support a **Deployment Diagram** showing components mapped to deployment targets. | Must |
| REQ-DIA-005 | Diagrams SHALL be rendered as images (SVG or PNG) embedded in the HTML output. | Must |
| REQ-DIA-006 | archml SHALL use an open and well-known diagram rendering backend (e.g. PlantUML, Graphviz, or D2). | Must |
| REQ-DIA-007 | Diagram elements SHALL be automatically derived from the architecture entities defined in the documentation; no manual drawing SHALL be required. | Must |
| REQ-DIA-008 | archml SHOULD support filtering or scoping a diagram to show only a subset of entities (e.g. a single component and its neighbors). | Should |
| REQ-DIA-009 | archml SHOULD allow basic customization of diagram appearance (colors, grouping, layout direction). | Should |

---

## 4. Sphinx / RST Integration

| ID | Requirement | Priority |
|----|-------------|----------|
| REQ-INT-001 | Each architecture entity SHALL be representable as a Sphinx-needs directive in reStructuredText (`.rst`) files. | Must |
| REQ-INT-002 | archml SHALL allow cross-referencing architecture entities from any location in the documentation using standard Sphinx or sphinx-needs referencing mechanisms. | Must |
| REQ-INT-003 | archml SHALL provide a directive to embed a generated diagram at an arbitrary location in the documentation. | Must |
| REQ-INT-004 | archml SHOULD provide index pages or need-tables that list all entities of a given type (e.g. all components, all interfaces). | Should |
| REQ-INT-005 | archml SHOULD support Markdown (MyST) sources in addition to reStructuredText. | Should |

---

## 5. Validation and Consistency

| ID | Requirement | Priority |
|----|-------------|----------|
| REQ-VAL-001 | archml SHALL validate that every interface is associated with exactly one providing component. | Must |
| REQ-VAL-002 | archml SHALL validate that entity identifiers are unique across the documentation set. | Must |
| REQ-VAL-003 | archml SHALL report a build warning when a referenced entity does not exist. | Must |
| REQ-VAL-004 | archml SHOULD validate that deployment mappings reference valid component and deployment entities. | Should |
| REQ-VAL-005 | archml SHOULD provide an optional strict mode that turns validation warnings into build errors. | Should |

---

## 6. Extensibility

| ID | Requirement | Priority |
|----|-------------|----------|
| REQ-EXT-001 | archml SHOULD allow users to define custom entity types beyond the built-in set. | Should |
| REQ-EXT-002 | archml SHOULD allow users to add custom fields to built-in entity types via configuration. | Should |
| REQ-EXT-003 | archml SHOULD provide a documented Python API so that other Sphinx extensions can programmatically query the architecture model. | Could |

---

## 7. Documentation and Testing

| ID | Requirement | Priority |
|----|-------------|----------|
| REQ-DOC-001 | archml SHALL include user-facing documentation with installation instructions, a getting-started guide, and a reference of all directives. | Must |
| REQ-DOC-002 | archml SHALL include example projects demonstrating typical usage. | Should |
| REQ-TST-001 | archml SHALL have automated tests covering entity creation, relationship validation, and diagram generation. | Must |
| REQ-TST-002 | archml SHOULD achieve at least 80 % code coverage in its test suite. | Should |
