"""Protocol constants for the sidecar, sourced from the generated bus types.

FR-M32-09: the wire contract lives in shared/schema/ and is generated into
shared/py/bus_types.py. This module re-exports those constants so existing
imports keep working, and owns only the one thing the schema does not model:
this build's version string, reported in the handshake for diagnostics.
"""

from __future__ import annotations

import bus_types

# Wire contract (generated — do not edit here; edit shared/schema/).
PROTOCOL_VERSION = bus_types.PROTOCOL_VERSION

PARSE_ERROR = bus_types.PARSE_ERROR
INVALID_REQUEST = bus_types.INVALID_REQUEST
METHOD_NOT_FOUND = bus_types.METHOD_NOT_FOUND
INVALID_PARAMS = bus_types.INVALID_PARAMS
INTERNAL_ERROR = bus_types.INTERNAL_ERROR
ERROR_NOT_IMPLEMENTED = bus_types.NOT_IMPLEMENTED
ERROR_PROTOCOL_MISMATCH = bus_types.PROTOCOL_MISMATCH
ERROR_TIER_DISABLED = bus_types.TIER_DISABLED
ERROR_LEDGER_UNAVAILABLE = bus_types.LEDGER_UNAVAILABLE

# Version of this sidecar build, reported in the handshake for diagnostics.
CORE_VERSION = "0.0.1"
