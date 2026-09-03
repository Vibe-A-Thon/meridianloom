"""Observer manager: registry, health reporting, sticky degradation (FR-M35-08).

The manager owns the per-vendor observer adapters and is the single entry
point the sidecar (and doctor) asks about external-agent observation:

* ``observe()`` runs every registered observer's fallback chain and returns
  the union of observations (one per vendor — the best evidence wins).
* ``health()`` reports per-observer status for the doctor check and the
  External Agents screen: ``ok`` or ``degraded``, with the warnings that
  explain the degradation.
* Warnings are STICKY for the process lifetime (one session): a format
  change that forced a downgrade stays visible until the sidecar restarts
  (NFR-32: "within one session", never silence).

Zero model calls (FR-M36-07); pure stdlib.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import Observer

STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"


class ObserverManager:
    """Registry of observers with health reporting and warning retention."""

    def __init__(self, observers: list[Observer] | None = None) -> None:
        self._observers: dict[str, Observer] = {}
        # vendor -> list of sticky warning messages (NFR-32: visible for the
        # whole session once raised).
        self._warnings: dict[str, list[str]] = {}
        for observer in observers or []:
            self.register(observer)

    def register(self, observer: Observer) -> None:
        self._observers[observer.vendor] = observer

    def warn(self, vendor: str, message: str) -> None:
        """Record a sticky degradation warning directly (never silent)."""
        retained = self._warnings.setdefault(vendor, [])
        if message not in retained:
            retained.append(message)

    @property
    def vendors(self) -> list[str]:
        return sorted(self._observers)

    # -- Observation ---------------------------------------------------------

    def observe(self, workspace: Path | str, now: datetime | None = None) -> list:
        """Run every observer's fallback chain; one observation per vendor.

        Downgrade warnings the chains raise are retained (sticky, visible
        for the rest of the session) before the observations are returned.
        """
        from .base import Observation  # local: keep the module import graph tiny

        now = now or datetime.now(timezone.utc)
        root = Path(workspace)
        observations: list[Observation] = []
        for vendor in self.vendors:
            outcome = self._observers[vendor].observe(root, now)
            retained = self._warnings.setdefault(vendor, [])
            for message in outcome.warnings:
                # Sticky AND deduplicated: the session monitor polls every
                # few hundred milliseconds, and a persistent format change
                # must not pile up duplicate warnings (NFR-32: visible, not
                # noisy).
                if message not in retained:
                    retained.append(message)
            if outcome.observation is not None:
                observations.append(outcome.observation)
        return observations

    # -- Health ---------------------------------------------------------------

    def health(self) -> list[dict[str, Any]]:
        """Per-observer health records for doctor and the UI."""
        records: list[dict[str, Any]] = []
        for vendor in self.vendors:
            observer = self._observers[vendor]
            warnings = list(self._warnings.get(vendor, []))
            try:
                extra = observer.health()
            except Exception as error:  # noqa: BLE001 - health must never crash
                warnings.append(f"health probe failed: {error!r}")
                extra = {}
            status = STATUS_DEGRADED if warnings else STATUS_OK
            records.append(
                {
                    "name": vendor,
                    "vendor": vendor,
                    "status": status,
                    "detail": extra.get("detail", ""),
                    "vendorRelease": getattr(observer, "vendor_release", "unknown"),
                    "adapterVersion": getattr(observer, "adapter_version", "unknown"),
                    "warnings": warnings,
                }
            )
        return records

    def warnings(self, vendor: str | None = None) -> list[str]:
        if vendor is not None:
            return list(self._warnings.get(vendor, []))
        return [m for messages in self._warnings.values() for m in messages]
