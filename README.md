# OSTicket Helper

A CLI tool for managing OSTicket tickets via browser automation. Supports listing, reading (with attachment download and PDF receipt generation), and resolving tickets.

## Features

- **List** open/closed tickets, grouped by user
- **Read** tickets: download attachments, generate a combined PDF receipt (Typst summary page + attachment pages)
- **Resolve** tickets with a message
- **Fully localizable**: all user-facing strings are configurable via YAML

## Requirements

- Python 3.10+
- [Poetry](https://python-poetry.org/)
- [Playwright](https://playwright.dev/python/) (Chromium)
- [Typst](https://typst.app/) (for PDF receipt generation)
- GPG (for decrypting the password file)

## Installation

```bash
poetry install
playwright install chromium
```

## Configuration

Create a YAML config file (see `src/ostickethelper/defaults.yaml` for all available keys):

```yaml
osticket:
  url: "https://your-osticket-instance.com"
  username: "agent"
  secrets_file: "secrets/osticket-password.txt.gpg"
  headless: true
  slow_mo: 0
  inbox_dir: "inbox/osticket"
  logo_path: "resources/logo.png"       # optional
  receipts_dir: "receipts"             # optional, default: "receipts"
  temp_dir: ".tmp"                      # optional, default: ".tmp"
  template_path: "my-template.typ"      # optional, default: built-in template
```

All relative paths are resolved from the working directory (where you run the command).

### Configuration fields

| Field | Required | Description |
|-------|----------|-------------|
| `url` | Yes | OSTicket base URL |
| `username` | Yes | Agent username |
| `secrets_file` | Yes | Path to GPG-encrypted password file |
| `headless` | No | Run browser headless (default: `true`) |
| `slow_mo` | No | Slow down browser actions in ms (default: `0`) |
| `inbox_dir` | No | Directory for downloaded tickets (default: `inbox/osticket`) |
| `logo_path` | No | Logo image for PDF receipts (omit for no logo) |
| `receipts_dir` | No | Archive directory for receipts (default: `receipts`) |
| `temp_dir` | No | Temporary directory for Typst compilation (default: `.tmp`) |
| `template_path` | No | Custom Typst template (default: built-in `template.typ`) |

## String customization (localization)

All user-facing strings can be overridden in the config file under the `strings` section. The tool ships with English defaults (`defaults.yaml`). To localize, add a `strings` section to your config:

```yaml
strings:
  formatter:
    no_open_tickets: "Ei avoimia tikettejä."
    open_tickets_header: "Avoimet tiketit"
    total: "Yhteensä: {count} tikettiä"
  cli:
    logging_in: "Kirjaudutaan OSTicketiin..."
  pdf:
    title: "TOSITE"
    lang: "fi"
```

Only override the strings you want to change; the rest will use English defaults. See `src/ostickethelper/defaults.yaml` for the full list of available string keys.

## Usage

```bash
# List open tickets
ostickethelper --config config.yaml list

# List closed tickets
ostickethelper --config config.yaml list --status closed

# Read tickets and generate PDF receipts
ostickethelper --config config.yaml read 339 340

# Read without generating PDF
ostickethelper --config config.yaml read 339 --no-pdf

# Resolve tickets
ostickethelper --config config.yaml resolve 339 340 --message "Paid"
```

## PDF template customization

The default PDF template (`template.typ`) uses `string.Template` syntax with `$variable` placeholders. You can provide your own template via the `template_path` config option.

Available template variables:

| Variable | Description |
|----------|-------------|
| `$pdf_title` | Document title (from `strings.pdf.title`) |
| `$ticket_id` | Ticket ID |
| `$ticket_number` | Ticket number |
| `$logo_block` | Typst `#image(...)` block, or empty if no logo |
| `$subject` | Ticket subject (Typst-escaped) |
| `$user_name` | Sender name (Typst-escaped) |
| `$date_display` | Creation date |
| `$today_display` | Processing date |
| `$message` | Ticket message (Typst-escaped) |
| `$attachments_block` | Typst-formatted attachment list |
| `$lang` | Language code (from `strings.pdf.lang`) |
| `$lbl_ticket` | Label: "Ticket" |
| `$lbl_subject` | Label: "Subject" |
| `$lbl_sender` | Label: "Sender" |
| `$lbl_created` | Label: "Created" |
| `$lbl_processed` | Label: "Processed" |
| `$lbl_message` | Label: "Message" |
| `$lbl_attachments` | Label: "Attachments" |

## License

GPL-3.0 — see [LICENSE](LICENSE).
