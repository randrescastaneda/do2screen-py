"""Conformance test: does the real ``stata_registry`` satisfy the contract?

This test runs only when the upstream ``stata-command-registry`` repository
(distribution name ``stata-registry``, import name ``stata_registry``) is
installed (``pip install ".[registry]"``). It verifies
the actual API surface this adapter relies on. It is skipped with a clear
reason when the registry is absent.
"""

from __future__ import annotations

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


@requires_registry
def test_registry_exposes_required_methods():
    import stata_registry  # type: ignore[import-not-found]

    for name in _REQUIRED_METHODS:
        assert callable(getattr(stata_registry, name, None)), name


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
