"""Playwright-based browser automation for OSTicket."""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from playwright.sync_api import Page, sync_playwright, Browser, BrowserContext

from ostickethelper.config import OSTicketConfig


@dataclass
class Attachment:
    """Represents a ticket attachment."""
    name: str
    url: str
    type: str  # 'attachment' or 'inline'


@dataclass
class Ticket:
    """Represents an OSTicket ticket."""
    number: str
    id: str
    url: str
    subject: str
    user_name: str
    user_email: str
    created: str
    status: str
    message: str
    attachments: list[Attachment]


@dataclass
class TicketSummary:
    """Summary of a ticket for listing."""
    number: str
    id: str
    url: str
    subject: str
    user_name: str
    date: str


class OSTicketBrowser:
    """Browser automation for OSTicket operations."""

    def __init__(self, config: OSTicketConfig):
        self.config = config
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    def __enter__(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.config.headless,
            slow_mo=self.config.slow_mo,
        )
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        self._login()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._page:
            self._page.close()
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def _login(self) -> None:
        """Log in to OSTicket."""
        page = self._page
        page.goto(f"{self.config.url}/scp/login.php")

        page.get_by_role("textbox", name="Email or Username").fill(self.config.username)
        page.get_by_role("textbox", name="Password").fill(self.config.password)
        page.get_by_role("button", name=" Log In").click()

        # Wait for successful login
        page.wait_for_url("**/scp/**", timeout=10000)
        time.sleep(0.5)  # Brief pause for page to stabilize

    def list_tickets(self, queue: str = "open") -> list[TicketSummary]:
        """
        List tickets from a queue (fetches all pages).

        Args:
            queue: Queue to list ('open' or 'closed')

        Returns:
            List of TicketSummary objects.
        """
        page = self._page

        # queue=1 = Open, queue=8 = Closed
        queue_map = {"open": 1, "closed": 8}
        queue_id = queue_map.get(queue, 1)

        tickets = []
        current_page = 1

        while True:
            # Build URL with page parameter
            url = f"{self.config.url}/scp/tickets.php?queue={queue_id}"
            if current_page > 1:
                url += f"&p={current_page}"

            page.goto(url)
            time.sleep(0.5)

            # Get table rows from tbody (skip header)
            rows = page.locator("table tbody tr").all()
            page_tickets = 0

            for row in rows:
                cells = row.locator("td").all()
                if len(cells) < 5:
                    continue

                # Get ticket number link
                ticket_link = cells[1].locator("a").first
                ticket_number = ticket_link.inner_text().strip()
                ticket_href = ticket_link.get_attribute("href") or ""

                # Extract ticket ID from href
                ticket_id = ""
                if "id=" in ticket_href:
                    ticket_id = ticket_href.split("id=")[-1].split("&")[0]

                # Get subject link
                subject_link = cells[3].locator("a").first
                subject = subject_link.inner_text().strip()

                # Get user name
                user_name = cells[4].inner_text().strip()

                # Get date
                date = cells[2].inner_text().strip()

                ticket = TicketSummary(
                    number=ticket_number,
                    id=ticket_id,
                    url=f"{self.config.url}/scp/tickets.php?id={ticket_id}",
                    subject=subject,
                    user_name=user_name,
                    date=date,
                )
                tickets.append(ticket)
                page_tickets += 1

            # Check if there's a next page link
            next_page_link = page.locator(f'a[href*="p={current_page + 1}"]')
            if next_page_link.count() == 0 or page_tickets == 0:
                break

            current_page += 1

        return tickets

    def read_ticket(self, ticket_id: str) -> Ticket:
        """
        Read a single ticket's details.

        Args:
            ticket_id: The ticket ID (from URL parameter).

        Returns:
            Ticket object with full details.
        """
        page = self._page
        page.goto(f"{self.config.url}/scp/tickets.php?id={ticket_id}")
        time.sleep(0.5)

        # Get ticket number from heading
        heading = page.get_by_role("heading", level=2).first
        ticket_number = heading.inner_text().replace("Ticket #", "").strip()

        # Get all ticket details via JavaScript (faster than multiple locator calls)
        details = page.evaluate(r'''() => {
            const get = (sel) => {
                const el = document.querySelector(sel);
                if (!el) return "";
                // Add space between file extension and size (e.g., ".pdf114" -> ".pdf 114")
                // Use [a-zA-Z] instead of \\w to avoid matching digits in extension
                let text = el.innerText;
                text = text.replace(/(\.([a-zA-Z]{2,4}))(\d+(\.\d+)?\s*(kb|mb|gb|bytes))/gi, '$1 $3');
                return text.trim();
            };
            const getByHeader = (header) => {
                const th = [...document.querySelectorAll('th')].find(t => t.innerText.includes(header));
                if (th && th.nextElementSibling) return th.nextElementSibling.innerText.trim();
                return "";
            };
            const getUserLink = () => {
                const th = [...document.querySelectorAll('th')].find(t => t.innerText.includes("User:"));
                if (th && th.nextElementSibling) {
                    const a = th.nextElementSibling.querySelector('a');
                    return a ? a.innerText.trim() : "";
                }
                return "";
            };
            // Collect all thread entries (main message + replies)
            const getThreadMessages = () => {
                const entries = document.querySelectorAll('.thread-entry');
                if (entries.length === 0) return "";
                return [...entries].map(entry => {
                    const header = entry.querySelector('.header');
                    const body = entry.querySelector('.thread-body');
                    const headerText = header ? header.innerText.trim() : "";
                    const bodyText = body ? body.innerText.trim() : "";
                    if (headerText && bodyText) return headerText + "\n" + bodyText;
                    return bodyText || headerText || "";
                }).filter(Boolean).join("\n\n---\n\n");
            };
            return {
                subject: get('h3.title') || getByHeader('Subject:') || get('h3') || "",
                user_name: getUserLink(),
                user_email: getByHeader('Email:'),
                created: getByHeader('Create Date:'),
                status: getByHeader('Status:'),
                message: getThreadMessages() || get('.thread-entry .thread-body') || ""
            };
        }''')

        subject = details.get("subject", "")
        user_name = details.get("user_name", "")
        user_email = details.get("user_email", "")
        created = details.get("created", "")
        status = details.get("status", "")
        message = details.get("message", "")

        # Get all attachments
        attachments = self._get_all_attachments()

        return Ticket(
            number=ticket_number,
            id=ticket_id,
            url=f"{self.config.url}/scp/tickets.php?id={ticket_id}",
            subject=subject,
            user_name=user_name,
            user_email=user_email,
            created=created,
            status=status,
            message=message,
            attachments=attachments,
        )

    def _get_all_attachments(self) -> list[Attachment]:
        """Get all attachments from current ticket page."""
        page = self._page
        attachments = []

        # 1. Regular file attachments (download links)
        for link in page.locator('a[href*="/file.php?key="]').all():
            name = link.inner_text().strip()
            url = link.get_attribute("href") or ""
            if name and url:
                attachments.append(Attachment(name=name, url=url, type="attachment"))

        # 2. Inline images
        inline = page.evaluate('''() => {
            const imgs = document.querySelectorAll('img[src*="/file.php"]');
            return Array.from(imgs).map((img, idx) => ({
                name: img.alt || `inline_image_${idx + 1}.jpg`,
                url: img.src,
                type: 'inline'
            }));
        }''')
        for item in inline:
            attachments.append(Attachment(
                name=item["name"],
                url=item["url"],
                type=item["type"],
            ))

        return attachments

    def download_attachments(self, ticket: Ticket, download_dir: Optional[str] = None) -> list[str]:
        """
        Download all attachments from a ticket.

        Args:
            ticket: Ticket object with attachments.
            download_dir: Directory to save files. Defaults to inbox_dir/<id>.

        Returns:
            List of downloaded file paths.
        """
        if not ticket.attachments:
            return []

        if download_dir is None:
            download_dir = Path(self.config.inbox_dir) / ticket.id
        else:
            download_dir = Path(download_dir)

        download_dir.mkdir(parents=True, exist_ok=True)

        page = self._page
        downloaded = []

        for att in ticket.attachments:
            # Resolve full URL
            if att.url.startswith("/"):
                full_url = f"{self.config.url}{att.url}"
            else:
                full_url = att.url

            # Sanitize filename
            safe_name = att.name.replace("/", "_").replace("\\", "_")
            file_path = download_dir / safe_name

            try:
                # Use direct HTTP request - works for both attachments and inline images
                response = page.request.get(full_url)
                file_path.write_bytes(response.body())
                downloaded.append(str(file_path))
            except Exception as e:
                print(f"Warning: Failed to download {att.name}: {e}")

        # Save ticket metadata
        metadata_path = download_dir / "ticket.json"
        metadata = {
            "id": ticket.id,
            "number": ticket.number,
            "url": ticket.url,
            "subject": ticket.subject,
            "user": {
                "name": ticket.user_name,
                "email": ticket.user_email,
            },
            "created": ticket.created,
            "status": ticket.status,
            "message": ticket.message,
            "attachments": [att.name for att in ticket.attachments],
        }
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        return downloaded

    def resolve_ticket(self, ticket_id: str, message: str) -> bool:
        """
        Post a reply and resolve a ticket.

        Args:
            ticket_id: The ticket ID.
            message: Message to post as reply.

        Returns:
            True if successful, False otherwise.
        """
        page = self._page
        page.goto(f"{self.config.url}/scp/tickets.php?id={ticket_id}")
        time.sleep(0.5)

        try:
            # Wait for page to fully load
            page.wait_for_load_state("networkidle", timeout=15000)

            # Set reply message via Redactor editor API.
            # Redactor stores content in a contenteditable div but validates
            # against the hidden textarea. source.setCode() only updates the
            # editor, so we must also set the textarea value directly.
            page.wait_for_selector('textarea#response', state='attached', timeout=10000)
            page.evaluate(
                '''(msg) => {
                    const html = '<p>' + msg + '</p>';
                    const r = $('textarea#response').data('redactor');
                    r.source.setCode(html);
                    $('textarea#response').val(html);
                }''',
                message,
            )

            # Change status to Resolved (use list for selectOption)
            page.locator('select[name="reply_status_id"]').select_option(["Resolved"])

            # Submit the reply and wait for navigation away from ticket page.
            # After success, URL changes from tickets.php?id=X to e.g.
            # tickets.php#reply or tickets.php?queue=1.
            ticket_url = page.url
            page.get_by_role("button", name="Post Reply").click()
            page.wait_for_function(
                f'() => window.location.href !== "{ticket_url}"',
                timeout=30000,
            )

            return True

        except Exception as e:
            print(f"Error resolving ticket: {e}")
            return False
