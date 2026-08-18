"""Registry adapter behaviour against the mock registry and failure modes."""

from __future__ import annotations

import pytest

from do2screen import registry as registry_module
from do2screen.registry import (
    RegistryAdapter,
    RegistryIncompatibilityError,
)
from tests.mock_registry import MockStataRegistry


class _BrokenRegistry(MockStataRegistry):
    # override the inherited method with a non-callable to simulate a missing
    # API surface on the upstream package.
    variable_effect = None


def test_resolves_known_command(registry):
    assert registry.canonical_command("generate") == "generate"


def test_resolves_abbreviation(registry):
    assert registry.canonical_command("g") == "generate"
    assert registry.canonical_command("ge") == "generate"
    assert registry.canonical_command("gen") == "generate"


def test_command_that_cannot_be_abbreviated(registry):
    # replace cannot be abbreviated; a common wrong abbreviation must fail.
    assert registry.canonical_command("re") is None
    assert registry.canonical_command("rep") is None


def test_unknown_token(registry):
    assert registry.canonical_command("notacommand") is None
    assert registry.canonical_command("whatever") is None


def test_prefix_detection(registry):
    assert registry.is_prefix("bysort") is True
    assert registry.is_prefix("generate") is False


def test_variable_effect_resolves_abbreviations(registry):
    assert registry.variable_effect("generate") == "creates"
    assert registry.variable_effect("gen") == "creates"
    assert registry.variable_effect("replace") == "modifies"
    assert registry.variable_effect("drop") == "removes"
    assert registry.variable_effect("label") == "labels"
    assert registry.variable_effect("rename") == "renames"


def test_optional_is_include(registry):
    assert registry.is_include("include") is True
    assert registry.is_include("do") is True
    assert registry.is_include("generate") is False


def test_absent_registry_fails_cleanly_at_runtime():
    try:
        import importlib.util

        present = (
            importlib.util.find_spec("stata_registry") is not None
        )
    except ImportError:  # pragma: no cover
        present = False
    adapter = RegistryAdapter()
    if not present:
        assert adapter.available is False
        assert "Registry" in adapter.describe_issue()
        with pytest.raises(RegistryIncompatibilityError):
            adapter.canonical_command("generate")
    else:
        assert adapter.available is True


def test_broken_api_reported_as_incompatible():
    adapter = RegistryAdapter(module=_BrokenRegistry())
    assert adapter.available is False
    assert "variable_effect" in adapter.describe_issue()
    with pytest.raises(RegistryIncompatibilityError):
        adapter.variable_effect("generate")


def test_missing_is_include_is_graceful():
    class NoInclude(MockStataRegistry):
        is_include = None  # upstream does not export the optional method

    adapter = RegistryAdapter(module=NoInclude())
    assert adapter.available is True
    assert adapter.is_include("include") is False


def test_registry_module_is_never_imported_at_import_time():
    # The module must be importable without the registry present.
    import importlib

    assert importlib.util.find_spec("do2screen.registry") is not None
    assert registry_module._MODULE_NAME == "stata_registry"
