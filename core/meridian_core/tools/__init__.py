"""M9/M28 Tool Layer — FR-M9-01…08, FR-M28-03…07.

Submodules: surface (native tools, permission gate, sandbox, truncation,
credential hygiene, MCP pinning), search (semantic index port +
deterministic lexical-semantic implementation, reuse-first), editing
(hunk edits, binary/generated exclusion), mcp_client (minimal stdio
MCP client). LSP diagnostics/symbol consumption (FR-M28-01) and
tree-sitter structural edits (FR-M28-02) live in engine/lsp_bridge and
engine/structural, consumed by the engine.
"""

from .editing import (
    DEFAULT_LARGE_FILE_BYTES,
    EditRefusedError,
    ExclusionSet,
    Hunk,
    apply_hunk,
)
from .mcp_client import McpProtocolError, McpStdioClient
from .search import (
    LexicalSemanticIndex,
    ReuseVerdict,
    SearchHit,
    SemanticIndex,
    reuse_first_check,
)
from .surface import (
    CHANGE_CLASS_DEPENDENCY_ADD,
    TRUNCATION_MARKER,
    McpServerRefusedError,
    PinnedMcpServer,
    SandboxConfig,
    ToolDeniedError,
    ToolResult,
    ToolSurface,
    run_in_sandbox,
    scrub_environment,
    validate_mcp_server,
)

__all__ = [
    "DEFAULT_LARGE_FILE_BYTES",
    "EditRefusedError",
    "ExclusionSet",
    "Hunk",
    "apply_hunk",
    "McpProtocolError",
    "McpStdioClient",
    "LexicalSemanticIndex",
    "ReuseVerdict",
    "SearchHit",
    "SemanticIndex",
    "reuse_first_check",
    "CHANGE_CLASS_DEPENDENCY_ADD",
    "TRUNCATION_MARKER",
    "McpServerRefusedError",
    "PinnedMcpServer",
    "SandboxConfig",
    "ToolDeniedError",
    "ToolResult",
    "ToolSurface",
    "run_in_sandbox",
    "scrub_environment",
    "validate_mcp_server",
]
