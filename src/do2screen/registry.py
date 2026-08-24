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
- ``is_include(token: str) -> bool`` -- whether a token resolves to an explicit
  source-driver command in the upstream registry.

The registry is deliberately an optional runtime dependency: constructing the
adapter never fails, but calling registry-backed methods raises
``RegistryIncompatibilityError`` when the package is absent or the API
does not match the contract. The ``[registry]`` extra obtains the latest
upstream repository revision at installation or upgrade time; runtime tracing
does not access the network. This package must install and run all of its
registry-independent tests without ``stata_registry`` present.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import re
import sys
from typing import Any

#: Methods the registry must expose for this adapter to function.
_REQUIRED_METHODS = ("canonical_command", "is_prefix", "variable_effect")
_SOURCE_DRIVER_MIN_VERSION = (0, 4, 0)

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
        self._injected = module is not None
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
        module_version = getattr(self._module, "__version__", None)
        if module_version is not None:
            return str(module_version)
        if self._injected:
            return "unknown"
        try:
            return importlib.metadata.version("stata-registry")
        except importlib.metadata.PackageNotFoundError:
            return "unknown"

    def describe_issue(self) -> str:
        """Human-readable reason the adapter cannot serve registry lookups."""
        action = (
            f"install `stata-registry` compatible with the documented contract "
            f"({', '.join(_REQUIRED_METHODS)})"
        )
        if self._module is None:
            return (
                f"Registry unavailable: {self._import_error}. "
                f"Install the upstream `stata-command-registry` repository "
                f"(distribution `stata-registry`, import name "
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
        try:
            result = self._require().canonical_command(token)
        except RegistryIncompatibilityError:
            raise
        except KeyError:
            # stata-registry 0.4.0 raises for unknown tokens while this adapter
            # contract deliberately exposes a nullable lookup to the parser.
            return None
        except Exception as exc:  # noqa: BLE001 - normalize upstream API errors
            raise RegistryIncompatibilityError(
                f"Registry command lookup failed for {token!r}: {exc}"
            ) from exc
        return result

    def is_prefix(self, token: str) -> bool:
        """Return True when the token is a command prefix (for example
        ``bysort``) that must be stripped before classifying a statement."""
        try:
            return bool(self._require().is_prefix(token))
        except RegistryIncompatibilityError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize upstream API errors
            raise RegistryIncompatibilityError(
                f"Registry prefix lookup failed for {token!r}: {exc}"
            ) from exc

    def variable_effect(self, command: str) -> str:
        """Return the dataset effect of a canonical command: ``creates``,
        ``modifies``, ``renames``, ``removes``, ``labels``, ``restructures``,
        or ``none``."""
        try:
            return str(self._require().variable_effect(command))
        except RegistryIncompatibilityError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize upstream API errors
            raise RegistryIncompatibilityError(
                f"Registry variable-effect lookup failed for {command!r}: {exc}"
            ) from exc

    def is_include(self, command: str) -> bool:
        """Return True when a canonical command drives an include/nested do.

        The source-driver lookup is required for project tracing. Keeping the
        check here preserves the registry boundary: this package never infers
        source execution from another registry field.
        """
        self.ensure_source_driver()
        assert self._module is not None
        check = getattr(self._module, "is_include", None)
        try:
            return bool(check(command))
        except RegistryIncompatibilityError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize upstream API errors
            raise RegistryIncompatibilityError(
                f"Registry source-driver lookup failed for {command!r}: {exc}"
            ) from exc

    @property
    def source_driver_available(self) -> bool:
        """True when the upstream explicit source-driver API is available."""
        return self._module is not None and callable(
            getattr(self._module, "is_include", None)
        )

    def ensure_source_driver(self) -> None:
        """Require the upstream source-driver capability for project tracing."""
        self._require_source_driver()
        version = self.version()
        if version == "unknown" or not _version_at_least_source_driver(version):
            raise RegistryIncompatibilityError(
                f"Registry v{version} is too old for project source tracing; "
                "install `stata-registry>=0.4.0`."
            )

    def _require_source_driver(self) -> Any:
        """Return the module or raise for project source-graph operations."""
        if not self.available:
            raise RegistryIncompatibilityError(self.describe_issue())
        if not self.source_driver_available:
            raise RegistryIncompatibilityError(
                "Registry source-driver capability unavailable: the upstream "
                "package must expose callable `is_include(token)`."
            )
        return self._module


def _version_tuple(version: str) -> tuple[int, ...]:
    """Parse the numeric prefix of a package version without a dependency."""
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", version)
    if match is None:
        return (0,)
    return tuple(int(part or 0) for part in match.groups())


def _version_at_least_source_driver(version: str) -> bool:
    """Return whether *version* is a released ``0.4.0`` or newer version."""
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(.*)$", version)
    if match is None:
        return False
    values = tuple(int(part or 0) for part in match.groups()[:3])
    suffix = match.group(4)
    if suffix and not suffix.startswith("+"):
        return False
    return values >= _SOURCE_DRIVER_MIN_VERSION
