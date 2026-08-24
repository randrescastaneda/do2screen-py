"""Conformance test: does the real ``stata_registry`` satisfy the contract?

This test runs only when the upstream ``stata-command-registry`` repository
(distribution name ``stata-registry``, import name ``stata_registry``) is
installed (``pip install ".[registry]"``). It verifies
the actual API surface this adapter relies on. It is skipped with a clear
reason when the registry is absent.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util

import pytest

from do2screen.registry import _REQUIRED_METHODS, RegistryAdapter

REGISTRY_SPEC = importlib.util.find_spec("stata_registry")

requires_registry = pytest.mark.skipif(
    REGISTRY_SPEC is None,
    reason="stata_registry not installed; install the latest upstream main with '.[registry]'",
)


@requires_registry
def test_registry_installed_and_available():
    adapter = RegistryAdapter()
    assert adapter.available, adapter.describe_issue()
    version = importlib.metadata.version("stata-registry")
    assert tuple(int(part) for part in version.split(".")[:2]) >= (0, 4)


@requires_registry
def test_registry_exposes_required_methods():
    import stata_registry  # type: ignore[import-not-found]

    for name in _REQUIRED_METHODS:
        assert callable(getattr(stata_registry, name, None)), name
    assert callable(getattr(stata_registry, "is_include", None))


@requires_registry
def test_contract_behaviour():
    adapter = RegistryAdapter()
    # A known command resolves to itself.
    assert adapter.canonical_command("generate") == "generate"
    # variable_effect returns one of the documented effect literals.
    effect = adapter.variable_effect("generate")
    assert effect in {
        "creates",
        "modifies",
        "renames",
        "removes",
        "labels",
        "restructures",
        "none",
    }
    assert adapter.is_include("do") is True
    assert adapter.is_include("run") is True
    assert adapter.is_include("include") is True
    assert adapter.is_include("generate") is False
    assert adapter.is_include("not_a_command") is False
    assert adapter.source_driver_available is True


@requires_registry
def test_upstream_entries_have_explicit_boolean_source_driver_metadata():
    import stata_registry  # type: ignore[import-not-found]

    entries = []
    for document in stata_registry._load_yaml_files():
        for category in document.get("categories", {}).values():
            entries.extend(category.get("commands") or [])
    assert entries
    assert all(type(entry.get("include_driver")) is bool for entry in entries)
    assert {
        entry["name"] for entry in entries if entry["include_driver"]
    } >= {"do", "include", "run"}
