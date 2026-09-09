"""Template scaffolding capability (FR-M33-02; FR-M6-01).

Skill-pack templates are versioned artefacts: a template directory holds
text files whose content AND relative paths carry placeholders in a
substitution syntax the template itself declares (a ``template.yaml``
manifest at the template root, defaulting to ``${NAME}``). Rendering is
pure substitution — values come from the action payload, nothing is
invented.

Safety contract: every rendered relative path must resolve INSIDE the
target directory. A template file whose rendered path escapes the target
(``..`` segments, absolute roots) is REFUSED with the file named before
any byte is written; the whole render is atomic in the sense that the
first escape refuses the action (no partial intent is hidden — already
written files from earlier entries stay, and the result names the
refusal so the caller can clean up). Non-UTF-8 template files are
refused with the path named.

Zero model calls: string substitution and path arithmetic only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from .capabilities import CapabilityOutcome

__all__ = ["TemplateScaffoldCapability"]

_CAPABILITY_NAME = "template_scaffold"

#: Manifest file at the template root declaring the substitution syntax.
_MANIFEST = "template.yaml"

#: Default delimiters when the template declares none.
_DEFAULT_OPEN = "${"
_DEFAULT_CLOSE = "}"


class TemplateScaffoldCapability:
    """The ``template_scaffold`` capability, owned by the ``scaffold``
    action class (FR-M33-01).

    Payload: ``{template_dir, target_dir, values}`` — ``values`` is a
    mapping of substitution key → string.
    """

    @property
    def name(self) -> str:
        return _CAPABILITY_NAME

    def run(self, action: Mapping[str, Any]) -> CapabilityOutcome:
        template_dir = action.get("template_dir")
        target_dir = action.get("target_dir")
        values = action.get("values")
        if not isinstance(template_dir, str) or not template_dir:
            return CapabilityOutcome(handled=False, reason="missing 'template_dir'")
        if not isinstance(target_dir, str) or not target_dir:
            return CapabilityOutcome(handled=False, reason="missing 'target_dir'")
        if not isinstance(values, Mapping):
            return CapabilityOutcome(handled=False, reason="missing 'values' mapping")
        source_root = Path(template_dir)
        if not source_root.is_dir():
            return CapabilityOutcome(handled=False, reason=f"template directory does not exist: {source_root}")

        open_delim, close_delim = self._syntax(source_root)
        if isinstance(open_delim, CapabilityOutcome):
            return open_delim
        substitutions = {
            f"{open_delim}{key}{close_delim}": str(value) for key, value in values.items()
        }
        # Longest keys first so overlapping names substitute deterministically.
        ordered = sorted(substitutions.items(), key=lambda item: len(item[0]), reverse=True)

        def render(text: str) -> str:
            for key, value in ordered:
                text = text.replace(key, value)
            return text

        target_root = Path(target_dir)
        written: list[dict[str, str]] = []
        for source in sorted(p for p in source_root.rglob("*") if p.is_file()):
            if source.name == _MANIFEST and source.parent == source_root:
                continue
            relative = source.relative_to(source_root)
            rendered_rel = Path(render(str(relative).replace("\\", "/")))
            # Refuse path escape BEFORE writing: the rendered relative path
            # must stay inside the target (no absolute roots, no .. climbs).
            if rendered_rel.is_absolute() or ".." in rendered_rel.parts:
                return CapabilityOutcome(
                    handled=False,
                    reason=f"template file '{relative}' renders to '{rendered_rel}', which escapes "
                    f"the target directory — scaffolding refused (no path escape)",
                )
            destination = target_root / rendered_rel
            try:
                content = source.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                return CapabilityOutcome(
                    handled=False,
                    reason=f"template file '{relative}' is not UTF-8 text — refused with the path named",
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(render(content), encoding="utf-8")
            written.append({"source": str(relative), "target": str(destination)})

        return CapabilityOutcome(
            handled=True,
            result={
                "template_dir": str(source_root),
                "target_dir": str(target_root),
                "files": written,
                "rendered": len(written),
            },
            reason=f"scaffolded {len(written)} files from {source_root} (FR-M6-01)",
        )

    @staticmethod
    def _syntax(source_root: Path) -> "tuple[str, str] | CapabilityOutcome":
        manifest = source_root / _MANIFEST
        if not manifest.is_file():
            return _DEFAULT_OPEN, _DEFAULT_CLOSE
        try:
            raw = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            return CapabilityOutcome(
                handled=False, reason=f"template manifest {_MANIFEST} unreadable: {error}"
            )
        if raw is None:
            return _DEFAULT_OPEN, _DEFAULT_CLOSE
        if not isinstance(raw, Mapping):
            return CapabilityOutcome(
                handled=False, reason=f"template manifest {_MANIFEST} must be a mapping"
            )
        syntax = raw.get("syntax", {})
        if not isinstance(syntax, Mapping):
            return CapabilityOutcome(
                handled=False, reason=f"template manifest 'syntax' must be a mapping"
            )
        open_delim = syntax.get("open", _DEFAULT_OPEN)
        close_delim = syntax.get("close", _DEFAULT_CLOSE)
        if not isinstance(open_delim, str) or not open_delim:
            return CapabilityOutcome(
                handled=False, reason="template manifest syntax.open must be a non-empty string"
            )
        if not isinstance(close_delim, str) or not close_delim:
            return CapabilityOutcome(
                handled=False, reason="template manifest syntax.close must be a non-empty string"
            )
        return open_delim, close_delim
