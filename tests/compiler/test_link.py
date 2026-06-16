# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the whole-program instantiation (linking) phase."""

from archml.compiler.link import link
from archml.compiler.parser import parse
from archml.compiler.semantic_analysis import analyze
from archml.model.entities import ArchFile, Component, System, UserDef
from archml.validation.checks import validate

# ###############
# Test Helpers
# ###############


def _compiled(**files: str) -> dict[str, ArchFile]:
    """Parse and assign qualified names for each ``key=source`` file."""
    out: dict[str, ArchFile] = {}
    for key, source in files.items():
        arch_file = parse(source)
        # No resolved_imports -> import validation skipped, qualified names assigned.
        analyze(arch_file, file_key=key)
        out[key] = arch_file
    return out


def _child(entity: Component | System, name: str) -> Component | System | UserDef:
    """Return the direct child of *entity* with the given name."""
    members: list[Component | System | UserDef] = list(entity.components)
    if isinstance(entity, System):
        members += list(entity.systems) + list(entity.users)
    for member in members:
        if member.name == name:
            return member
    raise AssertionError(f"child '{name}' not found in '{entity.name}'")


def _top(compiled: dict[str, ArchFile], key: str, name: str) -> Component | System:
    """Return the top-level component or system named *name* in file *key*."""
    arch_file = compiled[key]
    for entity in (*arch_file.systems, *arch_file.components):
        if entity.name == name:
            return entity
    raise AssertionError(f"top-level entity '{name}' not found in '{key}'")


# ###############
# Instantiation
# ###############


class TestInstantiation:
    def test_use_instantiates_with_real_ports(self) -> None:
        compiled = _compiled(
            app="""
interface API { endpoint: String }
template component Worker { requires API  provides API }
system Orders {
    use component Worker
}
"""
        )
        result = link(compiled)
        assert result.errors == []
        orders = compiled["app"].systems[0]
        worker = _child(orders, "Worker")
        assert worker.is_stub is False
        assert [r.name for r in worker.requires] == ["API"]
        assert [p.name for p in worker.provides] == ["API"]
        assert worker.qualified_name == "app::Orders::Worker"

    def test_instance_internal_structure_copied(self) -> None:
        compiled = _compiled(
            app="""
interface PaymentRequest { id: String }
template system Pipeline {
    component Gateway { provides PaymentRequest }
    component Processor { requires PaymentRequest }
    channel pay: PaymentRequest
    connect Gateway.PaymentRequest -> $pay -> Processor.PaymentRequest
}
system Orders {
    use system Pipeline
}
"""
        )
        result = link(compiled)
        assert result.errors == []
        orders = _top(compiled, "app", "Orders")
        pipeline = _child(orders, "Pipeline")
        assert isinstance(pipeline, System)
        assert pipeline.is_stub is False
        assert {c.name for c in pipeline.components} == {"Gateway", "Processor"}
        assert pipeline.qualified_name == "app::Orders::Pipeline"
        # Internal channel copied and re-qualified under the instance path.
        assert [ch.name for ch in pipeline.channels] == ["pay"]
        assert pipeline.channels[0].qualified_name == "app::Orders::Pipeline::pay"
        # Internal connect copied.
        assert len(pipeline.connects) == 1

    def test_two_hosts_get_independent_instances(self) -> None:
        compiled = _compiled(
            app="""
interface Msg { id: String }
template system Pipe {
    component A { provides Msg }
    component B { requires Msg }
    channel m: Msg
    connect A.Msg -> $m -> B.Msg
}
system Orders { use system Pipe }
system Billing { use system Pipe }
"""
        )
        result = link(compiled)
        assert result.errors == []
        orders_pipe = _child(_top(compiled, "app", "Orders"), "Pipe")
        billing_pipe = _child(_top(compiled, "app", "Billing"), "Pipe")
        assert isinstance(orders_pipe, System)
        assert isinstance(billing_pipe, System)
        # Independent copies, distinct channel qualified names, no collision.
        assert orders_pipe is not billing_pipe
        assert orders_pipe.channels[0].qualified_name == "app::Orders::Pipe::m"
        assert billing_pipe.channels[0].qualified_name == "app::Billing::Pipe::m"

    def test_non_template_use_is_also_linked(self) -> None:
        """Uniform rule: a plain (non-template) `use` is expanded too."""
        compiled = _compiled(
            app="""
interface API { endpoint: String }
component Worker { requires API  provides API }
system Orders {
    use component Worker
}
"""
        )
        result = link(compiled)
        assert result.errors == []
        worker = _child(compiled["app"].systems[0], "Worker")
        assert worker.is_stub is False
        assert [p.name for p in worker.provides] == ["API"]

    def test_use_user_is_linked(self) -> None:
        compiled = _compiled(
            app="""
interface Cmd { id: String }
template user Account { provides Cmd }
system Orders {
    use user Account
}
"""
        )
        result = link(compiled)
        assert result.errors == []
        account = _child(compiled["app"].systems[0], "Account")
        assert isinstance(account, UserDef)
        assert account.is_stub is False
        assert [p.name for p in account.provides] == ["Cmd"]

    def test_cross_file_template_resolution(self) -> None:
        compiled = _compiled(
            templates="""
interface API { endpoint: String }
template component Worker { provides API }
""",
            app="""
system Orders {
    use component Worker
}
""",
        )
        result = link(compiled)
        assert result.errors == []
        worker = _child(compiled["app"].systems[0], "Worker")
        assert worker.is_stub is False
        assert [p.name for p in worker.provides] == ["API"]


# ###############
# Cycles and nesting
# ###############


class TestCyclesAndNesting:
    def test_instantiation_cycle_is_error(self) -> None:
        compiled = _compiled(
            app="""
component A { use component B }
component B { use component A }
"""
        )
        result = link(compiled)
        assert any("cycle" in e for e in result.errors)

    def test_template_inside_template_not_expanded_and_warns(self) -> None:
        compiled = _compiled(
            app="""
interface X { id: String }
template component Inner { provides X }
template system Outer {
    use component Inner
}
system Host {
    use system Outer
}
"""
        )
        result = link(compiled)
        assert result.errors == []
        assert any("inside template 'Outer' is discouraged" in w for w in result.warnings)
        # The Outer instance exists, but its inner template use is left as a stub.
        outer_instance = _child(_top(compiled, "app", "Host"), "Outer")
        assert isinstance(outer_instance, System)
        assert outer_instance.is_stub is False
        inner = _child(outer_instance, "Inner")
        assert inner.is_stub is True


# ###############
# Template warnings
# ###############


class TestTemplateWarnings:
    def test_unused_template_warns(self) -> None:
        compiled = _compiled(
            app="""
interface X { id: String }
template component Unused { provides X }
system S { component A { provides X } }
"""
        )
        result = link(compiled)
        assert any("template 'Unused' is never instantiated" in w for w in result.warnings)

    def test_instantiated_template_has_no_unused_warning(self) -> None:
        compiled = _compiled(
            app="""
interface X { id: String }
template component Worker { provides X }
system S { use component Worker }
"""
        )
        result = link(compiled)
        assert not any("never instantiated" in w for w in result.warnings)

    def test_cross_file_instantiation_suppresses_unused_warning(self) -> None:
        compiled = _compiled(
            templates="""
interface X { id: String }
template component Worker { provides X }
""",
            app="""
system S { use component Worker }
""",
        )
        result = link(compiled)
        assert not any("never instantiated" in w for w in result.warnings)


# ###############
# Validation on the linked model
# ###############


class TestLinkedValidation:
    def test_unconnected_instance_port_is_unwired_error(self) -> None:
        """The core guarantee: an instance's open ports must be wired by the host."""
        compiled = _compiled(
            app="""
interface API { endpoint: String }
template component Worker { provides API }
system Orders {
    use component Worker
    component Other { requires API }
}
"""
        )
        result = link(compiled)
        assert result.errors == []
        messages = [e.message for e in validate(compiled["app"]).errors]
        assert any("Worker.API" in m and "neither wired" in m for m in messages)
