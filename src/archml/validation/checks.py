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
       the hierarchy.

    3. **Unwired ports** (error): Every port of every sub-entity must be
       accounted for within its enclosing scope: either wired by a ``connect``
       statement or explicitly promoted to the enclosing boundary with
       ``expose``.  A port that is neither wired nor exposed is a validation
       error.

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


def _check_interface_propagation(arch_file: ArchFile) -> list[ValidationError]:
    """Return errors for interfaces not propagated to any direct member.

    For every non-leaf component or system that declares interfaces in
    ``requires`` or ``provides``, at least one direct child must declare
    the same interface.  Leaf entities (no children) are exempt because
    they have no members to delegate to.
    """
    errors: list[ValidationError] = []

    def _check_component(component: Component) -> None:
        if component.components:
            member_provides = {_iface_key(r) for sub in component.components for r in sub.provides}
            member_requires = {_iface_key(r) for sub in component.components for r in sub.requires}
            label = _entity_label(component.name, component.qualified_name)
            for ref in component.provides:
                if _iface_key(ref) not in member_provides:
                    errors.append(
                        ValidationError(
                            message=(
                                f"Component '{label}' provides interface '{ref.name}' but no sub-component provides it."
                            )
                        )
                    )
            for ref in component.requires:
                if _iface_key(ref) not in member_requires:
                    errors.append(
                        ValidationError(
                            message=(
                                f"Component '{label}' requires interface '{ref.name}' but no sub-component requires it."
                            )
                        )
                    )
        for sub in component.components:
            _check_component(sub)

    def _check_system(system: System) -> None:
        has_members = bool(system.components or system.systems or system.users)
        if has_members:
            member_provides = (
                {_iface_key(r) for comp in system.components for r in comp.provides}
                | {_iface_key(r) for sub in system.systems for r in sub.provides}
                | {_iface_key(r) for user in system.users for r in user.provides}
            )
            member_requires = (
                {_iface_key(r) for comp in system.components for r in comp.requires}
                | {_iface_key(r) for sub in system.systems for r in sub.requires}
                | {_iface_key(r) for user in system.users for r in user.requires}
            )
            label = _entity_label(system.name, system.qualified_name)
            for ref in system.provides:
                if _iface_key(ref) not in member_provides:
                    errors.append(
                        ValidationError(
                            message=(f"System '{label}' provides interface '{ref.name}' but no member provides it.")
                        )
                    )
            for ref in system.requires:
                if _iface_key(ref) not in member_requires:
                    errors.append(
                        ValidationError(
                            message=(f"System '{label}' requires interface '{ref.name}' but no member requires it.")
                        )
                    )
        for sub in system.systems:
            _check_system(sub)
        for comp in system.components:
            _check_component(comp)

    for system in arch_file.systems:
        _check_system(system)
    for component in arch_file.components:
        _check_component(component)

    return errors


def _effective_port_name(ref: InterfaceRef) -> str:
    """Return the effective port name for an interface reference.

    When no explicit ``as`` alias is given, the port name defaults to the
    interface name.
    """
    return ref.port_name if ref.port_name is not None else ref.name


def _wired_ports(
    connects: list[ConnectDef],
    exposes: list[ExposeDef],
) -> dict[str, set[str]]:
    """Build a map from child entity name to the set of its wired port names.

    A port is considered wired when it appears in a ``connect`` statement as
    ``Entity.port`` (either side) or in an ``expose`` statement as
    ``Entity.port``.  Ports on the current scope's own boundary (where the
    entity name is omitted) are not sub-entity ports and are not tracked here.
    """
    wired: dict[str, set[str]] = {}
    for conn in connects:
        if conn.src_entity is not None and conn.src_port is not None:
            wired.setdefault(conn.src_entity, set()).add(conn.src_port)
        if conn.dst_entity is not None and conn.dst_port is not None:
            wired.setdefault(conn.dst_entity, set()).add(conn.dst_port)
    for exp in exposes:
        wired.setdefault(exp.entity, set()).add(exp.port)
    return wired


def _check_unwired_ports(arch_file: ArchFile) -> list[ValidationError]:
    """Return errors for sub-entity ports not wired by connect or expose.

    Every port of every sub-entity must be accounted for within the enclosing
    scope: either wired by a ``connect`` or promoted by ``expose``.  Leaf
    entities (no sub-entities) are exempt — their own ports are their
    boundary and need no internal wiring.
    """
    errors: list[ValidationError] = []

    def _check_component_scope(comp: Component) -> None:
        if not comp.components:
            return  # leaf — nothing to wire
        wired = _wired_ports(comp.connects, comp.exposes)
        label = _entity_label(comp.name, comp.qualified_name)
        for sub in comp.components:
            sub_wired = wired.get(sub.name, set())
            for ref in sub.requires + sub.provides:
                port = _effective_port_name(ref)
                if port not in sub_wired:
                    errors.append(
                        ValidationError(
                            message=(
                                f"Component '{label}': port '{sub.name}.{port}'"
                                f" is neither wired by a connect nor exposed."
                            )
                        )
                    )
        for sub in comp.components:
            _check_component_scope(sub)

    def _check_system_scope(system: System) -> None:
        has_members = bool(system.components or system.systems or system.users)
        if not has_members:
            return  # leaf — nothing to wire
        wired = _wired_ports(system.connects, system.exposes)
        label = _entity_label(system.name, system.qualified_name)
        for comp in system.components:
            comp_wired = wired.get(comp.name, set())
            for ref in comp.requires + comp.provides:
                port = _effective_port_name(ref)
                if port not in comp_wired:
                    errors.append(
                        ValidationError(
                            message=(
                                f"System '{label}': port '{comp.name}.{port}'"
                                f" is neither wired by a connect nor exposed."
                            )
                        )
                    )
        for sub_sys in system.systems:
            sys_wired = wired.get(sub_sys.name, set())
            for ref in sub_sys.requires + sub_sys.provides:
                port = _effective_port_name(ref)
                if port not in sys_wired:
                    errors.append(
                        ValidationError(
                            message=(
                                f"System '{label}': port '{sub_sys.name}.{port}'"
                                f" is neither wired by a connect nor exposed."
                            )
                        )
                    )
        for user in system.users:
            user_wired = wired.get(user.name, set())
            for ref in user.requires + user.provides:
                port = _effective_port_name(ref)
                if port not in user_wired:
                    errors.append(
                        ValidationError(
                            message=(
                                f"System '{label}': port '{user.name}.{port}'"
                                f" is neither wired by a connect nor exposed."
                            )
                        )
                    )
        for sub_sys in system.systems:
            _check_system_scope(sub_sys)
        for comp in system.components:
            _check_component_scope(comp)

    for system in arch_file.systems:
        _check_system_scope(system)
    for comp in arch_file.components:
        _check_component_scope(comp)

    return errors
