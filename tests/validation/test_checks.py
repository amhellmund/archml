# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the ArchML business validation checks."""

from archml.model.entities import (
    ArchFile,
    Component,
    ConnectDef,
    ExposeDef,
    InterfaceDef,
    InterfaceRef,
    System,
    TypeDef,
    UserDef,
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
    ValidationResult,
    validate,
)

# ###############
# Test Helpers
# ###############


def _iref(name: str) -> InterfaceRef:
    """Create an InterfaceRef."""
    return InterfaceRef(name=name)


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
    assert any(fragment in m for m in msgs), f"Expected warning containing {fragment!r} but got: {msgs}"


def _assert_error(arch_file: ArchFile, fragment: str) -> None:
    result = validate(arch_file)
    msgs = _errors(result)
    assert any(fragment in m for m in msgs), f"Expected error containing {fragment!r} but got: {msgs}"


def _assert_no_warning(arch_file: ArchFile) -> None:
    result = validate(arch_file)
    assert result.warnings == [], f"Expected no warnings but got: {_warnings(result)}"


def _assert_no_error(arch_file: ArchFile) -> None:
    result = validate(arch_file)
    assert result.errors == [], f"Expected no errors but got: {_errors(result)}"


# ###############
# Type Definition Cycles
# ###############


class TestTypeCycles:
    """Check: Recursive type or interface definition cycles are errors."""

    def test_no_types_no_error(self) -> None:
        _assert_clean(ArchFile())

    def test_types_with_only_primitives_no_error(self) -> None:
        arch = ArchFile(types=[TypeDef(name="Address", fields=[_pfield("street"), _pfield("city")])])
        _assert_no_error(arch)

    def test_direct_self_reference_type(self) -> None:
        # type Node { next: Node }
        arch = ArchFile(types=[TypeDef(name="Node", fields=[_nfield("next", "Node")])])
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
        arch = ArchFile(types=[TypeDef(name="Tree", fields=[_lfield("children", "Tree")])])
        _assert_error(arch, "Recursive type definition cycle")
        _assert_error(arch, "Tree")

    def test_cycle_through_optional_type(self) -> None:
        # type Node { next: Optional<Node> }
        arch = ArchFile(types=[TypeDef(name="Node", fields=[_ofield("next", "Node")])])
        _assert_error(arch, "Recursive type definition cycle")

    def test_cycle_through_map_value(self) -> None:
        # type Registry { entries: Map<String, Registry> }
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
        arch = ArchFile(interfaces=[InterfaceDef(name="A", fields=[_nfield("nested", "A")])])
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
        arch = ArchFile(types=[TypeDef(name="A", fields=[_nfield("x", "Unknown")])])
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
    """Check: Upstream interface declarations must be grounded in at least one member."""

    # ---- System propagation ----

    def test_leaf_system_with_provides_no_error(self) -> None:
        # A system with no members is a leaf — propagation check does not apply.
        arch = ArchFile(systems=[System(name="S", provides=[_iref("I")])])
        _assert_no_error(arch)

    def test_leaf_system_with_requires_no_error(self) -> None:
        arch = ArchFile(systems=[System(name="S", requires=[_iref("I")])])
        _assert_no_error(arch)

    def test_system_provides_propagated_to_component(self) -> None:
        comp = Component(name="C", provides=[_iref("I")])
        sys_ = System(
            name="S",
            provides=[_iref("I")],
            components=[comp],
            exposes=[ExposeDef(entity="C", port="I")],
        )
        arch = ArchFile(systems=[sys_])
        _assert_no_error(arch)

    def test_system_requires_propagated_to_component(self) -> None:
        comp = Component(name="C", requires=[_iref("I")])
        sys_ = System(
            name="S",
            requires=[_iref("I")],
            components=[comp],
            exposes=[ExposeDef(entity="C", port="I")],
        )
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
        outer = System(
            name="Outer",
            provides=[_iref("I")],
            systems=[sub],
            exposes=[ExposeDef(entity="Sub", port="I")],
        )
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
        sys_ = System(
            name="S",
            components=[comp],
            exposes=[ExposeDef(entity="C", port="I")],
        )
        arch = ArchFile(systems=[sys_])
        # S has no requires/provides, so there is nothing to propagate — no error.
        _assert_no_error(arch)

    def test_only_one_member_needs_interface(self) -> None:
        # Two members; only one provides the interface — still valid.
        c1 = Component(name="C1", provides=[_iref("I")])
        c2 = Component(name="C2", requires=[_iref("I")])
        sys_ = System(
            name="S",
            provides=[_iref("I")],
            components=[c1, c2],
            connects=[ConnectDef(src_entity="C1", src_port="I", channel="i", dst_entity="C2", dst_port="I")],
        )
        arch = ArchFile(systems=[sys_])
        _assert_no_error(arch)

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
            qualified_name="Root::S",
            provides=[_iref("I")],
            components=[comp],
        )
        arch = ArchFile(systems=[sys_])
        _assert_error(arch, "'Root::S'")

    # ---- Component propagation ----

    def test_leaf_component_with_provides_no_error(self) -> None:
        arch = ArchFile(components=[Component(name="C", provides=[_iref("I")])])
        _assert_no_error(arch)

    def test_component_provides_propagated_to_subcomponent(self) -> None:
        sub = Component(name="Sub", provides=[_iref("I")])
        outer = Component(
            name="Outer",
            provides=[_iref("I")],
            components=[sub],
            exposes=[ExposeDef(entity="Sub", port="I")],
        )
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
# Interface Propagation with Users
# ###############


class TestInterfacePropagationWithUsers:
    """Interface propagation must consider user members alongside components/systems."""

    def test_system_provides_satisfied_by_user(self) -> None:
        user = UserDef(name="Client", provides=[_iref("I")])
        sys_ = System(
            name="S",
            provides=[_iref("I")],
            users=[user],
            exposes=[ExposeDef(entity="Client", port="I")],
        )
        arch = ArchFile(systems=[sys_])
        _assert_no_error(arch)

    def test_system_requires_satisfied_by_user(self) -> None:
        user = UserDef(name="Client", requires=[_iref("I")])
        sys_ = System(
            name="S",
            requires=[_iref("I")],
            users=[user],
            exposes=[ExposeDef(entity="Client", port="I")],
        )
        arch = ArchFile(systems=[sys_])
        _assert_no_error(arch)

    def test_system_provides_not_satisfied_when_user_has_other_interface(self) -> None:
        user = UserDef(name="Client", provides=[_iref("Other")])
        sys_ = System(
            name="S",
            provides=[_iref("I")],
            users=[user],
            exposes=[ExposeDef(entity="Client", port="Other")],
        )
        arch = ArchFile(systems=[sys_])
        _assert_error(arch, "provides interface 'I'")
        _assert_error(arch, "no member provides it")

    def test_system_requires_satisfied_by_user_not_component(self) -> None:
        # Only the user satisfies the system's requires — no component needed.
        user = UserDef(name="Admin", requires=[_iref("AdminAPI")])
        comp = Component(name="Service", provides=[_iref("AdminAPI")])
        sys_ = System(
            name="S",
            requires=[_iref("AdminAPI")],
            users=[user],
            components=[comp],
            connects=[ConnectDef(src_entity="Service", src_port="AdminAPI", dst_entity="Admin", dst_port="AdminAPI")],
        )
        arch = ArchFile(systems=[sys_])
        _assert_no_error(arch)


# ###############
# Unwired Ports
# ###############


class TestUnwiredPorts:
    """Every sub-entity port must be wired by connect or promoted by expose."""

    # ---- Leaf entities are exempt ----

    def test_leaf_component_ports_not_checked(self) -> None:
        arch = ArchFile(components=[Component(name="C", provides=[_iref("I")])])
        _assert_no_error(arch)

    def test_leaf_system_ports_not_checked(self) -> None:
        arch = ArchFile(systems=[System(name="S", requires=[_iref("I")])])
        _assert_no_error(arch)

    def test_component_with_no_sub_components_no_error(self) -> None:
        arch = ArchFile(components=[Component(name="C", provides=[_iref("I")])])
        _assert_no_error(arch)

    # ---- Component scope: sub-component ports must be wired ----

    def test_sub_component_port_wired_by_connect_no_error(self) -> None:
        sub_a = Component(name="A", provides=[_iref("I")])
        sub_b = Component(name="B", requires=[_iref("I")])
        outer = Component(
            name="Outer",
            components=[sub_a, sub_b],
            connects=[ConnectDef(src_entity="A", src_port="I", channel="i", dst_entity="B", dst_port="I")],
        )
        arch = ArchFile(components=[outer])
        _assert_no_error(arch)

    def test_sub_component_port_promoted_by_expose_no_error(self) -> None:
        sub = Component(name="Sub", provides=[_iref("I")])
        outer = Component(
            name="Outer",
            components=[sub],
            exposes=[ExposeDef(entity="Sub", port="I")],
        )
        arch = ArchFile(components=[outer])
        _assert_no_error(arch)

    def test_sub_component_port_not_wired_error(self) -> None:
        sub = Component(name="Sub", provides=[_iref("I")])
        outer = Component(name="Outer", components=[sub])
        arch = ArchFile(components=[outer])
        _assert_error(arch, "Component 'Outer'")
        _assert_error(arch, "port 'Sub.I'")
        _assert_error(arch, "neither wired by a connect nor exposed")

    def test_sub_component_requires_port_not_wired_error(self) -> None:
        sub = Component(name="Sub", requires=[_iref("I")])
        outer = Component(name="Outer", components=[sub])
        arch = ArchFile(components=[outer])
        _assert_error(arch, "port 'Sub.I'")

    def test_explicit_port_alias_must_be_used_in_connect(self) -> None:
        # Port declared as `requires Foo as in_port` — the connect must
        # reference `Sub.in_port`, not `Sub.Foo`.
        sub = Component(name="Sub", requires=[InterfaceRef(name="Foo", port_name="in_port")])
        outer = Component(
            name="Outer",
            components=[sub],
            exposes=[ExposeDef(entity="Sub", port="in_port")],
        )
        arch = ArchFile(components=[outer])
        _assert_no_error(arch)

    def test_wrong_port_name_in_expose_still_unwired(self) -> None:
        # expose Sub.Foo but the actual port is named `in_port` — mismatch.
        sub = Component(name="Sub", requires=[InterfaceRef(name="Foo", port_name="in_port")])
        outer = Component(
            name="Outer",
            components=[sub],
            exposes=[ExposeDef(entity="Sub", port="Foo")],  # wrong port name
        )
        arch = ArchFile(components=[outer])
        _assert_error(arch, "port 'Sub.in_port'")

    def test_multiple_sub_component_ports_all_wired_no_error(self) -> None:
        a = Component(name="A", provides=[_iref("X")], requires=[_iref("Y")])
        b = Component(name="B", provides=[_iref("Y")])
        outer = Component(
            name="Outer",
            components=[a, b],
            connects=[ConnectDef(src_entity="B", src_port="Y", dst_entity="A", dst_port="Y")],
            exposes=[ExposeDef(entity="A", port="X")],
        )
        arch = ArchFile(components=[outer])
        _assert_no_error(arch)

    def test_one_of_two_ports_unwired_is_error(self) -> None:
        sub = Component(name="Sub", provides=[_iref("I")], requires=[_iref("J")])
        outer = Component(
            name="Outer",
            components=[sub],
            exposes=[ExposeDef(entity="Sub", port="I")],  # I wired, J not
        )
        arch = ArchFile(components=[outer])
        _assert_error(arch, "port 'Sub.J'")

    # ---- System scope: component/system/user ports must be wired ----

    def test_system_component_port_wired_by_connect_no_error(self) -> None:
        a = Component(name="A", provides=[_iref("I")])
        b = Component(name="B", requires=[_iref("I")])
        sys_ = System(
            name="S",
            components=[a, b],
            connects=[ConnectDef(src_entity="A", src_port="I", channel="i", dst_entity="B", dst_port="I")],
        )
        arch = ArchFile(systems=[sys_])
        _assert_no_error(arch)

    def test_system_component_port_not_wired_error(self) -> None:
        comp = Component(name="C", provides=[_iref("I")])
        sys_ = System(name="S", components=[comp])
        arch = ArchFile(systems=[sys_])
        _assert_error(arch, "System 'S'")
        _assert_error(arch, "port 'C.I'")
        _assert_error(arch, "neither wired by a connect nor exposed")

    def test_system_sub_system_port_not_wired_error(self) -> None:
        sub = System(name="Sub", provides=[_iref("I")])
        outer = System(name="Outer", systems=[sub])
        arch = ArchFile(systems=[outer])
        _assert_error(arch, "System 'Outer'")
        _assert_error(arch, "port 'Sub.I'")

    def test_system_sub_system_port_exposed_no_error(self) -> None:
        sub = System(name="Sub", provides=[_iref("I")])
        outer = System(
            name="Outer",
            systems=[sub],
            exposes=[ExposeDef(entity="Sub", port="I")],
        )
        arch = ArchFile(systems=[outer])
        _assert_no_error(arch)

    def test_system_user_port_not_wired_error(self) -> None:
        user = UserDef(name="Client", provides=[_iref("OrderRequest")])
        sys_ = System(name="S", users=[user])
        arch = ArchFile(systems=[sys_])
        _assert_error(arch, "System 'S'")
        _assert_error(arch, "port 'Client.OrderRequest'")

    def test_system_user_port_wired_by_connect_no_error(self) -> None:
        user = UserDef(name="Client", provides=[_iref("OrderRequest")])
        comp = Component(name="Service", requires=[_iref("OrderRequest")])
        sys_ = System(
            name="S",
            users=[user],
            components=[comp],
            connects=[
                ConnectDef(
                    src_entity="Client",
                    src_port="OrderRequest",
                    channel="orders",
                    dst_entity="Service",
                    dst_port="OrderRequest",
                )
            ],
        )
        arch = ArchFile(systems=[sys_])
        _assert_no_error(arch)

    def test_system_user_port_exposed_no_error(self) -> None:
        user = UserDef(name="Client", provides=[_iref("OrderRequest")])
        sys_ = System(
            name="S",
            users=[user],
            exposes=[ExposeDef(entity="Client", port="OrderRequest")],
        )
        arch = ArchFile(systems=[sys_])
        _assert_no_error(arch)

    # ---- Qualified name used in error messages ----

    def test_qualified_name_used_in_error(self) -> None:
        sub = Component(name="Sub", provides=[_iref("I")])
        outer = Component(name="Outer", qualified_name="ns::Outer", components=[sub])
        arch = ArchFile(components=[outer])
        _assert_error(arch, "Component 'ns::Outer'")

    # ---- Recursive checking ----

    def test_nested_component_checked_recursively(self) -> None:
        inner = Component(name="Inner", provides=[_iref("I")])
        mid = Component(
            name="Mid",
            components=[inner],
            exposes=[ExposeDef(entity="Inner", port="I")],
        )
        outer = Component(
            name="Outer",
            components=[mid],
            exposes=[ExposeDef(entity="Mid", port="I")],
        )
        arch = ArchFile(components=[outer])
        _assert_no_error(arch)

    def test_unwired_port_in_nested_scope_reported(self) -> None:
        inner = Component(name="Inner", provides=[_iref("I")])
        mid = Component(name="Mid", components=[inner])  # Inner.I not wired
        outer = Component(
            name="Outer",
            components=[mid],
        )
        arch = ArchFile(components=[outer])
        _assert_error(arch, "port 'Inner.I'")

    def test_nested_system_checked_recursively(self) -> None:
        comp = Component(name="C", provides=[_iref("I")])
        inner_sys = System(
            name="Inner",
            components=[comp],
            exposes=[ExposeDef(entity="C", port="I")],
        )
        outer_sys = System(
            name="Outer",
            systems=[inner_sys],
            exposes=[ExposeDef(entity="Inner", port="I")],
        )
        arch = ArchFile(systems=[outer_sys])
        _assert_no_error(arch)


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
        arch = ArchFile(types=[TypeDef(name="A", fields=[_nfield("self", "A")])])
        result = validate(arch)
        assert result.has_errors

    def test_multiple_check_failures_reported_together(self) -> None:
        # Type cycle (error) + interface not propagated (error) in one archfile.
        arch = ArchFile(
            types=[TypeDef(name="A", fields=[_nfield("self", "A")])],
            systems=[
                System(
                    name="S",
                    provides=[_iref("I")],
                    components=[Component(name="C", requires=[_iref("Other")])],
                )
            ],
        )
        result = validate(arch)
        assert len(result.errors) >= 2

    def test_empty_archfile_is_fully_valid(self) -> None:
        result = validate(ArchFile())
        assert result == ValidationResult()
        assert not result.has_errors


# ###############
# Per-Variant Unwired Ports
# ###############


def _iref_v(name: str, *variants: str) -> InterfaceRef:
    """Create an InterfaceRef with variant annotations."""
    return InterfaceRef(name=name, variants=list(variants))


def _conn(src_e: str, src_p: str, dst_e: str, dst_p: str, *variants: str) -> ConnectDef:
    """Create a ConnectDef between two entity.port pairs, optionally variant-scoped."""
    return ConnectDef(
        src_entity=src_e,
        src_port=src_p,
        channel="ch",
        dst_entity=dst_e,
        dst_port=dst_p,
        variants=list(variants),
    )


def _exp(entity: str, port: str, *variants: str) -> ExposeDef:
    """Create an ExposeDef, optionally variant-scoped."""
    return ExposeDef(entity=entity, port=port, variants=list(variants))


class TestVariantUnwiredPorts:
    """Per-variant unwired-port checks."""

    # --- Baseline behaviour unchanged ---

    def test_no_variants_baseline_port_wired_no_error(self) -> None:
        a = Component(name="A", provides=[_iref("I")])
        b = Component(name="B", requires=[_iref("I")])
        outer = Component(name="Outer", components=[a, b], connects=[_conn("A", "I", "B", "I")])
        _assert_no_error(ArchFile(components=[outer]))

    def test_no_variants_baseline_port_unwired_error_has_no_variant_label(self) -> None:
        sub = Component(name="Sub", provides=[_iref("I")])
        outer = Component(name="Outer", components=[sub])
        result = validate(ArchFile(components=[outer]))
        msgs = _errors(result)
        assert any("port 'Sub.I'" in m for m in msgs)
        assert not any("[variant" in m for m in msgs)

    # --- Variant-specific entity not checked in wrong variant ---

    def test_cloud_only_entity_not_checked_in_on_premise_variant(self) -> None:
        # A is cloud-only; B is on_premise-only.  Each is wired only in its own variant.
        # No cross-variant wiring needed.
        a = Component(name="A", variants=["cloud"], provides=[_iref("CloudPort")])
        b = Component(name="B", variants=["on_premise"], provides=[_iref("PremPort")])
        outer = Component(
            name="Outer",
            components=[a, b],
            exposes=[_exp("A", "CloudPort", "cloud"), _exp("B", "PremPort", "on_premise")],
        )
        _assert_no_error(ArchFile(components=[outer]))

    def test_variant_entity_port_not_wired_in_own_variant_is_error(self) -> None:
        a = Component(name="A", variants=["cloud"], provides=[_iref("CloudPort")])
        outer = Component(name="Outer", components=[a])  # port not wired
        result = validate(ArchFile(components=[outer]))
        msgs = _errors(result)
        assert any("port 'A.CloudPort'" in m for m in msgs)
        assert any("[variant 'cloud']" in m for m in msgs)

    # --- Baseline port must be wired in every declared variant ---

    def test_baseline_port_wired_only_in_cloud_error_in_on_premise(self) -> None:
        # A and B are baseline (present in all variants).
        # The connect wires them only in cloud.
        # When on_premise is declared (via C), A.I and B.I are unwired in on_premise.
        a = Component(name="A", provides=[_iref("I")])
        b = Component(name="B", requires=[_iref("I")])
        c = Component(name="C", variants=["on_premise"], provides=[_iref("P")])
        outer = Component(
            name="Outer",
            components=[a, b, c],
            connects=[_conn("A", "I", "B", "I", "cloud")],
            exposes=[_exp("C", "P", "on_premise")],
        )
        result = validate(ArchFile(components=[outer]))
        msgs = _errors(result)
        assert any("port 'A.I'" in m and "[variant 'on_premise']" in m for m in msgs)
        assert any("port 'B.I'" in m and "[variant 'on_premise']" in m for m in msgs)
        # Cloud variant: both wired → no cloud error
        assert not any("port 'A.I'" in m and "[variant 'cloud']" in m for m in msgs)

    def test_baseline_port_wired_in_all_declared_variants_no_error(self) -> None:
        a = Component(name="A", provides=[_iref("I")])
        b = Component(name="B", requires=[_iref("I")])
        c = Component(name="C", variants=["on_premise"], provides=[_iref("P")])
        outer = Component(
            name="Outer",
            components=[a, b, c],
            connects=[_conn("A", "I", "B", "I", "cloud"), _conn("A", "I", "B", "I", "on_premise")],
            exposes=[_exp("C", "P", "on_premise")],
        )
        _assert_no_error(ArchFile(components=[outer]))

    def test_variant_port_wired_in_its_variant_no_error(self) -> None:
        a = Component(name="A", provides=[_iref_v("CloudPort", "cloud")])
        b = Component(name="B", requires=[_iref_v("CloudPort", "cloud")])
        outer = Component(
            name="Outer",
            components=[a, b],
            connects=[_conn("A", "CloudPort", "B", "CloudPort", "cloud")],
        )
        _assert_no_error(ArchFile(components=[outer]))

    def test_variant_port_unwired_in_its_variant_is_error(self) -> None:
        a = Component(name="A", provides=[_iref_v("CloudPort", "cloud")])
        outer = Component(name="Outer", components=[a])  # not wired
        result = validate(ArchFile(components=[outer]))
        msgs = _errors(result)
        assert any("port 'A.CloudPort'" in m and "[variant 'cloud']" in m for m in msgs)

    def test_variant_port_not_reported_in_other_variant(self) -> None:
        # A is cloud-only; B is on_premise-only.
        # In the on_premise check A is inactive → no error about A.CloudPort.
        a = Component(name="A", variants=["cloud"], provides=[_iref("CloudPort")])
        b = Component(name="B", variants=["on_premise"], provides=[_iref("PremPort")])
        outer = Component(
            name="Outer",
            components=[a, b],
            exposes=[_exp("A", "CloudPort", "cloud"), _exp("B", "PremPort", "on_premise")],
        )
        _assert_no_error(ArchFile(components=[outer]))

    # --- System scope ---

    def test_system_variant_member_port_not_wired_is_error(self) -> None:
        comp = Component(name="Svc", variants=["cloud"], provides=[_iref("API")])
        sys_ = System(name="S", components=[comp])  # API not wired
        result = validate(ArchFile(systems=[sys_]))
        msgs = _errors(result)
        assert any("port 'Svc.API'" in m and "[variant 'cloud']" in m for m in msgs)

    def test_system_baseline_port_wired_in_all_variants_no_error(self) -> None:
        a = Component(name="A", provides=[_iref("I")])
        b = Component(name="B", requires=[_iref("I")])
        extra = Component(name="Extra", variants=["v1"], provides=[_iref("X")])
        sys_ = System(
            name="S",
            components=[a, b, extra],
            connects=[_conn("A", "I", "B", "I")],  # baseline connect → wired in all variants
            exposes=[_exp("Extra", "X", "v1")],
        )
        _assert_no_error(ArchFile(systems=[sys_]))

    def test_system_user_variant_port_not_wired_is_error(self) -> None:
        user = UserDef(name="Admin", variants=["cloud"], provides=[_iref("AdminAPI")])
        sys_ = System(name="S", users=[user])  # port not wired
        result = validate(ArchFile(systems=[sys_]))
        msgs = _errors(result)
        assert any("port 'Admin.AdminAPI'" in m and "[variant 'cloud']" in m for m in msgs)

    def test_system_user_variant_port_wired_no_error(self) -> None:
        user = UserDef(name="Admin", variants=["cloud"], provides=[_iref("AdminAPI")])
        svc = Component(name="Svc", requires=[_iref("AdminAPI")])
        sys_ = System(
            name="S",
            components=[svc],
            users=[user],
            connects=[_conn("Admin", "AdminAPI", "Svc", "AdminAPI", "cloud")],
        )
        _assert_no_error(ArchFile(systems=[sys_]))

    def test_expose_variant_wires_port_in_that_variant_only(self) -> None:
        a = Component(name="A", variants=["cloud"], provides=[_iref("P")])
        b = Component(name="B", variants=["on_premise"], provides=[_iref("Q")])
        outer = Component(
            name="Outer",
            components=[a, b],
            exposes=[_exp("A", "P", "cloud"), _exp("B", "Q", "on_premise")],
        )
        _assert_no_error(ArchFile(components=[outer]))


# ###############
# Per-Variant Interface Propagation
# ###############


class TestVariantInterfacePropagation:
    """Per-variant interface propagation checks."""

    def test_no_variants_baseline_error_has_no_variant_label(self) -> None:
        comp = Component(name="C", requires=[_iref("Other")])
        sys_ = System(name="S", provides=[_iref("I")], components=[comp])
        result = validate(ArchFile(systems=[sys_]))
        msgs = _errors(result)
        assert any("provides interface 'I'" in m for m in msgs)
        assert not any("[variant" in m for m in msgs)

    def test_variant_member_satisfies_propagation_in_its_variant(self) -> None:
        # System provides I; only the cloud component provides it.
        cloud_comp = Component(name="CloudSvc", variants=["cloud"], provides=[_iref("I")])
        sys_ = System(
            name="S",
            provides=[_iref_v("I", "cloud")],
            components=[cloud_comp],
            exposes=[_exp("CloudSvc", "I", "cloud")],
        )
        _assert_no_error(ArchFile(systems=[sys_]))

    def test_variant_member_not_active_in_other_variant_propagation_error(self) -> None:
        # System provides I in both variants, but only cloud_comp provides I (cloud-only).
        # In on_premise, no member provides I → error.
        cloud_comp = Component(name="CloudSvc", variants=["cloud"], provides=[_iref("I")])
        prem_comp = Component(name="PremSvc", variants=["on_premise"], provides=[_iref("Other")])
        sys_ = System(
            name="S",
            provides=[_iref("I")],  # baseline provides — required in all variants
            components=[cloud_comp, prem_comp],
        )
        result = validate(ArchFile(systems=[sys_]))
        msgs = _errors(result)
        # on_premise: no member provides I
        assert any("provides interface 'I'" in m and "[variant 'on_premise']" in m for m in msgs)
        # cloud: cloud_comp provides I → no cloud propagation error for I
        assert not any("provides interface 'I'" in m and "[variant 'cloud']" in m for m in msgs)

    def test_component_propagation_per_variant(self) -> None:
        sub_cloud = Component(name="SubCloud", variants=["cloud"], provides=[_iref("I")])
        outer = Component(
            name="Outer",
            provides=[_iref_v("I", "cloud")],
            components=[sub_cloud],
            exposes=[_exp("SubCloud", "I", "cloud")],
        )
        _assert_no_error(ArchFile(components=[outer]))

    def test_component_propagation_missing_in_variant_is_error(self) -> None:
        # Outer provides I (baseline). SubCloud provides I (cloud-only).
        # In on_premise no active member provides I → error [variant 'on_premise'].
        # In cloud SubCloud provides I → no error.
        sub_cloud = Component(name="SubCloud", variants=["cloud"], provides=[_iref("I")])
        sub_prem = Component(name="SubPrem", variants=["on_premise"], provides=[_iref("Other")])
        outer = Component(
            name="Outer",
            provides=[_iref("I")],  # baseline: must be grounded in every variant
            components=[sub_cloud, sub_prem],
        )
        result = validate(ArchFile(components=[outer]))
        msgs = _errors(result)
        assert any("provides interface 'I'" in m and "[variant 'on_premise']" in m for m in msgs)
        assert not any("provides interface 'I'" in m and "[variant 'cloud']" in m for m in msgs)


# ###############
# Fully Connected
# ###############


class TestFullyConnected:
    """Every non-stub entity must have at least one port active in each variant."""

    # --- Baseline (no variants) ---

    def test_component_with_provides_is_connected(self) -> None:
        arch = ArchFile(components=[Component(name="C", provides=[_iref("I")])])
        _assert_no_error(arch)

    def test_component_with_requires_is_connected(self) -> None:
        arch = ArchFile(components=[Component(name="C", requires=[_iref("I")])])
        _assert_no_error(arch)

    def test_component_with_no_ports_is_error(self) -> None:
        arch = ArchFile(components=[Component(name="C")])
        _assert_error(arch, "Component 'C'")
        _assert_error(arch, "has no ports (requires or provides)")

    def test_error_has_no_variant_label_when_no_variants(self) -> None:
        arch = ArchFile(components=[Component(name="C")])
        result = validate(arch)
        msgs = _errors(result)
        assert any("has no ports" in m for m in msgs)
        assert not any("[variant" in m for m in msgs)

    def test_leaf_system_with_no_ports_is_error(self) -> None:
        arch = ArchFile(systems=[System(name="S")])
        _assert_error(arch, "System 'S'")
        _assert_error(arch, "has no ports (requires or provides)")

    def test_top_level_user_with_no_ports_is_error(self) -> None:
        arch = ArchFile(users=[UserDef(name="Admin")])
        _assert_error(arch, "User 'Admin'")
        _assert_error(arch, "has no ports (requires or provides)")

    def test_top_level_user_with_requires_is_connected(self) -> None:
        arch = ArchFile(users=[UserDef(name="Admin", requires=[_iref("AdminAPI")])])
        _assert_no_error(arch)

    # --- Stub entities are exempt ---

    def test_stub_component_with_no_ports_no_error(self) -> None:
        arch = ArchFile(components=[Component(name="Stub", is_stub=True)])
        _assert_no_error(arch)

    def test_stub_system_with_no_ports_no_error(self) -> None:
        arch = ArchFile(systems=[System(name="Stub", is_stub=True)])
        _assert_no_error(arch)

    # --- Sub-entities within containers ---

    def test_sub_component_with_no_ports_is_error(self) -> None:
        sub = Component(name="Sub")
        outer = Component(name="Outer", provides=[_iref("I")], components=[sub])
        arch = ArchFile(components=[outer])
        _assert_error(arch, "Component 'Sub'")
        _assert_error(arch, "has no ports (requires or provides)")

    def test_sub_component_with_ports_no_error(self) -> None:
        sub = Component(name="Sub", provides=[_iref("I")])
        outer = Component(
            name="Outer",
            provides=[_iref("I")],
            components=[sub],
            exposes=[ExposeDef(entity="Sub", port="I")],
        )
        _assert_no_error(ArchFile(components=[outer]))

    def test_user_inside_system_with_no_ports_is_error(self) -> None:
        user = UserDef(name="Client")
        sys_ = System(name="S", provides=[_iref("I")], users=[user])
        _assert_error(ArchFile(systems=[sys_]), "User 'Client'")

    def test_leaf_subsystem_with_no_ports_is_error(self) -> None:
        sub = System(name="Sub")
        outer = System(name="Outer", provides=[_iref("I")], systems=[sub])
        _assert_error(ArchFile(systems=[outer]), "System 'Sub'")

    def test_container_system_with_no_own_ports_but_has_children_no_error(self) -> None:
        comp = Component(name="C", provides=[_iref("I")])
        sys_ = System(name="S", components=[comp], exposes=[ExposeDef(entity="C", port="I")])
        _assert_no_error(ArchFile(systems=[sys_]))

    def test_container_component_with_no_own_ports_but_has_children_no_error(self) -> None:
        sub = Component(name="Sub", provides=[_iref("I")])
        outer = Component(name="Outer", components=[sub], exposes=[ExposeDef(entity="Sub", port="I")])
        _assert_no_error(ArchFile(components=[outer]))

    def test_qualified_name_used_in_error(self) -> None:
        comp = Component(name="C", qualified_name="ns::C")
        arch = ArchFile(components=[comp])
        _assert_error(arch, "'ns::C'")

    # --- Per-variant: entity only active in one variant ---

    def test_variant_entity_with_ports_in_its_variant_no_error(self) -> None:
        # cloud-only component has a cloud-only port → fine in cloud, not checked in on_premise.
        a = Component(name="A", variants=["cloud"], provides=[_iref_v("P", "cloud")])
        outer = Component(
            name="Outer",
            provides=[_iref_v("P", "cloud")],
            components=[a],
            exposes=[_exp("A", "P", "cloud")],
        )
        _assert_no_error(ArchFile(components=[outer]))

    def test_baseline_component_with_no_ports_error_has_no_variant_label(self) -> None:
        # Even when variants exist in the scope, a baseline portless component
        # produces errors for every checked variant — no variant label in baseline mode
        # only applies when the whole scope has no variants.  When variants ARE present,
        # the error message will carry a variant label.
        a = Component(name="A")  # no ports, baseline
        b = Component(name="B", variants=["cloud"], provides=[_iref("X")])
        outer = Component(name="Outer", provides=[_iref("X")], components=[a, b])
        result = validate(ArchFile(components=[outer]))
        msgs = _errors(result)
        # A is portless in every variant → error for cloud (the only named variant here)
        assert any("Component 'A'" in m and "[variant 'cloud']" in m for m in msgs)

    def test_cloud_entity_has_no_ports_in_on_premise_check_not_run(self) -> None:
        # cloud-only component with cloud-scoped port is only checked in cloud variant.
        a = Component(name="A", variants=["cloud"], provides=[_iref("P")])
        b = Component(name="B", variants=["on_premise"], provides=[_iref("Q")])
        outer = Component(
            name="Outer",
            provides=[_iref_v("P", "cloud"), _iref_v("Q", "on_premise")],
            components=[a, b],
            exposes=[_exp("A", "P", "cloud"), _exp("B", "Q", "on_premise")],
        )
        _assert_no_error(ArchFile(components=[outer]))

    def test_entity_port_only_in_other_variant_reports_portless_error(self) -> None:
        # Component A has a cloud-only port but is baseline (present in all variants).
        # In on_premise, A has no active ports → error.
        a = Component(name="A", provides=[_iref_v("P", "cloud")])
        b = Component(name="B", variants=["on_premise"], provides=[_iref("Q")])
        outer = Component(
            name="Outer",
            provides=[_iref_v("P", "cloud"), _iref("Q")],
            components=[a, b],
            exposes=[_exp("A", "P", "cloud"), _exp("B", "Q", "on_premise")],
        )
        result = validate(ArchFile(components=[outer]))
        msgs = _errors(result)
        assert any("Component 'A'" in m and "[variant 'on_premise']" in m for m in msgs)
        assert not any("Component 'A'" in m and "[variant 'cloud']" in m for m in msgs)

    def test_system_variant_member_portless_is_error(self) -> None:
        inner = System(name="Inner", variants=["cloud"])  # no ports
        outer = System(name="Outer", provides=[_iref_v("I", "cloud")], systems=[inner])
        result = validate(ArchFile(systems=[outer]))
        msgs = _errors(result)
        assert any("System 'Inner'" in m and "[variant 'cloud']" in m for m in msgs)

    def test_user_in_system_variant_portless_is_error(self) -> None:
        user = UserDef(name="Admin", variants=["cloud"])  # no ports
        comp = Component(name="Svc", provides=[_iref("I")])
        sys_ = System(
            name="S",
            components=[comp],
            users=[user],
            exposes=[ExposeDef(entity="Svc", port="I")],
        )
        result = validate(ArchFile(systems=[sys_]))
        msgs = _errors(result)
        assert any("User 'Admin'" in m and "[variant 'cloud']" in m for m in msgs)
