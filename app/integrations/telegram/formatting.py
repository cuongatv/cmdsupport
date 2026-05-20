from __future__ import annotations

from html import escape as html_escape


def escape_html(text: str) -> str:
    return html_escape(text, quote=True).replace("'", "&#x27;")


def format_task_created(task_title: str, task_url: str, assignee_username: str | None) -> str:
    title = escape_html(task_title)
    url = task_url
    assignee = f" @{escape_html(assignee_username)}" if assignee_username else ""
    return (
        f"<b>Task created:</b> <a href=\"{url}\">{title}</a>"
        f"{assignee}"
    )


def format_task_status_changed(
    task_title: str,
    from_state: str,
    to_state: str,
    task_url: str,
) -> str:
    title = escape_html(task_title)
    from_text = escape_html(from_state)
    to_text = escape_html(to_state)
    return (
        f"<b>Task status changed:</b> <a href=\"{task_url}\">{title}</a>"
        f" {from_text} → {to_text}"
    )


def format_command_reply(message: str) -> str:
    return escape_html(message)
