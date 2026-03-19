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
    ConnectDef,
    EnumDef,
    ExposeDef,
    InterfaceDef,
    InterfaceRef,
    System,
    UserDef,
)
from archml.model.types import FieldDef, ListTypeRef, MapTypeRef, NamedTypeRef, OptionalTypeRef, TypeRef

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
    file_key: str | None = None,
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
    - Duplicate port names within each component, system, and user:
      ``requires`` and ``provides`` declarations share a port namespace; the
      effective port name defaults to the interface name when no explicit
      ``as`` alias is given.
    - Duplicate member names within nested components and systems.
    - Name conflicts between components and sub-systems within a system.
    - Connect statements: entity references in ``Entity.port`` must name
      a direct child of the enclosing scope.
    - Expose statements: ``Entity`` must name a direct child of the
      enclosing scope.
    - Import entity validation: when *resolved_imports* is provided, each
      entity named in a ``from ... import`` statement must actually be
      defined at the top level of the resolved source file.
    - Duplicate import names: the same entity name may not be imported from
      more than one source path.

    Side effect:
        Fully-qualified names are assigned to all :class:`Component`,
        :class:`System`, and :class:`InterfaceDef` entities in the file
        (setting their ``qualified_name`` attribute).  When *file_key* is
        provided it is prepended (e.g. ``"myapp/services::SystemA"``).
        Nested entities receive a ``::``-separated path built from all
        enclosing scopes plus their own name
        (e.g. ``"myapp/services::SystemA::Worker"``).

    Args:
        arch_file: The parsed ArchFile to analyze.
        resolved_imports: Optional mapping from import source paths to their
            parsed ArchFile contents. When provided, imported entity names
            are verified against the definitions in those files. An import
            source path missing from this mapping is reported as an error.
        file_key: Optional canonical key for the file being analysed
            (e.g. ``"myapp/services"`` or ``"@payments/lib/types"``).
            When provided it is used as the prefix for all
            ``qualified_name`` values in this file.

    Returns:
        A list of :class:`SemanticError` instances. An empty list means no
        semantic errors were found.
    """
    _assign_qualified_names(arch_file, file_key=file_key)
    return _SemanticAnalyzer(arch_file, resolved_imports).analyze()


# ################
# Implementation
# ################


class _SemanticAnalyzer:
    """Performs semantic analysis on a single ArchFile."""

    def __init__(
        self,
        arch_file: ArchFile,
        resolved_imports: dict[str, ArchFile] | None,
    ) -> None:
        self._file = arch_file
        self._resolved = resolved_imports

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
        imported_names: set[str] = {name for imp in self._file.imports for name in imp.entities}

        # Combined sets used for reference resolution.
        all_type_names = local_type_names | imported_names
        all_interface_plain_names = {i.name for i in self._file.interfaces} | imported_names

        # 1. Check for duplicate top-level definitions.
        errors.extend(_check_top_level_duplicates(self._file))

        # 1a. Check for duplicate import names across all import statements.
        errors.extend(_check_duplicate_imports(self._file))

        # 2. Check internals of each enum.
        for enum_def in self._file.enums:
            errors.extend(_check_enum_values(enum_def))

        # 3. Check internals of each type definition.
        for type_def in self._file.types:
            errors.extend(_check_field_names(f"type '{type_def.name}'", type_def.fields))
            errors.extend(_check_type_refs_in_fields(f"type '{type_def.name}'", type_def.fields, all_type_names))

        # 4. Check internals of each interface definition.
        for iface_def in self._file.interfaces:
            errors.extend(_check_field_names(f"interface '{iface_def.name}'", iface_def.fields))
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

        # 7. Check top-level users.
        for user in self._file.users:
            errors.extend(
                _check_user(
                    user,
                    all_interface_plain_names,
                    local_interface_defs,
                    imported_names,
                )
            )

        # 8. Check top-level connect statements.
        top_child_entity_map: dict[str, Component | System | UserDef] = {
            **{c.name: c for c in self._file.components},
            **{s.name: s for s in self._file.systems},
            **{u.name: u for u in self._file.users},
        }
        for conn in self._file.connects:
            errors.extend(_resolve_simplified_connect(conn, top_child_entity_map, "top-level"))
            errors.extend(_check_connect("top-level", conn, top_child_entity_map))

        # 9. Validate import entities against resolved source files.
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

        # Check for duplicate local interface definitions.
        errors.extend(
            _check_duplicate_names(
                [i.name for i in comp.interfaces],
                "Duplicate local interface name '{}' in " + ctx,
            )
        )

        # Check for duplicate sub-component names.
        errors.extend(
            _check_duplicate_names(
                [c.name for c in comp.components],
                "Duplicate sub-component name '{}' in " + ctx,
            )
        )

        # Merge locally-defined interfaces into scope for this component and its children.
        merged_interface_names = all_interface_names | {i.name for i in comp.interfaces}
        merged_interface_defs = {**local_interface_defs, **{(i.name, i.version): i for i in comp.interfaces}}

        # Check requires / provides interface references.
        for ref in comp.requires:
            errors.extend(
                _check_interface_ref(
                    ctx,
                    ref,
                    merged_interface_names,
                    merged_interface_defs,
                    imported_names,
                    "requires",
                )
            )
        for ref in comp.provides:
            errors.extend(
                _check_interface_ref(
                    ctx,
                    ref,
                    merged_interface_names,
                    merged_interface_defs,
                    imported_names,
                    "provides",
                )
            )

        # Check for duplicate port names across requires and provides.
        errors.extend(_check_port_names(ctx, comp.requires, comp.provides))

        # Check connect / expose statements.
        child_entity_map: dict[str, Component | System | UserDef] = {c.name: c for c in comp.components}
        for conn in comp.connects:
            errors.extend(_resolve_simplified_connect(conn, child_entity_map, ctx))
            errors.extend(_check_connect(ctx, conn, child_entity_map))
        for exp in comp.exposes:
            errors.extend(_check_expose(ctx, exp, child_entity_map))

        # Recurse into sub-components, passing the merged scope.
        for sub in comp.components:
            errors.extend(
                self._check_component(
                    sub,
                    all_type_names,
                    merged_interface_names,
                    merged_interface_defs,
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

        # Check for duplicate local interface definitions.
        errors.extend(
            _check_duplicate_names(
                [i.name for i in system.interfaces],
                "Duplicate local interface name '{}' in " + ctx,
            )
        )

        # Merge locally-defined interfaces into scope for this system and its children.
        merged_interface_names = all_interface_names | {i.name for i in system.interfaces}
        merged_interface_defs = {**local_interface_defs, **{(i.name, i.version): i for i in system.interfaces}}

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
        # Check for duplicate user names within this system.
        errors.extend(
            _check_duplicate_names(
                [u.name for u in system.users],
                "Duplicate user name '{}' in " + ctx,
            )
        )

        # Check for name conflicts between components, sub-systems, and users.
        comp_names = {c.name for c in system.components}
        sys_names = {s.name for s in system.systems}
        user_names = {u.name for u in system.users}
        for name in sorted(comp_names & sys_names):
            errors.append(SemanticError(f"{ctx}: name '{name}' is used for both a component and a sub-system"))
        for name in sorted((comp_names | sys_names) & user_names):
            errors.append(SemanticError(f"{ctx}: name '{name}' is used for both a user and a component or sub-system"))

        # Check requires / provides interface references.
        for ref in system.requires:
            errors.extend(
                _check_interface_ref(
                    ctx,
                    ref,
                    merged_interface_names,
                    merged_interface_defs,
                    imported_names,
                    "requires",
                )
            )
        for ref in system.provides:
            errors.extend(
                _check_interface_ref(
                    ctx,
                    ref,
                    merged_interface_names,
                    merged_interface_defs,
                    imported_names,
                    "provides",
                )
            )

        # Check for duplicate port names across requires and provides.
        errors.extend(_check_port_names(ctx, system.requires, system.provides))

        # Check connect / expose statements.
        child_entity_map: dict[str, Component | System | UserDef] = {
            **{c.name: c for c in system.components},
            **{s.name: s for s in system.systems},
            **{u.name: u for u in system.users},
        }
        for conn in system.connects:
            errors.extend(_resolve_simplified_connect(conn, child_entity_map, ctx))
            errors.extend(_check_connect(ctx, conn, child_entity_map))
        for exp in system.exposes:
            errors.extend(_check_expose(ctx, exp, child_entity_map))

        # Recurse into children, passing the merged scope.
        for comp in system.components:
            errors.extend(
                self._check_component(
                    comp,
                    all_type_names,
                    merged_interface_names,
                    merged_interface_defs,
                    imported_names,
                )
            )
        for sub_sys in system.systems:
            errors.extend(
                self._check_system(
                    sub_sys,
                    all_type_names,
                    merged_interface_names,
                    merged_interface_defs,
                    imported_names,
                )
            )
        for user in system.users:
            errors.extend(
                _check_user(
                    user,
                    merged_interface_names,
                    merged_interface_defs,
                    imported_names,
                )
            )

        return errors

    def _check_import_resolutions(self) -> list[SemanticError]:
        """Verify that imported entity names are defined in their source files."""
        errors: list[SemanticError] = []
        if self._resolved is None:
            return errors

        for imp in self._file.imports:
            path = imp.source_path
            if path not in self._resolved:
                errors.append(SemanticError(f"Import source '{path}' could not be resolved"))
                continue

            resolved_file = self._resolved[path]
            defined_names = _collect_all_top_level_names(resolved_file)
            for entity_name in imp.entities:
                if entity_name not in defined_names:
                    errors.append(SemanticError(f"'{entity_name}' is not defined in '{path}'"))

        return errors


# ------------------------------------------------------------------
# Module-level helper functions
# ------------------------------------------------------------------


def _assign_qualified_names(arch_file: ArchFile, *, file_key: str | None = None) -> None:
    """Assign fully-qualified names to all components, systems, and interfaces.

    Mutates each entity in-place.  When *file_key* is provided it is used as
    the top-level prefix (e.g. ``"myapp/services"``), separated from entity
    names by ``"::"``  (e.g. ``"myapp/services::Worker"``).  Nested entities
    receive a ``::``-separated path that includes all enclosing scopes
    (e.g. ``"myapp/services::SystemA::Worker"``).  Versioned interfaces
    include the version suffix (e.g. ``"myapp/services::Foo@v2"``).
    """
    file_prefix = file_key  # treated as the parent prefix for top-level entities
    for iface in arch_file.interfaces:
        ver_str = f"@{iface.version}" if iface.version else ""
        local = f"{iface.name}{ver_str}"
        iface.qualified_name = f"{file_prefix}::{local}" if file_prefix else local
    for comp in arch_file.components:
        _assign_component_qualified_names(comp, prefix=file_prefix)
    for system in arch_file.systems:
        _assign_system_qualified_names(system, prefix=file_prefix)
    for user in arch_file.users:
        _assign_user_qualified_name(user, prefix=file_prefix)


def _assign_component_qualified_names(comp: Component, prefix: str | None) -> None:
    """Recursively set qualified names for a component and its sub-components."""
    comp.qualified_name = f"{prefix}::{comp.name}" if prefix else comp.name
    for iface in comp.interfaces:
        ver_str = f"@{iface.version}" if iface.version else ""
        iface.qualified_name = f"{comp.qualified_name}::{iface.name}{ver_str}"
    for sub in comp.components:
        _assign_component_qualified_names(sub, prefix=comp.qualified_name)


def _assign_user_qualified_name(user: UserDef, prefix: str | None) -> None:
    """Set the qualified name for a user entity."""
    user.qualified_name = f"{prefix}::{user.name}" if prefix else user.name


def _assign_system_qualified_names(system: System, prefix: str | None) -> None:
    """Recursively set qualified names for a system and all its children."""
    system.qualified_name = f"{prefix}::{system.name}" if prefix else system.name
    for iface in system.interfaces:
        ver_str = f"@{iface.version}" if iface.version else ""
        iface.qualified_name = f"{system.qualified_name}::{iface.name}{ver_str}"
    for comp in system.components:
        _assign_component_qualified_names(comp, prefix=system.qualified_name)
    for sub_sys in system.systems:
        _assign_system_qualified_names(sub_sys, prefix=system.qualified_name)
    for user in system.users:
        _assign_user_qualified_name(user, prefix=system.qualified_name)


def _check_duplicate_imports(arch_file: ArchFile) -> list[SemanticError]:
    """Check that no entity name is imported from more than one source path.

    An entity name that appears in multiple ``from ... import`` statements
    (whether from the same source path or different ones) is reported as an
    error, because it would create an ambiguous binding in the current file's
    scope.
    """
    seen: dict[str, str] = {}  # entity name -> first source path
    errors: list[SemanticError] = []
    for imp in arch_file.imports:
        for name in imp.entities:
            if name in seen:
                errors.append(
                    SemanticError(
                        f"Duplicate import name '{name}': already imported from '{seen[name]}'"
                        f", cannot also import from '{imp.source_path}'"
                    )
                )
            else:
                seen[name] = imp.source_path
    return errors


def _collect_all_top_level_names(arch_file: ArchFile) -> set[str]:
    """Return the set of all entity names defined at the top level of a file."""
    names: set[str] = set()
    names.update(e.name for e in arch_file.enums)
    names.update(t.name for t in arch_file.types)
    names.update(i.name for i in arch_file.interfaces)
    names.update(c.name for c in arch_file.components)
    names.update(s.name for s in arch_file.systems)
    names.update(u.name for u in arch_file.users)
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
                errors.append(SemanticError(f"Duplicate interface definition '{iface.name}{ver_str}'"))
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
    errors.extend(
        _check_duplicate_names(
            [u.name for u in arch_file.users],
            "Duplicate user name '{}'",
        )
    )

    # An enum and a type with the same name create ambiguity for field type
    # references.
    enum_names = {e.name for e in arch_file.enums}
    type_names = {t.name for t in arch_file.types}
    for name in sorted(enum_names & type_names):
        errors.append(SemanticError(f"Name '{name}' is defined as both an enum and a type"))

    return errors


def _check_enum_values(enum_def: EnumDef) -> list[SemanticError]:
    """Check for duplicate values within an enum."""
    return _check_duplicate_names(
        enum_def.values,
        f"Duplicate value '{{}}' in enum '{enum_def.name}'",
    )


def _check_field_names(ctx: str, fields: list[FieldDef]) -> list[SemanticError]:
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
        return _collect_named_type_refs(type_ref.key_type) + _collect_named_type_refs(type_ref.value_type)
    if isinstance(type_ref, OptionalTypeRef):
        return _collect_named_type_refs(type_ref.inner_type)
    return []


def _check_type_refs_in_fields(
    ctx: str,
    fields: list[FieldDef],
    valid_type_names: set[str],
) -> list[SemanticError]:
    """Check that every NamedTypeRef in field types resolves to a known name."""
    errors: list[SemanticError] = []
    for field_def in fields:
        for name_ref in _collect_named_type_refs(field_def.type):
            if name_ref not in valid_type_names:
                errors.append(SemanticError(f"Undefined type '{name_ref}' in field '{field_def.name}' of {ctx}"))
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
        errors.append(SemanticError(f"{ctx}: '{keyword} {ref.name}{ver_str}' refers to unknown interface '{ref.name}'"))
        return errors

    # Only validate the version when the interface is locally defined and not
    # also imported (an imported version could satisfy the reference).
    if (
        ref.version is not None
        and ref.name not in imported_names
        and (ref.name, ref.version) not in local_interface_defs
    ):
        errors.append(
            SemanticError(
                f"{ctx}: '{keyword} {ref.name}@{ref.version}'"
                f" — no version '{ref.version}' of interface"
                f" '{ref.name}' is defined"
            )
        )

    return errors


def _valid_connect_port_names(entity: Component | System | UserDef) -> set[str] | None:
    """Return the set of port names that may appear in a connect statement for *entity*.

    Includes direct ``requires``/``provides`` port names and, for components
    and systems, the effective name of each ``expose`` declaration (either
    ``expose.as_name`` when set, otherwise ``expose.port``).

    Returns ``None`` for stub entities (created by ``use component``/``use system``)
    whose port definitions are not yet available during semantic analysis.
    """
    if isinstance(entity, (Component, System)) and entity.is_stub:
        return None
    names: set[str] = set()
    for ref in entity.requires:
        names.add(_effective_port_name(ref))
    for ref in entity.provides:
        names.add(_effective_port_name(ref))
    if isinstance(entity, (Component, System)):
        for exp in entity.exposes:
            names.add(exp.as_name if exp.as_name else exp.port)
    return names


def _check_connect(
    ctx: str,
    conn: ConnectDef,
    child_entity_map: dict[str, Component | System | UserDef],
) -> list[SemanticError]:
    """Check that entity and port references in a connect statement are valid."""
    errors: list[SemanticError] = []
    for side_entity, side_port in ((conn.src_entity, conn.src_port), (conn.dst_entity, conn.dst_port)):
        if side_entity is None:
            continue
        if side_entity not in child_entity_map:
            errors.append(SemanticError(f"{ctx}: connect references unknown child entity '{side_entity}'"))
            continue
        if side_port is not None:
            valid = _valid_connect_port_names(child_entity_map[side_entity])
            if valid is not None and side_port not in valid:
                errors.append(SemanticError(f"{ctx}: connect references unknown port '{side_port}' on '{side_entity}'"))
    return errors


def _infer_unique_port(
    entity: Component | System | UserDef,
    direction: str,
    entity_name: str,
    ctx: str,
) -> tuple[str | None, list[SemanticError]]:
    """Return the unique port name in *direction* ('provides' or 'requires') for *entity*.

    Returns ``(port_name, [])`` when exactly one port exists, or
    ``(None, [error])`` when zero or more than one port exists.
    """
    ports: list[InterfaceRef] = getattr(entity, direction)
    if len(ports) == 1:
        return _effective_port_name(ports[0]), []
    if len(ports) == 0:
        return None, [SemanticError(f"{ctx}: simplified connect: '{entity_name}' has no {direction} ports")]
    return None, [
        SemanticError(
            f"{ctx}: simplified connect: '{entity_name}' has multiple {direction} ports;"
            f" use '{entity_name}.port' form to disambiguate"
        )
    ]


def _resolve_simplified_connect(
    conn: ConnectDef,
    child_entity_map: dict[str, Component | System | UserDef],
    ctx: str,
) -> list[SemanticError]:
    """Resolve simplified connect forms in-place.

    When a bare identifier (no dot) is used as a port reference and that
    identifier names a direct child entity, it is the simplified form.
    The unique ``provides`` port (for src) or ``requires`` port (for dst) is
    inferred; ambiguous or missing ports produce a semantic error.
    """
    errors: list[SemanticError] = []

    # Src side: (None, "EntityName") where EntityName is a child.
    if conn.src_entity is None and conn.src_port is not None and conn.src_port in child_entity_map:
        entity = child_entity_map[conn.src_port]
        port, errs = _infer_unique_port(entity, "provides", conn.src_port, ctx)
        errors.extend(errs)
        if port is not None:
            conn.src_entity = conn.src_port
            conn.src_port = port

    # Dst side: (None, "EntityName") where EntityName is a child.
    if conn.dst_entity is None and conn.dst_port is not None and conn.dst_port in child_entity_map:
        entity = child_entity_map[conn.dst_port]
        port, errs = _infer_unique_port(entity, "requires", conn.dst_port, ctx)
        errors.extend(errs)
        if port is not None:
            conn.dst_entity = conn.dst_port
            conn.dst_port = port

    return errors


def _check_expose(
    ctx: str,
    exp: ExposeDef,
    child_entity_map: dict[str, Component | System | UserDef],
) -> list[SemanticError]:
    """Check that the entity and port in an expose statement are valid."""
    if exp.entity not in child_entity_map:
        return [SemanticError(f"{ctx}: expose references unknown child entity '{exp.entity}'")]
    entity = child_entity_map[exp.entity]
    if isinstance(entity, (Component, System)) and entity.is_stub:
        return []
    valid_ports = _valid_connect_port_names(entity)
    if valid_ports is not None and exp.port not in valid_ports:
        return [SemanticError(f"{ctx}: expose references unknown port '{exp.port}' on '{exp.entity}'")]
    return []


def _effective_port_name(ref: InterfaceRef) -> str:
    """Return the effective port name for an interface reference.

    When no explicit ``as`` alias is given, the port name defaults to the
    interface name.
    """
    return ref.port_name if ref.port_name is not None else ref.name


def _check_port_names(
    ctx: str,
    requires: list[InterfaceRef],
    provides: list[InterfaceRef],
) -> list[SemanticError]:
    """Check that all port names within an entity are unique.

    ``requires`` and ``provides`` ports share the same port namespace.
    The effective port name defaults to the interface name when no explicit
    ``as`` alias is given.
    """
    all_port_names = [_effective_port_name(r) for r in requires] + [_effective_port_name(p) for p in provides]
    return _check_duplicate_names(
        all_port_names,
        f"Duplicate port name '{{}}' in {ctx}",
    )


def _check_user(
    user: UserDef,
    all_interface_names: set[str],
    local_interface_defs: dict[tuple[str, str | None], InterfaceDef],
    imported_names: set[str],
) -> list[SemanticError]:
    """Check requires/provides interface references on a user entity."""
    errors: list[SemanticError] = []
    ctx = f"user '{user.name}'"
    for ref in user.requires:
        errors.extend(
            _check_interface_ref(ctx, ref, all_interface_names, local_interface_defs, imported_names, "requires")
        )
    for ref in user.provides:
        errors.extend(
            _check_interface_ref(ctx, ref, all_interface_names, local_interface_defs, imported_names, "provides")
        )
    errors.extend(_check_port_names(ctx, user.requires, user.provides))
    return errors
