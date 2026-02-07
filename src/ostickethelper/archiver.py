"""Generate PDF receipts from OSTicket tickets."""

import json
import re
import shutil
import subprocess
import uuid
from datetime import datetime, date
from pathlib import Path
from string import Template

import pikepdf
from PIL import Image

from ostickethelper.config import OSTicketConfig

# Default image compression settings
DEFAULT_MAX_WIDTH = 800
DEFAULT_JPEG_QUALITY = 75


def parse_osticket_date(date_str: str) -> date:
    """
    Parse OSTicket date format to a date object.

    Format: "1/3/26 9:20 PM" (US: month/day/year)

    Args:
        date_str: Date string from ticket.json 'created' field.

    Returns:
        date object.
    """
    dt = datetime.strptime(date_str.strip(), "%m/%d/%y %I:%M %p")
    return dt.date()


def next_sequential_number(target_dir: Path, date_prefix: str) -> int:
    """
    Find the next sequential number NN for a given date prefix in the target directory.

    Scans existing files matching YYYYMMDD_NN_*.pdf and returns the next number.

    Args:
        target_dir: Directory to scan.
        date_prefix: Date prefix in YYYYMMDD format.

    Returns:
        Next sequential number (starting from 1).
    """
    if not target_dir.exists():
        return 1

    max_num = 0
    for f in target_dir.glob(f"{date_prefix}_*_*.pdf"):
        parts = f.stem.split("_")
        if len(parts) >= 2:
            try:
                num = int(parts[1])
                max_num = max(max_num, num)
            except ValueError:
                continue

    return max_num + 1


def find_existing_archive(target_dir: Path, ticket_id: str) -> Path | None:
    """
    Check if a ticket has already been archived.

    Looks for files matching *_<ticket_id>.pdf in the target directory.

    Args:
        target_dir: Directory to search.
        ticket_id: The ticket ID.

    Returns:
        Path to existing archive if found, None otherwise.
    """
    if not target_dir.exists():
        return None

    matches = list(target_dir.glob(f"*_{ticket_id}.pdf"))
    return matches[0] if matches else None


def compress_image_to_pdf(
    image_path: Path,
    output_path: Path,
    max_width: int = DEFAULT_MAX_WIDTH,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
) -> tuple[int, int]:
    """
    Compress an image and save it as a single-page PDF.

    Args:
        image_path: Path to the source image.
        output_path: Path to write the PDF page.
        max_width: Maximum width in pixels.
        jpeg_quality: JPEG compression quality (1-100).

    Returns:
        Tuple of (original_size_bytes, compressed_size_bytes).
    """
    original_size = image_path.stat().st_size

    img = Image.open(image_path)

    # Strip EXIF data by converting
    if img.mode == "RGBA":
        # PDF doesn't support alpha, convert to RGB with white background
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Resize if wider than max_width
    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)

    # Save as PDF
    img.save(str(output_path), "PDF", resolution=150, quality=jpeg_quality)

    compressed_size = output_path.stat().st_size

    # If compressed version is larger, use original at reduced resolution
    if compressed_size > original_size:
        img_orig = Image.open(image_path)
        if img_orig.mode == "RGBA":
            background = Image.new("RGB", img_orig.size, (255, 255, 255))
            background.paste(img_orig, mask=img_orig.split()[3])
            img_orig = background
        elif img_orig.mode != "RGB":
            img_orig = img_orig.convert("RGB")
        img_orig.save(str(output_path), "PDF", resolution=72)
        compressed_size = output_path.stat().st_size

    return original_size, compressed_size


def _format_size(size_bytes: int) -> str:
    """Format byte size to human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def _is_image_file(file_path: Path) -> bool:
    """Check if a file is an image (by extension or by trying to open with Pillow)."""
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"}

    if file_path.suffix.lower() in image_extensions:
        return True

    # Extensionless files: try opening with Pillow
    if not file_path.suffix:
        try:
            with Image.open(file_path) as img:
                img.verify()
            return True
        except Exception:
            return False

    return False


def _is_pdf_file(file_path: Path) -> bool:
    """Check if a file is a PDF."""
    if file_path.suffix.lower() == ".pdf":
        return True

    # Check magic bytes for extensionless files
    if not file_path.suffix:
        try:
            with open(file_path, "rb") as f:
                header = f.read(5)
            return header == b"%PDF-"
        except Exception:
            return False

    return False


def _escape_typst(text: str) -> str:
    """Escape special Typst characters in text."""
    # Typst special characters that need escaping
    for char in ["\\", "#", "*", "_", "`", "<", ">", "@", "$", "~"]:
        text = text.replace(char, "\\" + char)
    return text


def infer_label(subject: str | None, default_label: str = "expense") -> str:
    """
    Infer a short filename label from an OSTicket ticket subject.

    Handles patterns like:
        "Support - password reset"  -> "password_reset"
        "Bug report, login issue"   -> "login_issue"
        "Issue: slow loading"       -> "slow_loading"
        "Support"                   -> default_label

    Args:
        subject: Ticket subject string.
        default_label: Fallback label when no specific label can be inferred.

    Returns:
        Lowercase label suitable for filenames.
    """
    if not subject:
        return default_label

    text = subject.strip()

    # Try to split on separators: " - ", ", ", ": "
    # Only use the right part if it looks like a short label (max 3 words)
    for sep in [" - ", ", ", ": "]:
        if sep in text:
            left, right = text.split(sep, 1)
            right_clean = right.strip()
            # Remove trailing date before counting words
            right_no_date = re.sub(r"\s*\d{1,2}\.\d{1,2}\.(\d{2,4})?\s*$", "", right_clean)
            if right_no_date.strip() and len(right_no_date.split()) <= 2:
                text = right_clean
            else:
                # Right side is too long or empty — use left side as label
                text = left.strip()
            break

    # Remove trailing date patterns like "4.1.", "12.1.2026", "4.1.2026"
    text = re.sub(r"\s*\d{1,2}\.\d{1,2}\.(\d{2,4})?\s*$", "", text)

    # Clean up
    text = text.strip().lower()

    # Replace spaces with underscores for filename safety
    text = re.sub(r"\s+", "_", text)

    # Remove characters that aren't safe in filenames
    text = re.sub(r"[^\w\-äöåÄÖÅ]", "", text)

    # Strip leading/trailing underscores and dashes
    text = text.strip("_-")

    return text if text else default_label


def generate_typst_source(
    ticket_data: dict,
    attachments_info: list[dict],
    config: OSTicketConfig,
    strings: dict,
) -> str:
    """
    Generate Typst source for the summary page.

    Args:
        ticket_data: Parsed ticket.json data.
        attachments_info: List of dicts with 'name', 'original_size', 'compressed_size', 'type' keys.
        config: OSTicket configuration (for logo_path and template_path).
        strings: Strings dict with 'pdf' and 'archiver' sections.

    Returns:
        Typst source as string.
    """
    pdf_strings = strings.get("pdf", {})
    archiver_strings = strings.get("archiver", {})

    ticket_id = ticket_data["id"]
    ticket_number = ticket_data.get("number", "")
    user_name = ticket_data["user"]["name"]
    created_str = ticket_data["created"]
    subject = ticket_data.get("subject", "")
    message = ticket_data.get("message", "")

    # Parse date for display
    try:
        created_date = parse_osticket_date(created_str)
        date_display = created_date.strftime("%-d.%-m.%Y")
    except ValueError:
        date_display = created_str

    today_display = date.today().strftime("%-d.%-m.%Y")

    # Escape text for Typst
    subject_esc = _escape_typst(subject)
    user_name_esc = _escape_typst(user_name)
    message_esc = _escape_typst(message)

    # Build attachments list
    att_lines = []
    for i, att in enumerate(attachments_info, 1):
        name = _escape_typst(att["name"])
        orig_size = _format_size(att["original_size"])
        if att["type"] == "image" and att.get("compressed_size") is not None:
            comp_size = _format_size(att["compressed_size"])
            att_lines.append(f"+ {name} ({orig_size} → {comp_size}, {archiver_strings.get('compressed', 'compressed')})")
        elif att["type"] == "pdf":
            att_lines.append(f"+ {name} ({orig_size}, {archiver_strings.get('original', 'original')})")
        else:
            att_lines.append(f"+ {name} ({orig_size})")

    attachments_block = "\n".join(att_lines) if att_lines else pdf_strings.get("no_attachments", "No attachments.")

    # Logo block
    logo_block = ""
    if config.logo_path and config.logo_path.exists():
        logo_filename = config.logo_path.name
        logo_block = f'#image("{logo_filename}", width: 40%)'

    # Title block: if pdf_title is set, show it above "OSTicket #id"; otherwise just "OSTicket #id"
    pdf_title = pdf_strings.get("title", "")
    if pdf_title:
        title_block = (
            f'#text(size: 16pt, weight: "bold")[{pdf_title}]\n'
            f'  #v(0.1cm)\n'
            f'  #text(size: 12pt)[OSTicket \\#{ticket_id}]'
        )
        document_title = f"{pdf_title} - OSTicket #{ticket_id}"
    else:
        title_block = f'#text(size: 16pt, weight: "bold")[OSTicket \\#{ticket_id}]'
        document_title = f"OSTicket #{ticket_id}"

    # Load and fill template
    template_path = config.template_path
    template_text = template_path.read_text(encoding="utf-8")

    tmpl = Template(template_text)
    source = tmpl.safe_substitute(
        document_title=document_title,
        title_block=title_block,
        ticket_id=ticket_id,
        ticket_number=ticket_number,
        logo_block=logo_block,
        subject=subject_esc,
        user_name=user_name_esc,
        date_display=date_display,
        today_display=today_display,
        message=message_esc,
        attachments_block=attachments_block,
        lang=pdf_strings.get("lang", "en"),
        lbl_ticket=pdf_strings.get("ticket", "Ticket"),
        lbl_subject=pdf_strings.get("subject", "Subject"),
        lbl_sender=pdf_strings.get("sender", "Sender"),
        lbl_created=pdf_strings.get("created", "Created"),
        lbl_processed=pdf_strings.get("processed", "Processed"),
        lbl_message=pdf_strings.get("message", "Message"),
        lbl_attachments=pdf_strings.get("attachments", "Attachments"),
    )
    return source


def compile_typst(typst_source: str, output_path: Path, work_dir: Path) -> None:
    """
    Compile Typst source to PDF.

    The .typ file is written into work_dir. Any resources referenced by the
    Typst source (e.g. logo image) must already be present in work_dir.

    Args:
        typst_source: Typst source code.
        output_path: Path for the output PDF.
        work_dir: Directory for the .typ file (and co-located resources).

    Raises:
        RuntimeError: If compilation fails.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    typ_path = work_dir / f"archive_{uuid.uuid4().hex[:8]}.typ"
    typ_path.write_text(typst_source, encoding="utf-8")

    try:
        result = subprocess.run(
            ["typst", "compile", str(typ_path), str(output_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Typst compilation failed:\n{result.stderr}")
    finally:
        typ_path.unlink(missing_ok=True)


def merge_pdfs(pdf_paths: list[Path], output_path: Path) -> int:
    """
    Merge multiple PDFs into one using pikepdf.

    Args:
        pdf_paths: List of PDF file paths to merge (in order).
        output_path: Path for the merged output PDF.

    Returns:
        Total number of pages.
    """
    merged = pikepdf.Pdf.new()
    total_pages = 0

    for pdf_path in pdf_paths:
        src = pikepdf.Pdf.open(pdf_path)
        merged.pages.extend(src.pages)
        total_pages += len(src.pages)

    merged.save(output_path)
    merged.close()

    return total_pages


def generate_receipt_pdf(
    ticket_id: str,
    config: OSTicketConfig,
    strings: dict,
    output_path: Path | None = None,
    force: bool = False,
    max_width: int = DEFAULT_MAX_WIDTH,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
) -> str:
    """
    Generate a PDF receipt from an OSTicket ticket.

    Args:
        ticket_id: The ticket ID.
        config: OSTicket configuration.
        strings: Strings dict with 'pdf' and 'archiver' sections.
        output_path: Explicit output path. If None, generates to
                     inbox_dir/<id>.pdf.
        force: Overwrite existing PDF.
        max_width: Max image width for compression.
        jpeg_quality: JPEG quality for compression.

    Returns:
        Formatted output string describing the result.

    Raises:
        FileNotFoundError: If ticket inbox directory or ticket.json not found.
        RuntimeError: If Typst compilation or PDF merge fails.
    """
    archiver_strings = strings.get("archiver", {})
    inbox_dir = Path(config.inbox_dir) / ticket_id
    ticket_json_path = inbox_dir / "ticket.json"

    if not inbox_dir.exists():
        raise FileNotFoundError(f"{archiver_strings.get('inbox_not_found', 'Ticket inbox directory not found')}: {inbox_dir}")
    if not ticket_json_path.exists():
        raise FileNotFoundError(
            f"ticket.json missing: {ticket_json_path}\n"
            f"Run first: ostickethelper read {ticket_id}"
        )

    # Load ticket metadata
    with open(ticket_json_path, "r", encoding="utf-8") as f:
        ticket_data = json.load(f)

    # Default output: inbox_dir/<id>.pdf
    if output_path is None:
        output_path = Path(config.inbox_dir) / f"{ticket_id}.pdf"

    if output_path.exists() and not force:
        try:
            rel_path = output_path.relative_to(config.work_dir)
        except ValueError:
            rel_path = output_path
        return (
            f"{strings.get('formatter', {}).get('ticket', 'Ticket')} {ticket_id}: "
            f"{archiver_strings.get('already_exists', 'receipt already exists')}: {rel_path}\n"
            f"{archiver_strings.get('use_force', 'Use --force to overwrite.')}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Process attachments
    attachment_names = ticket_data.get("attachments", [])
    attachments_info = []
    page_descriptions = []

    # Use temp directory from config
    work_dir = config.temp_dir / f"receipt_{ticket_id}_{uuid.uuid4().hex[:8]}"
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        attachment_pdfs = []

        for att_name in attachment_names:
            att_path = inbox_dir / att_name
            if not att_path.exists():
                continue

            if _is_pdf_file(att_path):
                # PDF attachment — use as-is
                original_size = att_path.stat().st_size
                attachments_info.append({
                    "name": att_name,
                    "original_size": original_size,
                    "compressed_size": None,
                    "type": "pdf",
                })

                # Count pages
                src_pdf = pikepdf.Pdf.open(att_path)
                num_pages = len(src_pdf.pages)
                src_pdf.close()

                attachment_pdfs.append(att_path)
                page_descriptions.append(
                    f"  {att_name} ({_format_size(original_size)}, "
                    f"{archiver_strings.get('original', 'original')}, {num_pages} p.)"
                )

            elif _is_image_file(att_path):
                # Image — compress and convert to PDF page
                img_pdf_path = work_dir / f"{att_name}.pdf"
                original_size, compressed_size = compress_image_to_pdf(
                    att_path, img_pdf_path, max_width, jpeg_quality
                )
                attachments_info.append({
                    "name": att_name,
                    "original_size": original_size,
                    "compressed_size": compressed_size,
                    "type": "image",
                })
                attachment_pdfs.append(img_pdf_path)
                page_descriptions.append(
                    f"  {att_name} ({_format_size(original_size)} → "
                    f"{_format_size(compressed_size)}, {archiver_strings.get('compressed', 'compressed')})"
                )
            else:
                # Unknown file type — skip
                continue

        # Copy logo to work_dir so Typst snap can access it
        if config.logo_path and config.logo_path.exists():
            shutil.copy2(config.logo_path, work_dir / config.logo_path.name)

        # Generate Typst summary page
        typst_source = generate_typst_source(
            ticket_data, attachments_info, config, strings
        )
        summary_pdf_path = work_dir / "summary.pdf"
        compile_typst(typst_source, summary_pdf_path, work_dir)

        # Merge: summary + attachments
        all_pdfs = [summary_pdf_path] + attachment_pdfs
        total_pages = merge_pdfs(all_pdfs, output_path)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    # Build output
    output_size = output_path.stat().st_size
    try:
        rel_path = output_path.relative_to(config.work_dir)
    except ValueError:
        rel_path = output_path

    try:
        inbox_rel = Path(config.inbox_dir).relative_to(config.work_dir)
    except ValueError:
        inbox_rel = Path(config.inbox_dir)

    lines = [
        f"{strings.get('formatter', {}).get('ticket', 'Ticket')} {ticket_id}",
        f"  {archiver_strings.get('source', 'Source')}:   {inbox_rel}/{ticket_id}/",
        f"  {archiver_strings.get('target', 'Target')}:   {rel_path}",
        f"  {archiver_strings.get('pages', 'Pages')}:   {total_pages} ({_format_size(output_size)})",
        f"    1    {archiver_strings.get('summary', 'Summary (Typst)')}",
    ]

    # Add page descriptions
    page_num = 2
    for desc in page_descriptions:
        lines.append(f"    {page_num}   {desc.strip()}")
        page_num += 1

    return "\n".join(lines)
