# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Business validation checks for ArchML models.

These checks operate on fully resolved models (after semantic analysis) and
enforce architectural correctness rules beyond structural validity.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from archml.model.entities import ArchFile, Component, ConnectDef, ExposeDef, InterfaceRef, System
from archml.model.types import FieldDef, ListTypeRef, MapTypeRef, NamedTypeRef, OptionalTypeRef, TypeRef

# ###############
# Public Interface
# ###############


@dataclass(frozen=True)
class ValidationWarning:
    """A non-fatal business rule violation detected during validation.

    The architecture remains structurally valid, but the issue indicates
    incomplete or potentially unintentional design choices.

    Attributes:
        message: Human-readable description of the warning.
    """

    message: str


@dataclass(frozen=True)
class ValidationError:
    """A fatal business rule violation detected during validation.

    The architecture is considered invalid and should be corrected.

    Attributes:
        message: Human-readable description of the error.
    """

    message: str


@dataclass
class ValidationResult:
    """Result of running business validation checks.

    Attributes:
        warnings: Non-fatal issues found during validation.
        errors: Fatal errors that indicate an invalid architecture.
    """

    warnings: list[ValidationWarning] = field(default_factory=list)
    errors: list[ValidationError] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Return True if any fatal validation errors were found."""
        return len(self.errors) > 0


def validate(arch_file: ArchFile) -> ValidationResult:
    """Run all business validation checks on a fully resolved ArchFile.

    Checks performed:

    1. **Type definition cycles** (error): Recursive type or interface
       definitions where a type ultimately references itself through a chain
       of ``NamedTypeRef`` fields are forbidden.

    2. **Interface propagation** (error): If a system or component declares
       an interface in its ``requires`` or ``provides``, at least one direct
       member (sub-component, sub-system, or user) must declare the same
       interface.  This ensures that upstream declarations are grounded in
       the hierarchy.  When variants are present the check is performed
       independently for each declared variant.

    3. **Unwired ports** (error): Every port of every sub-entity must be
       accounted for within its enclosing scope: either wired by a ``connect``
       statement or explicitly promoted to the enclosing boundary with
       ``expose``.  A port that is neither wired nor exposed is a validation
       error.  When variants are present the check is performed independently
       for each declared variant.

    4. **Fully connected** (error): Every non-stub entity (component, system,
       user) must declare at least one port (``requires`` or ``provides``) that
       is active in each variant in which the entity participates.  An entity
       with no active ports in a variant is disconnected from the architecture
       and provides no value in that configuration.  When variants are present
       the check is performed independently for each declared variant.

    Args:
        arch_file: The resolved ArchFile to validate. Qualified names should
            be assigned prior to calling this function (e.g., via semantic
            analysis).

    Returns:
        A :class:`ValidationResult` containing any warnings and errors found.
        An empty result (no warnings, no errors) indicates a fully valid model.
    """
    warnings: list[ValidationWarning] = []
    errors: list[ValidationError] = []

    errors.extend(_check_type_cycles(arch_file))
    errors.extend(_check_interface_propagation(arch_file))
    errors.extend(_check_unwired_ports(arch_file))
    errors.extend(_check_fully_connected(arch_file))
    return ValidationResult(warnings=warnings, errors=errors)


# ################
# Implementation
# ################


def _entity_label(name: str, qualified_name: str) -> str:
    """Return qualified_name if set, otherwise fall back to name."""
    return qualified_name if qualified_name else name


def _collect_named_refs_from_type(type_ref: TypeRef) -> list[str]:
    """Recursively collect all NamedTypeRef names reachable from a type reference."""
    if isinstance(type_ref, NamedTypeRef):
        return [type_ref.name]
    if isinstance(type_ref, ListTypeRef):
        return _collect_named_refs_from_type(type_ref.element_type)
    if isinstance(type_ref, MapTypeRef):
        return _collect_named_refs_from_type(type_ref.key_type) + _collect_named_refs_from_type(type_ref.value_type)
    if isinstance(type_ref, OptionalTypeRef):
        return _collect_named_refs_from_type(type_ref.inner_type)
    return []


def _collect_named_refs_from_fields(fields: list[FieldDef]) -> list[str]:
    """Collect all NamedTypeRef names from a list of field definitions."""
    result: list[str] = []
    for f in fields:
        result.extend(_collect_named_refs_from_type(f.type))
    return result


def _detect_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    """Detect a cycle in a directed graph using DFS.

    Uses a three-colour marking scheme (white/grey/black) to distinguish
    unvisited, in-progress, and fully-explored nodes.

    Args:
        graph: Adjacency list mapping each node to its direct neighbours.
            Nodes that appear only as neighbours (not as keys) are treated
            as having no outgoing edges.

    Returns:
        A list of node names forming the cycle with the start node repeated
        at the end (e.g. ``["A", "B", "C", "A"]``), or ``None`` if the
        graph is acyclic.
    """
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {}
    path: list[str] = []

    def _dfs(node: str) -> list[str] | None:
        color[node] = GREY
        path.append(node)
        for neighbor in graph.get(node, []):
            state = color.get(neighbor, WHITE)
            if state == GREY:
                cycle_start = path.index(neighbor)
                return path[cycle_start:] + [neighbor]
            if state == WHITE:
                result = _dfs(neighbor)
                if result is not None:
                    return result
        path.pop()
        color[node] = BLACK
        return None

    for node in graph:
        if color.get(node, WHITE) == WHITE:
            result = _dfs(node)
            if result is not None:
                return result
    return None


def _check_type_cycles(arch_file: ArchFile) -> list[ValidationError]:
    """Return errors for recursive cycles in type or interface definitions."""
    errors: list[ValidationError] = []

    # Only types and interfaces can form recursive definition cycles via NamedTypeRef.
    # Enums have no fields and are always leaf nodes in the reference graph.
    all_defined: set[str] = {t.name for t in arch_file.types} | {i.name for i in arch_file.interfaces}

    graph: dict[str, list[str]] = {}
    for typedef in arch_file.types:
        refs = _collect_named_refs_from_fields(typedef.fields)
        graph[typedef.name] = [r for r in refs if r in all_defined]
    for iface in arch_file.interfaces:
        refs = _collect_named_refs_from_fields(iface.fields)
        graph[iface.name] = [r for r in refs if r in all_defined]

    cycle = _detect_cycle(graph)
    if cycle is not None:
        cycle_str = " -> ".join(cycle)
        errors.append(ValidationError(message=f"Recursive type definition cycle detected: {cycle_str}."))

    return errors


def _iface_key(ref: InterfaceRef) -> str:
    """Return a hashable key for an interface reference."""
    return ref.name


# ------------------------------------------------------------------
# Variant helpers
# ------------------------------------------------------------------


def _active(variants: list[str], v: str | None) -> bool:
    """Return True if an item annotated with *variants* is active for variant *v*.

    When *v* is ``None`` (baseline mode, used when no variants exist in the
    scope) every item is active.  When *v* is a specific variant name, only
    baseline items (``variants == []``) and items whose variant list contains
    *v* are active.
    """
    if v is None:
        return True
    return not variants or v in variants


def _variant_label(v: str | None) -> str:
    """Return a variant label string for insertion in error messages."""
    return f" [variant '{v}']" if v is not None else ""


def _collect_component_variants(comp: Component) -> set[str]:
    """Collect all variant names mentioned anywhere in a component subtree."""
    vs: set[str] = set(comp.variants)
    for ref in comp.requires + comp.provides:
        vs.update(ref.variants)
    for conn in comp.connects:
        vs.update(conn.variants)
    for exp in comp.exposes:
        vs.update(exp.variants)
    for iface in comp.interfaces:
        vs.update(iface.variants)
    for sub in comp.components:
        vs.update(_collect_component_variants(sub))
    return vs


def _collect_system_variants(system: System) -> set[str]:
    """Collect all variant names mentioned anywhere in a system subtree."""
    vs: set[str] = set(system.variants)
    for ref in system.requires + system.provides:
        vs.update(ref.variants)
    for conn in system.connects:
        vs.update(conn.variants)
    for exp in system.exposes:
        vs.update(exp.variants)
    for iface in system.interfaces:
        vs.update(iface.variants)
    for comp in system.components:
        vs.update(_collect_component_variants(comp))
    for sub in system.systems:
        vs.update(_collect_system_variants(sub))
    for user in system.users:
        vs.update(user.variants)
        for ref in user.requires + user.provides:
            vs.update(ref.variants)
    return vs


def _check_variants_for(vs_set: set[str]) -> list[str | None]:
    """Return the variants to check for a scope.

    When no variants are declared anywhere in the scope, returns ``[None]``
    so that exactly one baseline check (identical to the old variant-blind
    behaviour) is performed.  When variants are present, returns the sorted
    list of named variants.
    """
    if vs_set:
        return sorted(vs_set)
    return [None]


# ------------------------------------------------------------------
# Interface propagation (per variant)
# ------------------------------------------------------------------


def _check_component_propagation(comp: Component, v: str | None) -> list[ValidationError]:
    """Check interface propagation for *comp* in variant *v*.

    When *v* is ``None`` the check is variant-blind (baseline).
    """
    errors: list[ValidationError] = []
    active_subs = [sub for sub in comp.components if _active(sub.variants, v)]
    if active_subs:
        member_provides = {_iface_key(r) for sub in active_subs for r in sub.provides if _active(r.variants, v)}
        member_requires = {_iface_key(r) for sub in active_subs for r in sub.requires if _active(r.variants, v)}
        label = _entity_label(comp.name, comp.qualified_name)
        vlabel = _variant_label(v)
        for ref in comp.provides:
            if not _active(ref.variants, v):
                continue
            if _iface_key(ref) not in member_provides:
                errors.append(
                    ValidationError(
                        message=(
                            f"Component '{label}'{vlabel} provides interface '{ref.name}'"
                            f" but no sub-component provides it."
                        )
                    )
                )
        for ref in comp.requires:
            if not _active(ref.variants, v):
                continue
            if _iface_key(ref) not in member_requires:
                errors.append(
                    ValidationError(
                        message=(
                            f"Component '{label}'{vlabel} requires interface '{ref.name}'"
                            f" but no sub-component requires it."
                        )
                    )
                )
    for sub in active_subs:
        errors.extend(_check_component_propagation(sub, v))
    return errors


def _check_system_propagation(system: System, v: str | None) -> list[ValidationError]:
    """Check interface propagation for *system* in variant *v*.

    When *v* is ``None`` the check is variant-blind (baseline).
    """
    errors: list[ValidationError] = []
    active_comps = [c for c in system.components if _active(c.variants, v)]
    active_subs = [s for s in system.systems if _active(s.variants, v)]
    active_users = [u for u in system.users if _active(u.variants, v)]
    has_members = bool(active_comps or active_subs or active_users)
    if has_members:
        member_provides = (
            {_iface_key(r) for c in active_comps for r in c.provides if _active(r.variants, v)}
            | {_iface_key(r) for s in active_subs for r in s.provides if _active(r.variants, v)}
            | {_iface_key(r) for u in active_users for r in u.provides if _active(r.variants, v)}
        )
        member_requires = (
            {_iface_key(r) for c in active_comps for r in c.requires if _active(r.variants, v)}
            | {_iface_key(r) for s in active_subs for r in s.requires if _active(r.variants, v)}
            | {_iface_key(r) for u in active_users for r in u.requires if _active(r.variants, v)}
        )
        label = _entity_label(system.name, system.qualified_name)
        vlabel = _variant_label(v)
        for ref in system.provides:
            if not _active(ref.variants, v):
                continue
            if _iface_key(ref) not in member_provides:
                errors.append(
                    ValidationError(
                        message=(f"System '{label}'{vlabel} provides interface '{ref.name}' but no member provides it.")
                    )
                )
        for ref in system.requires:
            if not _active(ref.variants, v):
                continue
            if _iface_key(ref) not in member_requires:
                errors.append(
                    ValidationError(
                        message=(f"System '{label}'{vlabel} requires interface '{ref.name}' but no member requires it.")
                    )
                )
    for sub in active_subs:
        errors.extend(_check_system_propagation(sub, v))
    for comp in active_comps:
        errors.extend(_check_component_propagation(comp, v))
    return errors


def _check_interface_propagation(arch_file: ArchFile) -> list[ValidationError]:
    """Return errors for interfaces not propagated to any direct member.

    For every non-leaf component or system that declares interfaces in
    ``requires`` or ``provides``, at least one direct child active in the
    current variant must declare the same interface.  Leaf entities (no
    children active in the variant) are exempt.

    When variants are present in a scope, the check is performed
    independently for each declared variant.  When no variants are present
    the check is variant-blind (equivalent to the previous behaviour).
    """
    errors: list[ValidationError] = []
    for system in arch_file.systems:
        for v in _check_variants_for(_collect_system_variants(system)):
            errors.extend(_check_system_propagation(system, v))
    for comp in arch_file.components:
        for v in _check_variants_for(_collect_component_variants(comp)):
            errors.extend(_check_component_propagation(comp, v))
    return errors


# ------------------------------------------------------------------
# Unwired ports (per variant)
# ------------------------------------------------------------------


def _effective_port_name(ref: InterfaceRef) -> str:
    """Return the effective port name for an interface reference.

    When no explicit ``as`` alias is given, the port name defaults to the
    interface name.
    """
    return ref.port_name if ref.port_name is not None else ref.name


def _wired_ports(
    connects: list[ConnectDef],
    exposes: list[ExposeDef],
    v: str | None,
) -> dict[str, set[str]]:
    """Build a map from child entity name to the set of its wired port names.

    Only connects and exposes that are active in variant *v* are considered.
    When *v* is ``None`` all connects and exposes are included (baseline).
    """
    wired: dict[str, set[str]] = {}
    for conn in connects:
        if not _active(conn.variants, v):
            continue
        if conn.src_entity is not None and conn.src_port is not None:
            wired.setdefault(conn.src_entity, set()).add(conn.src_port)
        if conn.dst_entity is not None and conn.dst_port is not None:
            wired.setdefault(conn.dst_entity, set()).add(conn.dst_port)
    for exp in exposes:
        if not _active(exp.variants, v):
            continue
        wired.setdefault(exp.entity, set()).add(exp.port)
    return wired


def _check_component_scope(comp: Component, v: str | None) -> list[ValidationError]:
    """Check unwired ports within *comp* for variant *v*.

    When *v* is ``None`` the check is variant-blind (baseline).
    """
    errors: list[ValidationError] = []
    active_subs = [sub for sub in comp.components if _active(sub.variants, v)]
    if not active_subs:
        return []
    wired = _wired_ports(comp.connects, comp.exposes, v)
    label = _entity_label(comp.name, comp.qualified_name)
    vlabel = _variant_label(v)
    for sub in active_subs:
        sub_wired = wired.get(sub.name, set())
        for ref in sub.requires + sub.provides:
            if not _active(ref.variants, v):
                continue
            port = _effective_port_name(ref)
            if port not in sub_wired:
                errors.append(
                    ValidationError(
                        message=(
                            f"Component '{label}'{vlabel}: port '{sub.name}.{port}'"
                            f" is neither wired by a connect nor exposed."
                        )
                    )
                )
    for sub in active_subs:
        errors.extend(_check_component_scope(sub, v))
    return errors


def _check_system_scope(system: System, v: str | None) -> list[ValidationError]:
    """Check unwired ports within *system* for variant *v*.

    When *v* is ``None`` the check is variant-blind (baseline).
    """
    errors: list[ValidationError] = []
    active_comps = [c for c in system.components if _active(c.variants, v)]
    active_subs = [s for s in system.systems if _active(s.variants, v)]
    active_users = [u for u in system.users if _active(u.variants, v)]
    has_members = bool(active_comps or active_subs or active_users)
    if not has_members:
        return []
    wired = _wired_ports(system.connects, system.exposes, v)
    label = _entity_label(system.name, system.qualified_name)
    vlabel = _variant_label(v)
    for comp in active_comps:
        comp_wired = wired.get(comp.name, set())
        for ref in comp.requires + comp.provides:
            if not _active(ref.variants, v):
                continue
            port = _effective_port_name(ref)
            if port not in comp_wired:
                errors.append(
                    ValidationError(
                        message=(
                            f"System '{label}'{vlabel}: port '{comp.name}.{port}'"
                            f" is neither wired by a connect nor exposed."
                        )
                    )
                )
    for sub_sys in active_subs:
        sys_wired = wired.get(sub_sys.name, set())
        for ref in sub_sys.requires + sub_sys.provides:
            if not _active(ref.variants, v):
                continue
            port = _effective_port_name(ref)
            if port not in sys_wired:
                errors.append(
                    ValidationError(
                        message=(
                            f"System '{label}'{vlabel}: port '{sub_sys.name}.{port}'"
                            f" is neither wired by a connect nor exposed."
                        )
                    )
                )
    for user in active_users:
        user_wired = wired.get(user.name, set())
        for ref in user.requires + user.provides:
            if not _active(ref.variants, v):
                continue
            port = _effective_port_name(ref)
            if port not in user_wired:
                errors.append(
                    ValidationError(
                        message=(
                            f"System '{label}'{vlabel}: port '{user.name}.{port}'"
                            f" is neither wired by a connect nor exposed."
                        )
                    )
                )
    for sub_sys in active_subs:
        errors.extend(_check_system_scope(sub_sys, v))
    for comp in active_comps:
        errors.extend(_check_component_scope(comp, v))
    return errors


def _check_unwired_ports(arch_file: ArchFile) -> list[ValidationError]:
    """Return errors for sub-entity ports not wired by connect or expose.

    Every port of every sub-entity must be accounted for within the enclosing
    scope: either wired by a ``connect`` or promoted by ``expose``.  Leaf
    entities (no sub-entities active in the current variant) are exempt.

    When variants are present in a scope, the check is performed
    independently for each declared variant.  When no variants are present
    the check is variant-blind (equivalent to the previous behaviour).
    """
    errors: list[ValidationError] = []
    for system in arch_file.systems:
        for v in _check_variants_for(_collect_system_variants(system)):
            errors.extend(_check_system_scope(system, v))
    for comp in arch_file.components:
        for v in _check_variants_for(_collect_component_variants(comp)):
            errors.extend(_check_component_scope(comp, v))
    return errors


# ------------------------------------------------------------------
# Fully connected (per variant)
# ------------------------------------------------------------------


def _no_active_ports(
    requires: list[InterfaceRef],
    provides: list[InterfaceRef],
    v: str | None,
) -> bool:
    """Return True when the entity has no ports active in variant *v*."""
    return not any(_active(r.variants, v) for r in requires + provides)


def _fully_connected_component(comp: Component, v: str | None) -> list[ValidationError]:
    """Recursively check that every non-stub component active in *v* has ports.

    A component that has active sub-components participates through its children
    and is exempt from the portless check even if it declares no own ports.
    Only leaf components (no active sub-components) must have at least one
    active port.
    """
    errors: list[ValidationError] = []
    active_subs = [sub for sub in comp.components if _active(sub.variants, v)]
    if not comp.is_stub and not active_subs and _no_active_ports(comp.requires, comp.provides, v):
        label = _entity_label(comp.name, comp.qualified_name)
        errors.append(
            ValidationError(message=(f"Component '{label}'{_variant_label(v)} has no ports (requires or provides)."))
        )
    for sub in active_subs:
        errors.extend(_fully_connected_component(sub, v))
    return errors


def _fully_connected_system(system: System, v: str | None) -> list[ValidationError]:
    """Recursively check that every non-stub entity in *system* active in *v* has ports.

    A system that has active members (components, sub-systems, or users)
    participates through its children and is exempt from the portless check
    even if it declares no own ports.  Only leaf systems (no active members)
    must have at least one active port.  Users are always leaves.
    """
    errors: list[ValidationError] = []
    active_comps = [c for c in system.components if _active(c.variants, v)]
    active_subs = [s for s in system.systems if _active(s.variants, v)]
    active_users = [u for u in system.users if _active(u.variants, v)]
    has_active_members = bool(active_comps or active_subs or active_users)
    if not system.is_stub and not has_active_members and _no_active_ports(system.requires, system.provides, v):
        label = _entity_label(system.name, system.qualified_name)
        errors.append(
            ValidationError(message=(f"System '{label}'{_variant_label(v)} has no ports (requires or provides)."))
        )
    for comp in active_comps:
        errors.extend(_fully_connected_component(comp, v))
    for sub in active_subs:
        errors.extend(_fully_connected_system(sub, v))
    for user in active_users:
        if _no_active_ports(user.requires, user.provides, v):
            label = _entity_label(user.name, user.qualified_name)
            errors.append(
                ValidationError(message=(f"User '{label}'{_variant_label(v)} has no ports (requires or provides)."))
            )
    return errors


def _check_fully_connected(arch_file: ArchFile) -> list[ValidationError]:
    """Return errors for entities that have no active ports in a given variant.

    Every non-stub leaf component, system, and user must declare at least one
    port (``requires`` or ``provides``) active in each variant in which the
    entity participates.  Container entities that have active sub-entities
    participate through their children and are exempt from this check.

    Users are always leaves (they cannot contain sub-entities) and are always
    checked.

    When variants are present in a scope the check is performed independently
    for each declared variant.  When no variants are present the check is
    variant-blind.

    Top-level ``user`` declarations in the file are also checked.
    """
    errors: list[ValidationError] = []
    for system in arch_file.systems:
        for v in _check_variants_for(_collect_system_variants(system)):
            errors.extend(_fully_connected_system(system, v))
    for comp in arch_file.components:
        for v in _check_variants_for(_collect_component_variants(comp)):
            errors.extend(_fully_connected_component(comp, v))
    for user in arch_file.users:
        user_variants = set(user.variants)
        for ref in user.requires + user.provides:
            user_variants.update(ref.variants)
        for v in _check_variants_for(user_variants):
            if _active(user.variants, v) and _no_active_ports(user.requires, user.provides, v):
                label = _entity_label(user.name, user.qualified_name)
                errors.append(
                    ValidationError(message=(f"User '{label}'{_variant_label(v)} has no ports (requires or provides)."))
                )
    return errors
