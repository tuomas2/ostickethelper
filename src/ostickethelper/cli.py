#!/usr/bin/env python3
"""
OSTicket Helper - CLI tool for managing OSTicket tickets.

Usage:
    ostickethelper list
    ostickethelper read 656694
    ostickethelper resolve 656694 --message "Paid"
"""

import sys
from typing import Optional

import click

from ostickethelper.archiver import generate_receipt_pdf
from ostickethelper.config import load_config
from ostickethelper.formatter import format_ticket_list, format_ticket_detail, format_resolve_result
from ostickethelper.browser import OSTicketBrowser


@click.group()
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=False),
    default=None,
    help="Path to configuration file. Defaults to config.yaml in script directory.",
)
@click.pass_context
def cli(ctx, config_path: Optional[str]) -> None:
    """
    OSTicket Helper - Manage OSTicket tickets.

    This tool helps process tickets submitted via OSTicket.
    """
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path


@cli.command("list")
@click.option(
    "--status",
    type=click.Choice(["open", "closed"]),
    default="open",
    help="Filter by ticket status.",
)
@click.option(
    "--user",
    type=str,
    default=None,
    help="Filter by user name.",
)
@click.pass_context
def list_tickets(ctx, status: str, user: Optional[str]) -> None:
    """
    List tickets from OSTicket.

    Examples:
        ostickethelper list
        ostickethelper list --status open
        ostickethelper list --user "John Doe"
    """
    try:
        app_config = load_config(ctx.obj["config_path"])
        strings = app_config.strings
        cli_strings = strings.get("cli", {})
        fmt_strings = strings.get("formatter", {})

        click.echo(cli_strings.get("logging_in", "Logging in to OSTicket..."), err=True)

        with OSTicketBrowser(app_config.osticket) as browser:
            click.echo(cli_strings.get("fetching", "Fetching {status} tickets...").format(status=status), err=True)
            tickets = browser.list_tickets(queue=status)

            if user:
                tickets = [t for t in tickets if user.lower() in t.user_name.lower()]

            click.echo("", err=True)
            output = format_ticket_list(tickets, fmt_strings)
            click.echo(output)

    except FileNotFoundError as e:
        click.echo(f"{strings.get('cli', {}).get('error', 'Error')}: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"{strings.get('cli', {}).get('error', 'Error')}: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("ticket_ids", nargs=-1, required=True)
@click.option(
    "--no-download",
    is_flag=True,
    default=False,
    help="Don't download attachments, just show ticket info.",
)
@click.option(
    "--no-pdf",
    is_flag=True,
    default=False,
    help="Don't generate PDF receipt, just download attachments.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite existing PDF receipt.",
)
@click.pass_context
def read(ctx, ticket_ids: tuple[str, ...], no_download: bool, no_pdf: bool,
         force: bool) -> None:
    """
    Read one or more tickets, download attachments, and generate PDF receipts.

    TICKET_IDS can be ticket numbers (e.g., 656694) or internal IDs.

    PDF receipts are saved to inbox/<id>.pdf for manual review.

    Examples:
        ostickethelper read 656694
        ostickethelper read 656694 656695
        ostickethelper read 656694 --no-pdf
    """
    try:
        app_config = load_config(ctx.obj["config_path"])
        strings = app_config.strings
        cli_strings = strings.get("cli", {})
        fmt_strings = strings.get("formatter", {})

        click.echo(cli_strings.get("logging_in", "Logging in to OSTicket..."), err=True)

        with OSTicketBrowser(app_config.osticket) as browser:
            all_outputs = []
            for tid in ticket_ids:
                click.echo(cli_strings.get("reading", "Reading ticket {tid}...").format(tid=tid), err=True)
                ticket = browser.read_ticket(tid)

                downloaded_files = []
                if not no_download and ticket.attachments:
                    click.echo(
                        cli_strings.get("downloading", "Downloading {count} attachments...").format(
                            count=len(ticket.attachments)
                        ),
                        err=True,
                    )
                    downloaded_files = browser.download_attachments(ticket)

                all_outputs.append(format_ticket_detail(ticket, fmt_strings, downloaded_files))

                # Generate PDF receipt to inbox
                if not no_download and not no_pdf:
                    click.echo(cli_strings.get("generating", "Generating receipt..."), err=True)
                    try:
                        result = generate_receipt_pdf(tid, app_config.osticket, strings, force=force)
                        click.echo(result, err=True)
                    except (FileNotFoundError, RuntimeError) as e:
                        click.echo(
                            f"{cli_strings.get('generation_failed', 'Receipt generation failed')}: {e}",
                            err=True,
                        )

            click.echo("", err=True)
            click.echo("\n\n".join(all_outputs))

    except FileNotFoundError as e:
        click.echo(f"{strings.get('cli', {}).get('error', 'Error')}: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"{strings.get('cli', {}).get('error', 'Error')}: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("ticket_ids", nargs=-1, required=True)
@click.option(
    "--message",
    "-m",
    type=str,
    required=True,
    help="Message to post when resolving.",
)
@click.pass_context
def resolve(ctx, ticket_ids: tuple[str, ...], message: str) -> None:
    """
    Resolve one or more tickets with a message.

    Examples:
        ostickethelper resolve 656694 --message "Paid"
        ostickethelper resolve 656694 656695 --message "Resolved 25.1.2026"
    """
    try:
        app_config = load_config(ctx.obj["config_path"])
        strings = app_config.strings
        cli_strings = strings.get("cli", {})
        fmt_strings = strings.get("formatter", {})

        click.echo(cli_strings.get("logging_in", "Logging in to OSTicket..."), err=True)

        with OSTicketBrowser(app_config.osticket) as browser:
            results = []
            for tid in ticket_ids:
                click.echo(cli_strings.get("resolving", "Resolving ticket {tid}...").format(tid=tid), err=True)
                success = browser.resolve_ticket(tid, message)
                results.append(success)

            click.echo("", err=True)
            output = format_resolve_result(list(ticket_ids), results, message, fmt_strings)
            click.echo(output)

    except FileNotFoundError as e:
        click.echo(f"{strings.get('cli', {}).get('error', 'Error')}: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"{strings.get('cli', {}).get('error', 'Error')}: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
