"""Tests for formatter.py."""

from ostickethelper.browser import Attachment, Ticket, TicketSummary
from ostickethelper.formatter import format_ticket_list, format_ticket_detail, format_resolve_result


# === format_ticket_list ===


def _make_summary(id="1", number="100", subject="Expense claim", user_name="Test", date="2026-01-15"):
    return TicketSummary(
        number=number,
        id=id,
        url=f"https://example.com/scp/tickets.php?id={id}",
        subject=subject,
        user_name=user_name,
        date=date,
    )


class TestFormatTicketList:
    def test_empty_list(self, default_strings):
        result = format_ticket_list([], default_strings["formatter"])
        assert result == "No open tickets."

    def test_single_ticket_grouped(self, default_strings):
        tickets = [_make_summary(id="10", subject="Travel costs", user_name="Matti")]
        result = format_ticket_list(tickets, default_strings["formatter"], group_by_user=True)
        assert "## Open tickets" in result
        assert "### Matti" in result
        assert "[id=10] Travel costs" in result
        assert "Total: 1 tickets" in result

    def test_single_ticket_ungrouped(self, default_strings):
        tickets = [_make_summary(id="10", subject="Travel costs", user_name="Matti")]
        result = format_ticket_list(tickets, default_strings["formatter"], group_by_user=False)
        assert "### Matti" not in result
        assert "[id=10] Travel costs (Matti)" in result
        assert "Total: 1 tickets" in result

    def test_multiple_tickets_grouped_by_user(self, default_strings):
        tickets = [
            _make_summary(id="1", subject="Coffee", user_name="Bertta"),
            _make_summary(id="2", subject="Travel", user_name="Antti"),
            _make_summary(id="3", subject="Supplies", user_name="Bertta"),
        ]
        result = format_ticket_list(tickets, default_strings["formatter"], group_by_user=True)
        # Users in alphabetical order
        antti_pos = result.index("### Antti")
        bertta_pos = result.index("### Bertta")
        assert antti_pos < bertta_pos
        # Bertta has two tickets
        assert "[id=1] Coffee" in result
        assert "[id=3] Supplies" in result

    def test_multiple_users_ungrouped(self, default_strings):
        tickets = [
            _make_summary(id="1", subject="Coffee", user_name="Bertta"),
            _make_summary(id="2", subject="Travel", user_name="Antti"),
        ]
        result = format_ticket_list(tickets, default_strings["formatter"], group_by_user=False)
        assert "(Bertta)" in result
        assert "(Antti)" in result
        assert "Total: 2 tickets" in result

    def test_url_shown(self, default_strings):
        tickets = [_make_summary(id="42")]
        result = format_ticket_list(tickets, default_strings["formatter"])
        assert "https://example.com/scp/tickets.php?id=42" in result

    def test_custom_strings(self):
        custom = {
            "no_open_tickets": "Ei avoimia tikettejä.",
            "open_tickets_header": "Avoimet kululaskutiketit",
            "total": "Yhteensä: {count} tikettiä",
        }
        tickets = [_make_summary(id="10", subject="Test")]
        result = format_ticket_list(tickets, custom, group_by_user=True)
        assert "## Avoimet kululaskutiketit" in result
        assert "Yhteensä: 1 tikettiä" in result


# === format_ticket_detail ===


def _make_ticket(
    id="5",
    subject="Expense claim January",
    user_name="Matti Meikäläinen",
    user_email="matti@example.com",
    created="2026-01-10",
    status="Open",
    message="Here is my expense claim.",
    attachments=None,
):
    return Ticket(
        number="200",
        id=id,
        url=f"https://example.com/scp/tickets.php?id={id}",
        subject=subject,
        user_name=user_name,
        user_email=user_email,
        created=created,
        status=status,
        message=message,
        attachments=attachments or [],
    )


class TestFormatTicketDetail:
    def test_basic_info(self, default_strings):
        ticket = _make_ticket()
        result = format_ticket_detail(ticket, default_strings["formatter"])
        assert "## Ticket 5" in result
        assert "**Subject:** Expense claim January" in result
        assert "**Sender:** Matti Meikäläinen" in result
        assert "**Email:** matti@example.com" in result
        assert "**Status:** Open" in result
        assert "Here is my expense claim." in result

    def test_no_attachments(self, default_strings):
        ticket = _make_ticket(attachments=[])
        result = format_ticket_detail(ticket, default_strings["formatter"])
        assert "*No attachments*" in result

    def test_attachments_without_downloads(self, default_strings):
        attachments = [
            Attachment(name="receipt.pdf", url="/file.php?key=1", type="attachment"),
            Attachment(name="photo.jpg", url="/file.php?key=2", type="inline"),
        ]
        ticket = _make_ticket(attachments=attachments)
        result = format_ticket_detail(ticket, default_strings["formatter"])
        assert "### Attachments (2):" in result
        assert "receipt.pdf (attachment)" in result
        assert "photo.jpg (inline)" in result

    def test_attachments_with_downloads(self, default_strings):
        attachments = [
            Attachment(name="receipt.pdf", url="/file.php?key=1", type="attachment"),
        ]
        ticket = _make_ticket(attachments=attachments)
        downloaded = ["/home/user/inbox/5/receipt.pdf"]
        result = format_ticket_detail(ticket, default_strings["formatter"], downloaded_files=downloaded)
        assert "### Attachments (1):" in result
        assert "/home/user/inbox/5/receipt.pdf" in result
        # Should NOT show the type-based format when downloads are provided
        assert "receipt.pdf (attachment)" not in result


# === format_resolve_result ===


class TestFormatResolveResult:
    def test_single_success(self, default_strings):
        result = format_resolve_result(["10"], [True], "Paid 1.2.2026", default_strings["formatter"])
        assert "## Ticket resolution" in result
        assert "**Message:** Paid 1.2.2026" in result
        assert "Ticket 10: ✓" in result
        assert "All 1 tickets resolved successfully." in result

    def test_multiple_all_success(self, default_strings):
        result = format_resolve_result(["10", "11", "12"], [True, True, True], "Processed", default_strings["formatter"])
        assert "Ticket 10: ✓" in result
        assert "Ticket 11: ✓" in result
        assert "Ticket 12: ✓" in result
        assert "All 3 tickets resolved successfully." in result

    def test_partial_failure(self, default_strings):
        result = format_resolve_result(["10", "11"], [True, False], "Processed", default_strings["formatter"])
        assert "Ticket 10: ✓" in result
        assert "Ticket 11: ✗" in result
        assert "Resolved: 1, failed: 1" in result

    def test_all_failed(self, default_strings):
        result = format_resolve_result(["10", "11"], [False, False], "Processed", default_strings["formatter"])
        assert "Resolved: 0, failed: 2" in result
