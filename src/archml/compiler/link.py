# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Whole-program instantiation (linking) phase.

The per-file compiler leaves every ``use component/system/user`` as an empty
*stub* (``is_stub=True``).  This phase runs once over the fully compiled
workspace and resolves each stub into a concrete **instance**: a deep copy of
the referenced definition, re-qualified under the host path, with its real
ports and internal structure.  After linking, validation and the view layer
operate on a single fully-resolved model.

Templates (``is_template=True``) are ordinary definitions for the purpose of
instantiation; the only special rules are:

* a template used *inside another template* is not expanded (nested blueprints
  do not make sense) and yields a warning, and
* an unused template yields a warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from archml.model.entities import ArchFile, Component, System, UserDef

# ###############
# Public Interface
# ###############

_Entity = Component | System | UserDef


@dataclass
class LinkResult:
    """The linked model plus any diagnostics produced while linking."""

    model: dict[str, ArchFile]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def link(compiled: dict[str, ArchFile]) -> LinkResult:
    """Resolve every ``use`` stub in *compiled* into a concrete instance.

    Mutates the entities in *compiled* in place and returns the same mapping
    wrapped in a :class:`LinkResult` together with collected errors (e.g.
    instantiation cycles) and warnings (unused or nested templates).

    Args:
        compiled: Mapping from canonical file key to compiled
            :class:`~archml.model.entities.ArchFile`, as returned by
            :func:`archml.compiler.build.compile_files`.

    Returns:
        A :class:`LinkResult`.  When ``errors`` is non-empty the model should
        be treated as invalid.
    """
    registry = _build_registry(compiled)
    errors: list[str] = []

    # Diagnostics are computed from the original (pre-expansion) definitions.
    warnings = _template_warnings(compiled, registry)

    for arch_file in compiled.values():
        for comp in arch_file.components:
            _link_container(comp, registry, errors, chain=[comp.name])
        for system in arch_file.systems:
            _link_container(system, registry, errors, chain=[system.name])

    return LinkResult(model=compiled, errors=errors, warnings=warnings)


# ################
# Implementation
# ################


def _build_registry(compiled: dict[str, ArchFile]) -> dict[str, _Entity]:
    """Map each top-level entity name to its definition across all files.

    On a name collision the first definition encountered wins, mirroring the
    global-by-name resolution used by :mod:`archml.views.resolver`.
    """
    registry: dict[str, _Entity] = {}
    for arch_file in compiled.values():
        for entity in (*arch_file.components, *arch_file.systems, *arch_file.users):
            registry.setdefault(entity.name, entity)
    return registry


def _link_container(
    entity: Component | System,
    registry: dict[str, _Entity],
    errors: list[str],
    chain: list[str],
    *,
    within_template: bool | None = None,
) -> None:
    """Expand the stub children of *entity*, recursing into the results."""
    inside_template = entity.is_template if within_template is None else within_template

    entity.components = [
        _link_child(child, entity, registry, errors, chain, inside_template) for child in entity.components
    ]
    if isinstance(entity, System):
        entity.systems = [
            _link_child(child, entity, registry, errors, chain, inside_template) for child in entity.systems
        ]
        entity.users = [_link_child(child, entity, registry, errors, chain, inside_template) for child in entity.users]


def _link_child(
    child: _Entity,
    host: Component | System,
    registry: dict[str, _Entity],
    errors: list[str],
    chain: list[str],
    within_template: bool,
):  # type: ignore[no-untyped-def]
    """Return the linked replacement for *child* (an instance, or *child* itself)."""
    if not child.is_stub:
        # Inline definition: recurse so its own ``use`` stubs are expanded too.
        if isinstance(child, (Component, System)):
            _link_container(child, registry, errors, chain, within_template=within_template)
        return child

    definition = registry.get(child.name)
    if definition is None:
        # Unresolved reference; semantic analysis already reported the import error.
        return child

    # A template used inside another template is not a meaningful nested blueprint.
    if within_template and definition.is_template:
        return child

    if definition.name in chain:
        cycle = " -> ".join([*chain, definition.name])
        errors.append(f"instantiation cycle detected: {cycle}")
        return child

    instance = definition.model_copy(deep=True)
    instance.is_stub = False
    instance.is_template = False
    instance.variants = list(child.variants)
    _requalify(instance, prefix=host.qualified_name)

    if isinstance(instance, (Component, System)):
        _link_container(
            instance,
            registry,
            errors,
            [*chain, definition.name],
            within_template=within_template or definition.is_template,
        )
    return instance


def _requalify(entity: _Entity, prefix: str) -> None:
    """Recursively re-assign qualified names for a freshly instantiated subtree."""
    entity.qualified_name = f"{prefix}::{entity.name}" if prefix else entity.name
    if isinstance(entity, (Component, System)):
        for iface in entity.interfaces:
            iface.qualified_name = f"{entity.qualified_name}::{iface.name}"
        for channel in entity.channels:
            channel.qualified_name = f"{entity.qualified_name}::{channel.name}"
        for comp in entity.components:
            _requalify(comp, entity.qualified_name)
        if isinstance(entity, System):
            for sub in entity.systems:
                _requalify(sub, entity.qualified_name)
            for user in entity.users:
                _requalify(user, entity.qualified_name)


def _template_warnings(compiled: dict[str, ArchFile], registry: dict[str, _Entity]) -> list[str]:
    """Collect unused-template and nested-template warnings."""
    warnings: list[str] = []

    template_names = {name for name, entity in registry.items() if entity.is_template}

    # Every ``use`` stub target across the whole workspace.
    used_names: set[str] = set()
    for arch_file in compiled.values():
        for entity in (*arch_file.components, *arch_file.systems, *arch_file.users):
            _collect_stub_targets(entity, used_names)

    for name in sorted(template_names - used_names):
        warnings.append(f"template '{name}' is never instantiated")

    # A ``use <template>`` appearing inside a template definition is discouraged.
    for arch_file in compiled.values():
        for entity in (*arch_file.components, *arch_file.systems, *arch_file.users):
            if entity.is_template:
                _collect_nested_template_uses(entity, entity.name, registry, warnings)

    return warnings


def _collect_stub_targets(entity: _Entity, out: set[str]) -> None:
    """Record the names of every ``use`` stub reachable from *entity*."""
    if entity.is_stub:
        out.add(entity.name)
    if isinstance(entity, (Component, System)):
        for comp in entity.components:
            _collect_stub_targets(comp, out)
        if isinstance(entity, System):
            for sub in entity.systems:
                _collect_stub_targets(sub, out)
            for user in entity.users:
                _collect_stub_targets(user, out)


def _collect_nested_template_uses(
    entity: _Entity,
    outer_template: str,
    registry: dict[str, _Entity],
    warnings: list[str],
) -> None:
    """Warn for each ``use`` of a template found within *outer_template*'s body."""
    if isinstance(entity, (Component, System)):
        children: list[_Entity] = list(entity.components)
        if isinstance(entity, System):
            children += list(entity.systems) + list(entity.users)
        for child in children:
            if child.is_stub:
                target = registry.get(child.name)
                if target is not None and target.is_template:
                    warnings.append(
                        f"instantiating template '{child.name}' inside template '{outer_template}' is discouraged"
                    )
            else:
                _collect_nested_template_uses(child, outer_template, registry, warnings)
