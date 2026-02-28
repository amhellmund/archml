# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the ArchML business validation checks."""

import pytest

from archml.model.entities import (
    ArchFile,
    Component,
    Connection,
    ConnectionEndpoint,
    InterfaceDef,
    InterfaceRef,
    System,
    TypeDef,
)
from archml.model.types import (
    FieldDef,
    ListTypeRef,
    MapTypeRef,
    NamedTypeRef,
    OptionalTypeRef,
    PrimitiveType,
    PrimitiveTypeRef,
)
from archml.validation.checks import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
    validate,
)

# ###############
# Test Helpers
# ###############


def _iref(name: str, version: str | None = None) -> InterfaceRef:
    """Create an InterfaceRef."""
    return InterfaceRef(name=name, version=version)


def _conn(source: str, target: str, interface: str = "I") -> Connection:
    """Create a Connection between two named entities."""
    return Connection(
        source=ConnectionEndpoint(entity=source),
        target=ConnectionEndpoint(entity=target),
        interface=InterfaceRef(name=interface),
    )


def _pfield(name: str) -> FieldDef:
    """Create a FieldDef with a primitive String type."""
    return FieldDef(name=name, type=PrimitiveTypeRef(primitive=PrimitiveType.STRING))


def _nfield(name: str, type_name: str) -> FieldDef:
    """Create a FieldDef referencing a named type."""
    return FieldDef(name=name, type=NamedTypeRef(name=type_name))


def _lfield(name: str, element_type: str) -> FieldDef:
    """Create a FieldDef with a List<NamedType> type."""
    return FieldDef(name=name, type=ListTypeRef(element_type=NamedTypeRef(name=element_type)))


def _ofield(name: str, inner_type: str) -> FieldDef:
    """Create a FieldDef with an Optional<NamedType> type."""
    return FieldDef(name=name, type=OptionalTypeRef(inner_type=NamedTypeRef(name=inner_type)))


def _mfield(name: str, key_type: str, value_type: str) -> FieldDef:
    """Create a FieldDef with a Map<NamedKey, NamedValue> type."""
    return FieldDef(
        name=name,
        type=MapTypeRef(
            key_type=NamedTypeRef(name=key_type),
            value_type=NamedTypeRef(name=value_type),
        ),
    )


def _warnings(result: ValidationResult) -> list[str]:
    return [w.message for w in result.warnings]


def _errors(result: ValidationResult) -> list[str]:
    return [e.message for e in result.errors]


def _assert_clean(arch_file: ArchFile) -> None:
    result = validate(arch_file)
    assert result.warnings == [], f"Expected no warnings but got: {_warnings(result)}"
    assert result.errors == [], f"Expected no errors but got: {_errors(result)}"


def _assert_warning(arch_file: ArchFile, fragment: str) -> None:
    result = validate(arch_file)
    msgs = _warnings(result)
    assert any(fragment in m for m in msgs), (
        f"Expected warning containing {fragment!r} but got: {msgs}"
    )


def _assert_error(arch_file: ArchFile, fragment: str) -> None:
    result = validate(arch_file)
    msgs = _errors(result)
    assert any(fragment in m for m in msgs), (
        f"Expected error containing {fragment!r} but got: {msgs}"
    )


def _assert_no_warning(arch_file: ArchFile) -> None:
    result = validate(arch_file)
    assert result.warnings == [], f"Expected no warnings but got: {_warnings(result)}"


def _assert_no_error(arch_file: ArchFile) -> None:
    result = validate(arch_file)
    assert result.errors == [], f"Expected no errors but got: {_errors(result)}"


# ###############
# Isolated Entities
# ###############


class TestIsolatedEntities:
    """Check 1: Components/systems with no requires or provides yield a warning."""

    def test_empty_archfile_no_warnings(self) -> None:
        _assert_clean(ArchFile())

    def test_isolated_top_level_system_warns(self) -> None:
        arch = ArchFile(systems=[System(name="Standalone")])
        _assert_warning(arch, "System 'Standalone'")
        _assert_warning(arch, "isolated")

    def test_isolated_top_level_component_warns(self) -> None:
        arch = ArchFile(components=[Component(name="Orphan")])
        _assert_warning(arch, "Component 'Orphan'")
        _assert_warning(arch, "isolated")

    def test_system_with_provides_no_warning(self) -> None:
        arch = ArchFile(
            systems=[System(name="S", provides=[_iref("I")])]
        )
        _assert_no_warning(arch)

    def test_system_with_requires_no_warning(self) -> None:
        arch = ArchFile(
            systems=[System(name="S", requires=[_iref("I")])]
        )
        _assert_no_warning(arch)

    def test_component_with_provides_no_warning(self) -> None:
        arch = ArchFile(
            components=[Component(name="C", provides=[_iref("I")])]
        )
        _assert_no_warning(arch)

    def test_component_with_requires_no_warning(self) -> None:
        arch = ArchFile(
            components=[Component(name="C", requires=[_iref("I")])]
        )
        _assert_no_warning(arch)

    def test_nested_isolated_subsystem_warns(self) -> None:
        inner = System(name="Inner")
        outer = System(name="Outer", provides=[_iref("I")], systems=[inner])
        arch = ArchFile(systems=[outer])
        result = validate(arch)
        msgs = _warnings(result)
        assert any("Inner" in m for m in msgs), f"Expected warning for 'Inner' but got: {msgs}"
        # Outer has a provides, so no warning for it
        assert not any("Outer" in m for m in msgs), f"Unexpected warning for 'Outer': {msgs}"

    def test_nested_isolated_component_inside_system_warns(self) -> None:
        comp = Component(name="Worker")
        sys_ = System(name="S", provides=[_iref("I")], components=[comp])
        arch = ArchFile(systems=[sys_])
        _assert_warning(arch, "Component 'Worker'")

    def test_nested_component_inside_component_warns(self) -> None:
        inner = Component(name="Inner")
        outer = Component(name="Outer", provides=[_iref("I")], components=[inner])
        arch = ArchFile(components=[outer])
        _assert_warning(arch, "Component 'Inner'")

    def test_system_with_requires_and_provides_no_warning(self) -> None:
        arch = ArchFile(
            systems=[System(name="S", requires=[_iref("A")], provides=[_iref("B")])]
        )
        _assert_no_warning(arch)

    def test_qualified_name_used_in_warning_when_set(self) -> None:
        comp = Component(name="Worker", qualified_name="MySystem.Worker")
        sys_ = System(name="MySystem", provides=[_iref("I")], components=[comp])
        arch = ArchFile(systems=[sys_])
        _assert_warning(arch, "MySystem.Worker")

    def test_multiple_isolated_entities_all_warned(self) -> None:
        arch = ArchFile(
            systems=[System(name="S1"), System(name="S2")],
            components=[Component(name="C1")],
        )
        result = validate(arch)
        msgs = _warnings(result)
        assert len(msgs) == 3
        assert any("S1" in m for m in msgs)
        assert any("S2" in m for m in msgs)
        assert any("C1" in m for m in msgs)

    def test_isolated_warning_does_not_fail_validation(self) -> None:
        arch = ArchFile(systems=[System(name="Standalone")])
        result = validate(arch)
        assert result.warnings  # has warnings
        assert not result.has_errors  # but no errors


# ###############
# Connection Cycles
# ###############


class TestConnectionCycles:
    """Check 2: Cycles in the connection graph within any scope are errors."""

    def test_no_connections_no_error(self) -> None:
        arch = ArchFile(
            systems=[
                System(name="S", provides=[_iref("I")])
            ]
        )
        _assert_no_error(arch)

    def test_direct_cycle_in_system(self) -> None:
        # A -> B -> A within a system's connections
        sys_ = System(
            name="S",
            provides=[_iref("I")],
            connections=[_conn("A", "B"), _conn("B", "A")],
        )
        arch = ArchFile(systems=[sys_])
        _assert_error(arch, "Connection cycle")
        _assert_error(arch, "'S'")

    def test_three_node_cycle_in_system(self) -> None:
        sys_ = System(
            name="S",
            provides=[_iref("I")],
            connections=[_conn("A", "B"), _conn("B", "C"), _conn("C", "A")],
        )
        arch = ArchFile(systems=[sys_])
        _assert_error(arch, "Connection cycle")

    def test_self_loop(self) -> None:
        sys_ = System(
            name="S",
            provides=[_iref("I")],
            connections=[_conn("A", "A")],
        )
        arch = ArchFile(systems=[sys_])
        _assert_error(arch, "Connection cycle")

    def test_linear_connections_no_cycle(self) -> None:
        sys_ = System(
            name="S",
            provides=[_iref("I")],
            connections=[_conn("A", "B"), _conn("B", "C")],
        )
        arch = ArchFile(systems=[sys_])
        _assert_no_error(arch)

    def test_diamond_no_cycle(self) -> None:
        # A -> B, A -> C, B -> D, C -> D — acyclic diamond
        sys_ = System(
            name="S",
            provides=[_iref("I")],
            connections=[
                _conn("A", "B"),
                _conn("A", "C"),
                _conn("B", "D"),
                _conn("C", "D"),
            ],
        )
        arch = ArchFile(systems=[sys_])
        _assert_no_error(arch)

    def test_cycle_in_component_scope(self) -> None:
        comp = Component(
            name="C",
            provides=[_iref("I")],
            connections=[_conn("X", "Y"), _conn("Y", "X")],
        )
        arch = ArchFile(components=[comp])
        _assert_error(arch, "Connection cycle")
        _assert_error(arch, "'C'")

    def test_cycle_in_nested_subsystem(self) -> None:
        inner = System(
            name="Inner",
            provides=[_iref("I")],
            connections=[_conn("P", "Q"), _conn("Q", "P")],
        )
        outer = System(name="Outer", provides=[_iref("I")], systems=[inner])
        arch = ArchFile(systems=[outer])
        _assert_error(arch, "Connection cycle")
        _assert_error(arch, "Inner")

    def test_parent_acyclic_child_cyclic_reports_child(self) -> None:
        inner = System(
            name="Inner",
            provides=[_iref("I")],
            connections=[_conn("X", "Y"), _conn("Y", "X")],
        )
        outer = System(
            name="Outer",
            provides=[_iref("I")],
            systems=[inner],
            connections=[_conn("Inner", "Other")],  # acyclic at outer level
        )
        arch = ArchFile(systems=[outer])
        result = validate(arch)
        msgs = _errors(result)
        assert any("Inner" in m for m in msgs)
        # Outer should NOT have a cycle error
        assert not any("'Outer'" in m and "cycle" in m.lower() for m in msgs)

    def test_cycle_error_includes_cycle_path(self) -> None:
        sys_ = System(
            name="S",
            provides=[_iref("I")],
            connections=[_conn("A", "B"), _conn("B", "A")],
        )
        arch = ArchFile(systems=[sys_])
        result = validate(arch)
        msgs = _errors(result)
        # The cycle path should show A -> B -> A or B -> A -> B
        assert any("A" in m and "B" in m and "->" in m for m in msgs)

    def test_top_level_component_connections_checked(self) -> None:
        comp = Component(
            name="Root",
            provides=[_iref("I")],
            connections=[_conn("X", "Y"), _conn("Y", "Z"), _conn("Z", "X")],
        )
        arch = ArchFile(components=[comp])
        _assert_error(arch, "Connection cycle")


# ###############
# Type Definition Cycles
# ###############


class TestTypeCycles:
    """Check 3: Recursive type or interface definition cycles are errors."""

    def test_no_types_no_error(self) -> None:
        _assert_clean(ArchFile())

    def test_types_with_only_primitives_no_error(self) -> None:
        arch = ArchFile(
            types=[TypeDef(name="Address", fields=[_pfield("street"), _pfield("city")])]
        )
        _assert_no_error(arch)

    def test_direct_self_reference_type(self) -> None:
        # type Node { next: Node }
        arch = ArchFile(
            types=[TypeDef(name="Node", fields=[_nfield("next", "Node")])]
        )
        _assert_error(arch, "Recursive type definition cycle")
        _assert_error(arch, "Node")

    def test_two_type_mutual_cycle(self) -> None:
        # type A { b: B }  type B { a: A }
        arch = ArchFile(
            types=[
                TypeDef(name="A", fields=[_nfield("b", "B")]),
                TypeDef(name="B", fields=[_nfield("a", "A")]),
            ]
        )
        _assert_error(arch, "Recursive type definition cycle")

    def test_three_type_cycle(self) -> None:
        # A -> B -> C -> A
        arch = ArchFile(
            types=[
                TypeDef(name="A", fields=[_nfield("b", "B")]),
                TypeDef(name="B", fields=[_nfield("c", "C")]),
                TypeDef(name="C", fields=[_nfield("a", "A")]),
            ]
        )
        _assert_error(arch, "Recursive type definition cycle")

    def test_acyclic_chain_no_error(self) -> None:
        # A -> B -> C (no cycle)
        arch = ArchFile(
            types=[
                TypeDef(name="A", fields=[_nfield("b", "B")]),
                TypeDef(name="B", fields=[_nfield("c", "C")]),
                TypeDef(name="C", fields=[_pfield("value")]),
            ]
        )
        _assert_no_error(arch)

    def test_cycle_through_list_type(self) -> None:
        # type Tree { children: List<Tree> }
        arch = ArchFile(
            types=[TypeDef(name="Tree", fields=[_lfield("children", "Tree")])]
        )
        _assert_error(arch, "Recursive type definition cycle")
        _assert_error(arch, "Tree")

    def test_cycle_through_optional_type(self) -> None:
        # type Node { next: Optional<Node> }
        arch = ArchFile(
            types=[TypeDef(name="Node", fields=[_ofield("next", "Node")])]
        )
        _assert_error(arch, "Recursive type definition cycle")

    def test_cycle_through_map_value(self) -> None:
        # type Registry { entries: Map<String, Registry> }
        # Note: key_type is NamedTypeRef pointing to a non-defined name (no cycle via key)
        arch = ArchFile(
            types=[
                TypeDef(
                    name="Registry",
                    fields=[
                        FieldDef(
                            name="entries",
                            type=MapTypeRef(
                                key_type=PrimitiveTypeRef(primitive=PrimitiveType.STRING),
                                value_type=NamedTypeRef(name="Registry"),
                            ),
                        )
                    ],
                )
            ]
        )
        _assert_error(arch, "Recursive type definition cycle")

    def test_interface_self_reference_cycle(self) -> None:
        # interface A { nested: A }
        arch = ArchFile(
            interfaces=[InterfaceDef(name="A", fields=[_nfield("nested", "A")])]
        )
        _assert_error(arch, "Recursive type definition cycle")
        _assert_error(arch, "A")

    def test_interface_type_cross_cycle(self) -> None:
        # interface A { b: B }  type B { a: A }
        arch = ArchFile(
            interfaces=[InterfaceDef(name="A", fields=[_nfield("b", "B")])],
            types=[TypeDef(name="B", fields=[_nfield("a", "A")])],
        )
        _assert_error(arch, "Recursive type definition cycle")

    def test_enum_reference_not_a_cycle(self) -> None:
        # Enums have no fields and are leaf nodes — referencing one cannot form a cycle.
        from archml.model.entities import EnumDef

        arch = ArchFile(
            enums=[EnumDef(name="Color", values=["RED", "GREEN", "BLUE"])],
            types=[TypeDef(name="Palette", fields=[_nfield("primary", "Color")])],
        )
        _assert_no_error(arch)

    def test_type_references_undefined_name_no_cycle(self) -> None:
        # A reference to an unknown name is ignored by the cycle check
        # (structural resolution is handled by semantic analysis).
        arch = ArchFile(
            types=[TypeDef(name="A", fields=[_nfield("x", "Unknown")])]
        )
        _assert_no_error(arch)

    def test_two_independent_types_no_cycle(self) -> None:
        arch = ArchFile(
            types=[
                TypeDef(name="X", fields=[_pfield("a")]),
                TypeDef(name="Y", fields=[_pfield("b")]),
            ]
        )
        _assert_no_error(arch)


# ###############
# Interface Propagation
# ###############


class TestInterfacePropagation:
    """Check 4: Upstream interface declarations must be grounded in at least one member."""

    # ---- System propagation ----

    def test_leaf_system_with_provides_no_error(self) -> None:
        # A system with no members is a leaf — propagation check does not apply.
        arch = ArchFile(
            systems=[System(name="S", provides=[_iref("I")])]
        )
        _assert_no_error(arch)

    def test_leaf_system_with_requires_no_error(self) -> None:
        arch = ArchFile(
            systems=[System(name="S", requires=[_iref("I")])]
        )
        _assert_no_error(arch)

    def test_system_provides_propagated_to_component(self) -> None:
        comp = Component(name="C", provides=[_iref("I")])
        sys_ = System(name="S", provides=[_iref("I")], components=[comp])
        arch = ArchFile(systems=[sys_])
        _assert_no_error(arch)

    def test_system_requires_propagated_to_component(self) -> None:
        comp = Component(name="C", requires=[_iref("I")])
        sys_ = System(name="S", requires=[_iref("I")], components=[comp])
        arch = ArchFile(systems=[sys_])
        _assert_no_error(arch)

    def test_system_provides_not_propagated_error(self) -> None:
        comp = Component(name="C", requires=[_iref("OtherInterface")])
        sys_ = System(name="S", provides=[_iref("I")], components=[comp])
        arch = ArchFile(systems=[sys_])
        _assert_error(arch, "System 'S'")
        _assert_error(arch, "provides interface 'I'")
        _assert_error(arch, "no member provides it")

    def test_system_requires_not_propagated_error(self) -> None:
        comp = Component(name="C", provides=[_iref("OtherInterface")])
        sys_ = System(name="S", requires=[_iref("I")], components=[comp])
        arch = ArchFile(systems=[sys_])
        _assert_error(arch, "System 'S'")
        _assert_error(arch, "requires interface 'I'")
        _assert_error(arch, "no member requires it")

    def test_system_provides_propagated_to_subsystem(self) -> None:
        sub = System(name="Sub", provides=[_iref("I")])
        outer = System(name="Outer", provides=[_iref("I")], systems=[sub])
        arch = ArchFile(systems=[outer])
        _assert_no_error(arch)

    def test_system_provides_not_propagated_to_subsystem_error(self) -> None:
        sub = System(name="Sub", provides=[_iref("Other")])
        outer = System(name="Outer", provides=[_iref("I")], systems=[sub])
        arch = ArchFile(systems=[outer])
        _assert_error(arch, "System 'Outer'")
        _assert_error(arch, "provides interface 'I'")

    def test_system_no_interfaces_with_members_no_error(self) -> None:
        comp = Component(name="C", provides=[_iref("I")])
        sys_ = System(name="S", components=[comp])
        arch = ArchFile(systems=[sys_])
        # S has no requires/provides, so there is nothing to propagate.
        # But S itself is isolated → warning only, no error.
        _assert_no_error(arch)

    def test_only_one_member_needs_interface(self) -> None:
        # Two members; only one provides the interface — still valid.
        c1 = Component(name="C1", provides=[_iref("I")])
        c2 = Component(name="C2", requires=[_iref("I")])
        sys_ = System(name="S", provides=[_iref("I")], components=[c1, c2])
        arch = ArchFile(systems=[sys_])
        _assert_no_error(arch)

    def test_versioned_interface_exact_match_passes(self) -> None:
        comp = Component(name="C", provides=[_iref("I", "v2")])
        sys_ = System(name="S", provides=[_iref("I", "v2")], components=[comp])
        arch = ArchFile(systems=[sys_])
        _assert_no_error(arch)

    def test_versioned_interface_version_mismatch_error(self) -> None:
        # System provides I@v1 but member provides I@v2 — mismatch.
        comp = Component(name="C", provides=[_iref("I", "v2")])
        sys_ = System(name="S", provides=[_iref("I", "v1")], components=[comp])
        arch = ArchFile(systems=[sys_])
        _assert_error(arch, "provides interface 'I'")

    def test_versioned_vs_unversioned_mismatch_error(self) -> None:
        # System provides I@v1 but member provides unversioned I.
        comp = Component(name="C", provides=[_iref("I")])
        sys_ = System(name="S", provides=[_iref("I", "v1")], components=[comp])
        arch = ArchFile(systems=[sys_])
        _assert_error(arch, "provides interface 'I'")

    def test_nested_system_propagation_checked_recursively(self) -> None:
        # Both outer and inner must satisfy propagation independently.
        leaf_comp = Component(name="Leaf", provides=[_iref("Inner")])
        inner = System(name="Inner", provides=[_iref("Inner")], components=[leaf_comp])
        # Inner provides 'Inner' ✓, but outer provides 'Outer' and only has
        # inner as member. Inner does not provide 'Outer'.
        outer = System(name="Outer", provides=[_iref("Outer")], systems=[inner])
        arch = ArchFile(systems=[outer])
        _assert_error(arch, "System 'Outer'")
        _assert_error(arch, "provides interface 'Outer'")

    def test_qualified_name_used_in_error_when_set(self) -> None:
        comp = Component(name="C", requires=[_iref("Other")])
        sys_ = System(
            name="S",
            qualified_name="Root.S",
            provides=[_iref("I")],
            components=[comp],
        )
        arch = ArchFile(systems=[sys_])
        _assert_error(arch, "'Root.S'")

    # ---- Component propagation ----

    def test_leaf_component_with_provides_no_error(self) -> None:
        arch = ArchFile(
            components=[Component(name="C", provides=[_iref("I")])]
        )
        _assert_no_error(arch)

    def test_component_provides_propagated_to_subcomponent(self) -> None:
        sub = Component(name="Sub", provides=[_iref("I")])
        outer = Component(name="Outer", provides=[_iref("I")], components=[sub])
        arch = ArchFile(components=[outer])
        _assert_no_error(arch)

    def test_component_provides_not_propagated_error(self) -> None:
        sub = Component(name="Sub", requires=[_iref("Other")])
        outer = Component(name="Outer", provides=[_iref("I")], components=[sub])
        arch = ArchFile(components=[outer])
        _assert_error(arch, "Component 'Outer'")
        _assert_error(arch, "provides interface 'I'")
        _assert_error(arch, "no sub-component provides it")

    def test_component_requires_not_propagated_error(self) -> None:
        sub = Component(name="Sub", provides=[_iref("Other")])
        outer = Component(name="Outer", requires=[_iref("I")], components=[sub])
        arch = ArchFile(components=[outer])
        _assert_error(arch, "Component 'Outer'")
        _assert_error(arch, "requires interface 'I'")
        _assert_error(arch, "no sub-component requires it")

    def test_component_propagation_checked_recursively(self) -> None:
        # outer provides I, mid provides I and requires J, inner does not require J.
        inner = Component(name="Inner", provides=[_iref("I")])
        mid = Component(
            name="Mid",
            provides=[_iref("I")],
            requires=[_iref("J")],
            components=[inner],
        )
        outer = Component(name="Outer", provides=[_iref("I")], components=[mid])
        arch = ArchFile(components=[outer])
        # mid requires J but no child requires J → error for mid
        _assert_error(arch, "Component 'Mid'")
        _assert_error(arch, "requires interface 'J'")


# ###############
# Integration
# ###############


class TestValidationResult:
    """Verify the ValidationResult contract."""

    def test_has_errors_false_when_no_errors(self) -> None:
        result = validate(ArchFile())
        assert not result.has_errors

    def test_has_errors_true_when_errors_present(self) -> None:
        # A type cycle is an error.
        arch = ArchFile(
            types=[TypeDef(name="A", fields=[_nfield("self", "A")])]
        )
        result = validate(arch)
        assert result.has_errors

    def test_warnings_present_but_no_errors(self) -> None:
        arch = ArchFile(systems=[System(name="Lone")])
        result = validate(arch)
        assert result.warnings
        assert not result.has_errors

    def test_multiple_check_failures_reported_together(self) -> None:
        # An isolated system (warning) AND a connection cycle (error) in one archfile.
        sys_ = System(
            name="Bad",
            connections=[_conn("X", "Y"), _conn("Y", "X")],
        )
        arch = ArchFile(systems=[sys_])
        result = validate(arch)
        assert result.warnings  # isolated (no requires/provides)
        assert result.has_errors  # connection cycle

    def test_empty_archfile_is_fully_valid(self) -> None:
        result = validate(ArchFile())
        assert result == ValidationResult()
        assert not result.has_errors
