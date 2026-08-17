"""Narrow adapter around the upstream ``stata_registry`` package.

The upstream package supplies Stata command vocabulary (what a token means);
this package supplies grammar (the shape of the text). The adapter is the only
place in this codebase that talks to the registry, and it is written against a
documented contract the registry must satisfy:

- ``canonical_command(token: str) -> str | None`` -- resolve abbreviations.
- ``is_prefix(token: str) -> bool`` -- whether the token is a bysort-style
  command prefix that must be stripped before classification.
- ``variable_effect(command: str) -> str`` -- one of ``creates``, ``modifies``,
  ``renames``, ``removes``, ``labels``, ``restructures``, ``none``.

The registry is deliberately an optional runtime dependency: constructing the
adapter never fails, but calling registry-backed methods raises
:class:`RegistryIncompatibilityError` when the package is absent or the API
does not match the contract. This package must install and run all of its
registry-independent tests without ``stata_registry`` present.
"""

from __future__ import annotations

import importlib
import sys
from typing import Any

#: Methods the registry must expose for this adapter to function.
_REQUIRED_METHODS = ("canonical_command", "is_prefix", "variable_effect")

_MODULE_NAME = "stata_registry"


class RegistryIncompatibilityError(RuntimeError):
    """Raised when the registry is absent or its API does not match the
    documented contract. Carries version information when available."""


def _load_module() -> tuple[Any, str | None]:
    """Import the registry module, returning ``(module, error)``.

    The module is never imported at module import time; it is loaded lazily so
    that the package imports and tests run without the registry present.
    """
    if _MODULE_NAME in sys.modules:
        return sys.modules[_MODULE_NAME], None
    try:
        module = importlib.import_module(_MODULE_NAME)
    except Exception as exc:  # noqa: BLE001 - any import failure degrades cleanly
        return None, f"{_MODULE_NAME} package unavailable: {exc}"
    return module, None


class RegistryAdapter:
    """Contract-checked view over the ``stata_registry`` package.

    Args:
        module: Optional injected module (used by tests and the conformance
            test). When omitted, the adapter imports ``stata_registry`` lazily.
    """

    def __init__(self, module: Any | None = None) -> None:
        if module is not None:
            self._module = module
            self._import_error: str | None = None
            self._module_name = getattr(module, "__name__", "<injected module>")
        else:
            self._module_name = _MODULE_NAME
            self._module, self._import_error = _load_module()
        self._missing = self._missing_methods()

    # -- introspection -----------------------------------------------------

    def _missing_methods(self) -> list[str]:
        if self._module is None:
            return []
        return [
            name
            for name in _REQUIRED_METHODS
            if not callable(getattr(self._module, name, None))
        ]

    @property
    def available(self) -> bool:
        """True when the registry is importable and satisfies the contract."""
        return self._module is not None and not self._missing

    def version(self) -> str:
        """Best-effort version string for error messages."""
        if self._module is None:
            return "unknown"
        return str(getattr(self._module, "__version__", "unknown"))

    def describe_issue(self) -> str:
        """Human-readable reason the adapter cannot serve registry lookups."""
        action = (
            f"install `stata-registry` compatible with the documented contract "
            f"({', '.join(_REQUIRED_METHODS)})"
        )
        if self._module is None:
            return (
                f"Registry unavailable: {self._import_error}. "
                f"Install `stata-command-registry` (import name "
                f"`{self._module_name}`). To act on it, {action}."
            )
        missing = ", ".join(self._missing)
        return (
            f"Registry v{self.version()} incompatible: missing API "
            f"method(s) `{missing}`. The adapter requires "
            f"{', '.join(_REQUIRED_METHODS)}. To act on it, {action}."
        )

    # -- registry operations ----------------------------------------------

    def _require(self) -> Any:
        if not self.available:
            raise RegistryIncompatibilityError(self.describe_issue())
        return self._module

    def canonical_command(self, token: str) -> str | None:
        """Resolve an (possibly abbreviated) token to its canonical command
        name, or ``None`` when the token is not a known command."""
        return self._require().canonical_command(token)

    def is_prefix(self, token: str) -> bool:
        """Return True when the token is a command prefix (for example
        ``bysort``) that must be stripped before classifying a statement."""
        return bool(self._require().is_prefix(token))

    def variable_effect(self, command: str) -> str:
        """Return the dataset effect of a canonical command: ``creates``,
        ``modifies``, ``renames``, ``removes``, ``labels``, ``restructures``,
        or ``none``."""
        return str(self._require().variable_effect(command))

    def is_include(self, command: str) -> bool:
        """Return True when a canonical command drives an include/nested do.

        This is an *optional* extension of the contract. When the registry does
        not export it (or the call fails), the adapter returns ``False`` and
        include statements fall through to normal classification (typically
        ``unsupported_effect``).
        """
        if self._module is None:
            return False
        check = getattr(self._module, "is_include", None)
        if not callable(check):
            return False
        try:
            return bool(check(command))
        except Exception:  # noqa: BLE001 - degrade cleanly on missing behaviour
            return False
