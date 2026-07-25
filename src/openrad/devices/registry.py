"""A name -> Device-class registry, so the CLI can select drivers by string.

Drivers register themselves with the @register("name") decorator on import
(see devices/replay.py). Out-of-tree driver packages can do the same thing
against this registry without needing to modify openrad itself.
"""

from __future__ import annotations

from openrad.devices.base import Device

_REGISTRY: dict[str, type[Device]] = {}


def register(name: str):
    """Class decorator that registers a Device driver under `name`."""

    def _wrap(cls: type[Device]) -> type[Device]:
        if name in _REGISTRY:
            raise ValueError(f"device driver '{name}' already registered")
        _REGISTRY[name] = cls
        return cls

    return _wrap


def get(name: str) -> type[Device]:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        available = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError(f"unknown device driver '{name}', available: {available}") from exc


def available() -> list[str]:
    return sorted(_REGISTRY)
