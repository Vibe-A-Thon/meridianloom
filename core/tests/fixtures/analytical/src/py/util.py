"""Standalone utility: no imports, nobody imports it (fixture)."""


def slugify(text: str) -> str:
    return text.lower().replace(" ", "-")
