"""Agent identity trailers (FR-M36-03, F0 Workstream E task 24).

Every vendor's ``Co-Authored-By`` variant parses into an attribution record
through the single shared trailer parser; Meridian's own co-author line is
recognised and reserved for Meridian-authored commits.
"""

from __future__ import annotations

from meridian_core.trailers import (
    append_trailer,
    co_author_attribution,
    parse_attributions,
)

CLAUDE = "Co-Authored-By: Claude <noreply@anthropic.com>"
COPILOT = "Co-Authored-By: GitHub Copilot <copilot@github.com>"
CURSOR = "Co-Authored-By: Cursor <cursor@anysphere.inc>"
CURSOR_ALT = "Co-Authored-By: Cursor <cursor@cursor.com>"
MERIDIAN = "Co-Authored-By: Meridian <meridian@meridianloom.dev>"


class TestCoAuthorAttribution:
    def test_claude_variant(self):
        record = co_author_attribution("Claude <noreply@anthropic.com>")
        assert record == {
            "name": "Claude",
            "email": "noreply@anthropic.com",
            "vendor": "claude",
            "meridianAuthored": False,
        }

    def test_copilot_variant(self):
        record = co_author_attribution("GitHub Copilot <copilot@github.com>")
        assert record["vendor"] == "github-copilot"
        assert record["meridianAuthored"] is False

    def test_cursor_variants(self):
        for value in ("Cursor <cursor@anysphere.inc>", "Cursor <cursor@cursor.com>"):
            assert co_author_attribution(value)["vendor"] == "cursor"

    def test_generic_name_email(self):
        record = co_author_attribution("Ada Lovelace <ada@example.com>")
        assert record["vendor"] == "generic"
        assert record["name"] == "Ada Lovelace"
        assert record["meridianAuthored"] is False

    def test_meridian_is_recognised_and_reserved(self):
        record = co_author_attribution("Meridian <meridian@meridianloom.dev>")
        assert record["vendor"] == "meridian"
        assert record["meridianAuthored"] is True

    def test_meridian_reserved_by_name_even_with_foreign_email(self):
        # The reservation binds on the identity, not the mailbox: a line that
        # claims to be Meridian IS Meridian's, whatever address it carries.
        record = co_author_attribution("Meridian <something-else@example.com>")
        assert record["vendor"] == "meridian"
        assert record["meridianAuthored"] is True

    def test_unparseable_value_is_unknown_not_a_crash(self):
        record = co_author_attribution("no email here")
        assert record["vendor"] == "unknown"
        assert record["name"] == "no email here"
        assert record["email"] is None
        assert record["meridianAuthored"] is False


class TestParseAttributions:
    def test_every_vendor_in_one_message(self):
        message = (
            "feat: mixed session\n\n"
            f"{CLAUDE}\n{COPILOT}\n{CURSOR}\n"
            "Co-Authored-By: Ada Lovelace <ada@example.com>\n"
            f"{MERIDIAN}\n"
        )
        records = parse_attributions(message)
        assert [r["vendor"] for r in records] == [
            "claude",
            "github-copilot",
            "cursor",
            "generic",
            "meridian",
        ]
        assert sum(r["meridianAuthored"] for r in records) == 1

    def test_trailer_block_aware_appended_attribution_is_found(self):
        # The hook's own trailer edit must not hide agent identity: appending
        # Meridian-Ledger keeps the Co-Authored-By block intact.
        message = "fix: thing\n\n" f"{CLAUDE}\n"
        message = append_trailer(message, "Meridian-Ledger", "3-5")
        assert "Meridian-Ledger: 3-5" in message
        records = parse_attributions(message)
        assert len(records) == 1
        assert records[0]["vendor"] == "claude"

    def test_no_co_authors_is_empty(self):
        assert parse_attributions("fix: human only\n") == []

    def test_non_trailer_lines_are_ignored(self):
        message = "body mentions Co-Authored-By: inline but not as its own line\n"
        assert parse_attributions(message) == []
