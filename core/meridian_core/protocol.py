"""Protocol constants shared with the extension host.

Workstream B task 11 (FR-M32-09) replaces the hand-maintained copies with
generated types from ``shared/schema``; until then these are the Python-side
source of truth and the generated output must match them exactly.
"""

# Version of the JSON-RPC contract spoken on the wire. The extension refuses
# to proceed on mismatch (FR-M3-08); bump together with shared/schema.
PROTOCOL_VERSION = 1

# Version of this sidecar build, reported in the handshake for diagnostics.
CORE_VERSION = "0.0.1"

# JSON-RPC 2.0 standard error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Meridian-specific error codes (server-defined range -32000..-32099).
ERROR_NOT_IMPLEMENTED = -32001
ERROR_PROTOCOL_MISMATCH = -32002
