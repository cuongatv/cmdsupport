from __future__ import annotations

from app.integrations.telegram.formatting import (
    escape_html,
    format_command_reply,
    format_task_created,
    format_task_status_changed,
)


def test_escape_html_escapes_telegram_metacharacters() -> None:
    assert escape_html("<script>alert(1)</script> & friends") == "&lt;script&gt;alert(1)&lt;/script&gt; &amp; friends"


def test_format_task_created_escapes_title_and_keeps_url_verbatim() -> None:
    rendered = format_task_created("Fix <bug> & test", "http://example/t/1", "alice")

    assert "&lt;bug&gt; &amp;" in rendered
    assert "http://example/t/1" in rendered
    assert "@alice" in rendered


def test_format_task_status_changed_uses_html_mode() -> None:
    rendered = format_task_status_changed("Fix <bug>", "Todo", "Done", "http://example/t/1")

    assert "&lt;bug&gt;" in rendered
    assert "Todo" in rendered
    assert "Done" in rendered
    assert "http://example/t/1" in rendered


def test_format_command_reply_escapes_input() -> None:
    assert format_command_reply("Hello <world> & friends") == "Hello &lt;world&gt; &amp; friends"
