"""Output formatting for OSTicket Helper."""

from collections import defaultdict
from typing import Optional

from ostickethelper.browser import Ticket, TicketSummary


def format_ticket_list(tickets: list[TicketSummary], strings: dict, group_by_user: bool = True) -> str:
    """
    Format ticket list for output.

    Args:
        tickets: List of ticket summaries.
        strings: Strings dict (formatter section).
        group_by_user: Whether to group tickets by user.

    Returns:
        Formatted string output.
    """
    if not tickets:
        return strings.get("no_open_tickets", "No open tickets.")

    lines = []
    lines.append(f"## {strings.get('open_tickets_header', 'Open tickets')}")
    lines.append("")

    if group_by_user:
        # Group by user
        by_user = defaultdict(list)
        for ticket in tickets:
            by_user[ticket.user_name].append(ticket)

        for user_name, user_tickets in sorted(by_user.items()):
            lines.append(f"### {user_name}")
            for ticket in user_tickets:
                lines.append(f"- [id={ticket.id}] {ticket.subject}")
                lines.append(f"  URL: {ticket.url}")
            lines.append("")
    else:
        for ticket in tickets:
            lines.append(f"- [id={ticket.id}] {ticket.subject} ({ticket.user_name})")
            lines.append(f"  URL: {ticket.url}")

    total_str = strings.get("total", "Total: {count} tickets")
    lines.append(total_str.format(count=len(tickets)))

    return "\n".join(lines)


def format_ticket_detail(ticket: Ticket, strings: dict, downloaded_files: Optional[list[str]] = None) -> str:
    """
    Format detailed ticket information.

    Args:
        ticket: Full ticket details.
        strings: Strings dict (formatter section).
        downloaded_files: List of downloaded file paths.

    Returns:
        Formatted string output.
    """
    lbl_ticket = strings.get("ticket", "Ticket")
    lbl_subject = strings.get("subject", "Subject")
    lbl_sender = strings.get("sender", "Sender")
    lbl_email = strings.get("email", "Email")
    lbl_created = strings.get("created", "Created")
    lbl_status = strings.get("status", "Status")
    lbl_message = strings.get("message", "Message")
    lbl_attachments = strings.get("attachments", "Attachments")
    lbl_no_attachments = strings.get("no_attachments", "No attachments")

    lines = []
    lines.append(f"## {lbl_ticket} {ticket.id}")
    lines.append("")
    lines.append(f"**{lbl_subject}:** {ticket.subject}")
    lines.append(f"**{lbl_sender}:** {ticket.user_name}")
    lines.append(f"**{lbl_email}:** {ticket.user_email}")
    lines.append(f"**{lbl_created}:** {ticket.created}")
    lines.append(f"**{lbl_status}:** {ticket.status}")
    lines.append(f"**URL:** {ticket.url}")
    lines.append("")
    lines.append(f"### {lbl_message}:")
    lines.append("")
    lines.append(ticket.message)
    lines.append("")

    if ticket.attachments:
        lines.append(f"### {lbl_attachments} ({len(ticket.attachments)}):")
        lines.append("")

        if downloaded_files:
            for path in downloaded_files:
                lines.append(f"- {path}")
        else:
            for att in ticket.attachments:
                lines.append(f"- {att.name} ({att.type})")
    else:
        lines.append(f"*{lbl_no_attachments}*")

    return "\n".join(lines)


def format_resolve_result(ticket_ids: list[str], success: list[bool], message: str, strings: dict) -> str:
    """
    Format the result of resolving tickets.

    Args:
        ticket_ids: List of ticket IDs.
        success: List of success flags.
        message: The message posted.
        strings: Strings dict (formatter section).

    Returns:
        Formatted result string.
    """
    lbl_ticket = strings.get("ticket", "Ticket")
    lbl_resolve_header = strings.get("resolve_header", "Ticket resolution")
    lbl_message = strings.get("message", "Message")

    lines = []
    lines.append(f"## {lbl_resolve_header}")
    lines.append("")
    lines.append(f"**{lbl_message}:** {message}")
    lines.append("")

    succeeded = sum(success)
    failed = len(success) - succeeded

    for tid, ok in zip(ticket_ids, success):
        status = "✓" if ok else "✗"
        lines.append(f"- {lbl_ticket} {tid}: {status}")

    lines.append("")
    if failed == 0:
        all_resolved_str = strings.get("all_resolved", "All {count} tickets resolved successfully.")
        lines.append(all_resolved_str.format(count=succeeded))
    else:
        summary_str = strings.get("resolve_summary", "Resolved: {succeeded}, failed: {failed}")
        lines.append(summary_str.format(succeeded=succeeded, failed=failed))

    return "\n".join(lines)
