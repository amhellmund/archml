# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Semantic analysis for parsed ArchML entities.

Checks structural correctness of the parsed model: duplicate names,
unresolved references, import consistency, and version mismatches.
This is distinct from validation (business logic checks such as missing
interfaces or graph cycles), which operates on the fully resolved model.
"""

from __future__ import annotations

from dataclasses import dataclass

from archml.model.entities import (
    ArchFile,
    Component,
    Connection,
    EnumDef,
    InterfaceDef,
    InterfaceRef,
    System,
)
from archml.model.types import (
    Field,
    ListTypeRef,
    MapTypeRef,
    NamedTypeRef,
    OptionalTypeRef,
    TypeRef,
)

# ###############
# Public Interface
# ###############


@dataclass(frozen=True)
class SemanticError:
    """A structural error detected during semantic analysis.

    Attributes:
        message: Human-readable description of the error.
    """

    message: str


def analyze(
    arch_file: ArchFile,
    *,
    resolved_imports: dict[str, ArchFile] | None = None,
) -> list[SemanticError]:
    """Perform semantic analysis on a parsed ArchFile.

    Checks performed:
    - Duplicate top-level names (enum, type, interface, component, system).
    - Name conflicts between enums and types (both usable as field types).
    - Duplicate enum values within each enum.
    - Duplicate field names within each type and interface.
    - Named type references (NamedTypeRef) must resolve to a known type,
      enum, or interface (locally defined or imported).
    - Interface references in ``requires`` / ``provides`` must resolve to a
      known interface (locally defined or imported); locally-defined
      versioned references are checked against the actual declared version.
    - Interface references in ``connect ... by`` statements follow the same
      rules as requires/provides references.
    - Connection endpoint names in a system must refer to direct members of
      that system, to top-level entities in the file, or to imported names.
    - Connection endpoint names in a component must refer to direct
      sub-components of that component.
    - Duplicate member names within nested components and systems.
    - Name conflicts between components and sub-systems within a system.
    - Import entity validation: when *resolved_imports* is provided, each
      entity named in a ``from ... import`` statement must actually be
      defined at the top level of the resolved source file.

    Args:
        arch_file: The parsed ArchFile to analyze.
        resolved_imports: Optional mapping from import source paths to their
            parsed ArchFile contents. When provided, imported entity names
            are verified against the definitions in those files. An import
            source path missing from this mapping is reported as an error.

    Returns:
        A list of :class:`SemanticError` instances. An empty list means no
        semantic errors were found.
    """
    return _SemanticAnalyzer(arch_file, resolved_imports or {}).analyze()


# ################
# Implementation
# ################


class _SemanticAnalyzer:
    """Performs semantic analysis on a single ArchFile."""

    def __init__(
        self,
        arch_file: ArchFile,
        resolved_imports: dict[str, ArchFile],
    ) -> None:
        self._file = arch_file
        self._resolved = resolved_imports
        # Top-level component and system names visible at file scope.
        # These are valid connection endpoints from within any nested system.
        self._file_entity_names: set[str] = (
            {c.name for c in arch_file.components}
            | {s.name for s in arch_file.systems}
        )

    def analyze(self) -> list[SemanticError]:
        """Run all semantic checks and return collected errors."""
        errors: list[SemanticError] = []

        # Build the sets of names available in this file's scope.
        local_type_names: set[str] = (
            {e.name for e in self._file.enums}
            | {t.name for t in self._file.types}
            | {i.name for i in self._file.interfaces}
        )
        local_interface_defs: dict[tuple[str, str | None], InterfaceDef] = {
            (i.name, i.version): i for i in self._file.interfaces
        }
        imported_names: set[str] = {
            name for imp in self._file.imports for name in imp.entities
        }

        # Combined sets used for reference resolution.
        all_type_names = local_type_names | imported_names
        all_interface_plain_names = (
            {i.name for i in self._file.interfaces} | imported_names
        )

        # 1. Check for duplicate top-level definitions.
        errors.extend(_check_top_level_duplicates(self._file))

        # 2. Check internals of each enum.
        for enum_def in self._file.enums:
            errors.extend(_check_enum_values(enum_def))

        # 3. Check internals of each type definition.
        for type_def in self._file.types:
            errors.extend(
                _check_field_names(f"type '{type_def.name}'", type_def.fields)
            )
            errors.extend(
                _check_type_refs_in_fields(
                    f"type '{type_def.name}'", type_def.fields, all_type_names
                )
            )

        # 4. Check internals of each interface definition.
        for iface_def in self._file.interfaces:
            errors.extend(
                _check_field_names(
                    f"interface '{iface_def.name}'", iface_def.fields
                )
            )
            errors.extend(
                _check_type_refs_in_fields(
                    f"interface '{iface_def.name}'",
                    iface_def.fields,
                    all_type_names,
                )
            )

        # 5. Check top-level components.
        for comp in self._file.components:
            errors.extend(
                self._check_component(
                    comp,
                    all_type_names,
                    all_interface_plain_names,
                    local_interface_defs,
                    imported_names,
                )
            )

        # 6. Check top-level systems.
        for system in self._file.systems:
            errors.extend(
                self._check_system(
                    system,
                    all_type_names,
                    all_interface_plain_names,
                    local_interface_defs,
                    imported_names,
                )
            )

        # 7. Validate import entities against resolved source files.
        errors.extend(self._check_import_resolutions())

        return errors

    def _check_component(
        self,
        comp: Component,
        all_type_names: set[str],
        all_interface_names: set[str],
        local_interface_defs: dict[tuple[str, str | None], InterfaceDef],
        imported_names: set[str],
    ) -> list[SemanticError]:
        errors: list[SemanticError] = []
        ctx = f"component '{comp.name}'"

        # Check for duplicate sub-component names.
        errors.extend(
            _check_duplicate_names(
                [c.name for c in comp.components],
                "Duplicate sub-component name '{}' in " + ctx,
            )
        )

        # Check requires / provides interface references.
        for ref in comp.requires:
            errors.extend(
                _check_interface_ref(
                    ctx,
                    ref,
                    all_interface_names,
                    local_interface_defs,
                    imported_names,
                    "requires",
                )
            )
        for ref in comp.provides:
            errors.extend(
                _check_interface_ref(
                    ctx,
                    ref,
                    all_interface_names,
                    local_interface_defs,
                    imported_names,
                    "provides",
                )
            )

        # Check connections: endpoints must be direct sub-components.
        sub_names = {c.name for c in comp.components}
        for conn in comp.connections:
            errors.extend(
                _check_connection(
                    ctx,
                    conn,
                    sub_names,
                    all_interface_names,
                    local_interface_defs,
                    imported_names,
                )
            )

        # Recurse into sub-components.
        for sub in comp.components:
            errors.extend(
                self._check_component(
                    sub,
                    all_type_names,
                    all_interface_names,
                    local_interface_defs,
                    imported_names,
                )
            )

        return errors

    def _check_system(
        self,
        system: System,
        all_type_names: set[str],
        all_interface_names: set[str],
        local_interface_defs: dict[tuple[str, str | None], InterfaceDef],
        imported_names: set[str],
    ) -> list[SemanticError]:
        errors: list[SemanticError] = []
        ctx = f"system '{system.name}'"

        # Check for duplicate component names within this system.
        errors.extend(
            _check_duplicate_names(
                [c.name for c in system.components],
                "Duplicate component name '{}' in " + ctx,
            )
        )
        # Check for duplicate sub-system names within this system.
        errors.extend(
            _check_duplicate_names(
                [s.name for s in system.systems],
                "Duplicate sub-system name '{}' in " + ctx,
            )
        )

        # Check for name conflicts between components and sub-systems.
        comp_names = {c.name for c in system.components}
        sys_names = {s.name for s in system.systems}
        for name in sorted(comp_names & sys_names):
            errors.append(
                SemanticError(
                    f"{ctx}: name '{name}' is used for both a component"
                    " and a sub-system"
                )
            )

        # Check requires / provides interface references.
        for ref in system.requires:
            errors.extend(
                _check_interface_ref(
                    ctx,
                    ref,
                    all_interface_names,
                    local_interface_defs,
                    imported_names,
                    "requires",
                )
            )
        for ref in system.provides:
            errors.extend(
                _check_interface_ref(
                    ctx,
                    ref,
                    all_interface_names,
                    local_interface_defs,
                    imported_names,
                    "provides",
                )
            )

        # Connection endpoints in a system may reference:
        #   1. Direct members of this system (components and sub-systems),
        #   2. Top-level entities in the file (e.g. external systems defined
        #      at the top level and referenced in an internal connection), or
        #   3. Imported names (brought in via `from ... import` and used via
        #      `use component/system`).
        member_names = comp_names | sys_names
        connection_scope = member_names | self._file_entity_names | imported_names
        for conn in system.connections:
            errors.extend(
                _check_connection(
                    ctx,
                    conn,
                    connection_scope,
                    all_interface_names,
                    local_interface_defs,
                    imported_names,
                )
            )

        # Recurse into children.
        for comp in system.components:
            errors.extend(
                self._check_component(
                    comp,
                    all_type_names,
                    all_interface_names,
                    local_interface_defs,
                    imported_names,
                )
            )
        for sub_sys in system.systems:
            errors.extend(
                self._check_system(
                    sub_sys,
                    all_type_names,
                    all_interface_names,
                    local_interface_defs,
                    imported_names,
                )
            )

        return errors

    def _check_import_resolutions(self) -> list[SemanticError]:
        """Verify that imported entity names are defined in their source files."""
        errors: list[SemanticError] = []
        if not self._resolved:
            return errors

        for imp in self._file.imports:
            path = imp.source_path
            if path not in self._resolved:
                errors.append(
                    SemanticError(
                        f"Import source '{path}' could not be resolved"
                    )
                )
                continue

            resolved_file = self._resolved[path]
            defined_names = _collect_all_top_level_names(resolved_file)
            for entity_name in imp.entities:
                if entity_name not in defined_names:
                    errors.append(
                        SemanticError(
                            f"'{entity_name}' is not defined in '{path}'"
                        )
                    )

        return errors


# ------------------------------------------------------------------
# Module-level helper functions
# ------------------------------------------------------------------


def _collect_all_top_level_names(arch_file: ArchFile) -> set[str]:
    """Return the set of all entity names defined at the top level of a file."""
    names: set[str] = set()
    names.update(e.name for e in arch_file.enums)
    names.update(t.name for t in arch_file.types)
    names.update(i.name for i in arch_file.interfaces)
    names.update(c.name for c in arch_file.components)
    names.update(s.name for s in arch_file.systems)
    return names


def _check_duplicate_names(names: list[str], fmt: str) -> list[SemanticError]:
    """Return a SemanticError for each name that appears more than once.

    Only one error per unique duplicate name is emitted (even if it appears
    three or more times).  *fmt* must contain a single ``{}`` placeholder
    that will be filled with the duplicate name.
    """
    seen: set[str] = set()
    reported: set[str] = set()
    errors: list[SemanticError] = []
    for name in names:
        if name in seen:
            if name not in reported:
                errors.append(SemanticError(fmt.format(name)))
                reported.add(name)
        else:
            seen.add(name)
    return errors


def _check_top_level_duplicates(arch_file: ArchFile) -> list[SemanticError]:
    """Check for duplicate names among top-level definitions."""
    errors: list[SemanticError] = []

    errors.extend(
        _check_duplicate_names(
            [e.name for e in arch_file.enums],
            "Duplicate enum name '{}'",
        )
    )
    errors.extend(
        _check_duplicate_names(
            [t.name for t in arch_file.types],
            "Duplicate type name '{}'",
        )
    )

    # Interfaces are keyed by (name, version) — two interfaces with the same
    # name but different versions are legal.
    seen_ifaces: set[tuple[str, str | None]] = set()
    reported_ifaces: set[tuple[str, str | None]] = set()
    for iface in arch_file.interfaces:
        key = (iface.name, iface.version)
        if key in seen_ifaces:
            if key not in reported_ifaces:
                ver_str = f"@{iface.version}" if iface.version else ""
                errors.append(
                    SemanticError(
                        f"Duplicate interface definition '{iface.name}{ver_str}'"
                    )
                )
                reported_ifaces.add(key)
        else:
            seen_ifaces.add(key)

    errors.extend(
        _check_duplicate_names(
            [c.name for c in arch_file.components],
            "Duplicate component name '{}'",
        )
    )
    errors.extend(
        _check_duplicate_names(
            [s.name for s in arch_file.systems],
            "Duplicate system name '{}'",
        )
    )

    # An enum and a type with the same name create ambiguity for field type
    # references.
    enum_names = {e.name for e in arch_file.enums}
    type_names = {t.name for t in arch_file.types}
    for name in sorted(enum_names & type_names):
        errors.append(
            SemanticError(
                f"Name '{name}' is defined as both an enum and a type"
            )
        )

    return errors


def _check_enum_values(enum_def: EnumDef) -> list[SemanticError]:
    """Check for duplicate values within an enum."""
    return _check_duplicate_names(
        enum_def.values,
        f"Duplicate value '{{}}' in enum '{enum_def.name}'",
    )


def _check_field_names(ctx: str, fields: list[Field]) -> list[SemanticError]:
    """Check for duplicate field names within a type or interface."""
    return _check_duplicate_names(
        [f.name for f in fields],
        f"Duplicate field name '{{}}' in {ctx}",
    )


def _collect_named_type_refs(type_ref: TypeRef) -> list[str]:
    """Recursively collect all NamedTypeRef names from a type reference tree."""
    if isinstance(type_ref, NamedTypeRef):
        return [type_ref.name]
    if isinstance(type_ref, ListTypeRef):
        return _collect_named_type_refs(type_ref.element_type)
    if isinstance(type_ref, MapTypeRef):
        return _collect_named_type_refs(
            type_ref.key_type
        ) + _collect_named_type_refs(type_ref.value_type)
    if isinstance(type_ref, OptionalTypeRef):
        return _collect_named_type_refs(type_ref.inner_type)
    return []


def _check_type_refs_in_fields(
    ctx: str,
    fields: list[Field],
    valid_type_names: set[str],
) -> list[SemanticError]:
    """Check that every NamedTypeRef in field types resolves to a known name."""
    errors: list[SemanticError] = []
    for field_def in fields:
        for name_ref in _collect_named_type_refs(field_def.type):
            if name_ref not in valid_type_names:
                errors.append(
                    SemanticError(
                        f"Undefined type '{name_ref}' in field"
                        f" '{field_def.name}' of {ctx}"
                    )
                )
    return errors


def _check_interface_ref(
    ctx: str,
    ref: InterfaceRef,
    all_interface_names: set[str],
    local_interface_defs: dict[tuple[str, str | None], InterfaceDef],
    imported_names: set[str],
    keyword: str,
) -> list[SemanticError]:
    """Check that an interface reference resolves to a known interface.

    When the referenced interface is locally defined (not imported), a
    versioned reference is additionally checked against the declared version.
    """
    errors: list[SemanticError] = []
    ver_str = f"@{ref.version}" if ref.version else ""

    if ref.name not in all_interface_names:
        errors.append(
            SemanticError(
                f"{ctx}: '{keyword} {ref.name}{ver_str}'"
                f" refers to unknown interface '{ref.name}'"
            )
        )
        return errors

    # Only validate the version when the interface is locally defined and not
    # also imported (an imported version could satisfy the reference).
    if ref.version is not None and ref.name not in imported_names:
        if (ref.name, ref.version) not in local_interface_defs:
            errors.append(
                SemanticError(
                    f"{ctx}: '{keyword} {ref.name}@{ref.version}'"
                    f" — no version '{ref.version}' of interface"
                    f" '{ref.name}' is defined"
                )
            )

    return errors


def _check_connection(
    ctx: str,
    conn: Connection,
    member_names: set[str],
    all_interface_names: set[str],
    local_interface_defs: dict[tuple[str, str | None], InterfaceDef],
    imported_names: set[str],
) -> list[SemanticError]:
    """Check a single connection for endpoint and interface validity."""
    errors: list[SemanticError] = []

    src = conn.source.entity
    tgt = conn.target.entity
    if src not in member_names:
        errors.append(
            SemanticError(
                f"{ctx}: connection source '{src}' is not a known member entity"
            )
        )
    if tgt not in member_names:
        errors.append(
            SemanticError(
                f"{ctx}: connection target '{tgt}' is not a known member entity"
            )
        )

    errors.extend(
        _check_interface_ref(
            ctx,
            conn.interface,
            all_interface_names,
            local_interface_defs,
            imported_names,
            "connect ... by",
        )
    )

    return errors
