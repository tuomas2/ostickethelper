"""Tests for the OSTicket archiver module."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from conftest import make_config
from ostickethelper.archiver import (
    parse_osticket_date,
    next_sequential_number,
    find_existing_archive,
    compress_image_to_pdf,
    generate_typst_source,
    merge_pdfs,
    generate_receipt_pdf,
    infer_label,
    _format_size,
    _is_image_file,
    _is_pdf_file,
    _escape_typst,
)


class TestParseOsticketDate:
    def test_basic_pm(self):
        assert parse_osticket_date("1/3/26 9:20 PM") == date(2026, 1, 3)

    def test_basic_am(self):
        assert parse_osticket_date("11/29/25 9:05 PM") == date(2025, 11, 29)

    def test_with_leading_spaces(self):
        assert parse_osticket_date("  1/3/26 9:20 PM  ") == date(2026, 1, 3)

    def test_noon(self):
        assert parse_osticket_date("12/15/25 12:00 PM") == date(2025, 12, 15)

    def test_midnight(self):
        assert parse_osticket_date("6/1/26 12:30 AM") == date(2026, 6, 1)

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            parse_osticket_date("2026-01-03 21:20")


class TestNextSequentialNumber:
    def test_empty_directory(self, tmp_path):
        assert next_sequential_number(tmp_path, "20260103") == 1

    def test_nonexistent_directory(self, tmp_path):
        assert next_sequential_number(tmp_path / "nonexistent", "20260103") == 1

    def test_with_existing_files(self, tmp_path):
        (tmp_path / "20260103_01_rent.pdf").touch()
        (tmp_path / "20260103_02_catering_339.pdf").touch()
        assert next_sequential_number(tmp_path, "20260103") == 3

    def test_different_date(self, tmp_path):
        (tmp_path / "20260103_01_rent.pdf").touch()
        assert next_sequential_number(tmp_path, "20260104") == 1

    def test_non_numeric_parts(self, tmp_path):
        (tmp_path / "20260103_xx_test.pdf").touch()
        assert next_sequential_number(tmp_path, "20260103") == 1


class TestFindExistingArchive:
    def test_no_existing(self, tmp_path):
        assert find_existing_archive(tmp_path, "339") is None

    def test_nonexistent_directory(self, tmp_path):
        assert find_existing_archive(tmp_path / "nonexistent", "339") is None

    def test_found(self, tmp_path):
        archive_file = tmp_path / "20260103_01_catering_339.pdf"
        archive_file.touch()
        result = find_existing_archive(tmp_path, "339")
        assert result == archive_file

    def test_different_ticket(self, tmp_path):
        (tmp_path / "20260103_01_catering_330.pdf").touch()
        assert find_existing_archive(tmp_path, "339") is None


class TestFormatSize:
    def test_bytes(self):
        assert _format_size(500) == "500 B"

    def test_kilobytes(self):
        assert _format_size(5120) == "5 KB"

    def test_megabytes(self):
        assert _format_size(5 * 1024 * 1024) == "5.0 MB"


class TestEscapeTypst:
    def test_hash(self):
        assert _escape_typst("test #339") == "test \\#339"

    def test_asterisk(self):
        assert _escape_typst("*bold*") == "\\*bold\\*"

    def test_plain_text(self):
        assert _escape_typst("hello world") == "hello world"

    def test_euro_sign(self):
        assert _escape_typst("29.59€") == "29.59€"

    def test_dollar(self):
        assert _escape_typst("$100") == "\\$100"


class TestIsImageFile:
    def test_jpg(self, tmp_path):
        f = tmp_path / "test.jpg"
        f.touch()
        assert _is_image_file(f) is True

    def test_png(self, tmp_path):
        f = tmp_path / "test.png"
        f.touch()
        assert _is_image_file(f) is True

    def test_pdf(self, tmp_path):
        f = tmp_path / "test.pdf"
        f.touch()
        assert _is_image_file(f) is False

    def test_extensionless_not_image(self, tmp_path):
        f = tmp_path / "image"
        f.write_text("not an image")
        assert _is_image_file(f) is False


class TestIsPdfFile:
    def test_pdf_extension(self, tmp_path):
        f = tmp_path / "test.pdf"
        f.touch()
        assert _is_pdf_file(f) is True

    def test_jpg_extension(self, tmp_path):
        f = tmp_path / "test.jpg"
        f.touch()
        assert _is_pdf_file(f) is False

    def test_extensionless_pdf(self, tmp_path):
        f = tmp_path / "document"
        f.write_bytes(b"%PDF-1.4 content")
        assert _is_pdf_file(f) is True

    def test_extensionless_not_pdf(self, tmp_path):
        f = tmp_path / "document"
        f.write_bytes(b"\x89PNG content")
        assert _is_pdf_file(f) is False


class TestCompressImageToPdf:
    def test_basic_compression(self, tmp_path):
        from PIL import Image

        # Create a test image (large enough to trigger resize)
        img = Image.new("RGB", (1600, 1200), color="red")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, "JPEG")

        out_path = tmp_path / "output.pdf"
        orig, comp = compress_image_to_pdf(img_path, out_path, max_width=800)

        assert orig > 0
        assert comp > 0
        assert out_path.exists()

    def test_small_image_no_resize(self, tmp_path):
        from PIL import Image

        img = Image.new("RGB", (400, 300), color="blue")
        img_path = tmp_path / "small.jpg"
        img.save(img_path, "JPEG")

        out_path = tmp_path / "output.pdf"
        orig, comp = compress_image_to_pdf(img_path, out_path, max_width=800)

        assert out_path.exists()

    def test_rgba_image(self, tmp_path):
        from PIL import Image

        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        img_path = tmp_path / "transparent.png"
        img.save(img_path, "PNG")

        out_path = tmp_path / "output.pdf"
        orig, comp = compress_image_to_pdf(img_path, out_path)

        assert out_path.exists()


class TestGenerateTypstSource:
    def test_basic_output(self, tmp_path, default_strings):
        config = make_config(tmp_path, logo=True)
        ticket_data = {
            "id": "339",
            "number": "656694",
            "subject": "Catering Jan 4",
            "user": {"name": "John Smith", "email": "test@test.com"},
            "created": "1/3/26 9:20 PM",
            "message": "Test message 29.59€",
        }
        attachments_info = [
            {"name": "receipt.pdf", "original_size": 114000, "compressed_size": None, "type": "pdf"},
            {"name": "photo.jpg", "original_size": 5000000, "compressed_size": 87000, "type": "image"},
        ]

        source = generate_typst_source(ticket_data, attachments_info, config, default_strings)

        assert "OSTicket" in source
        assert "339" in source
        assert "656694" in source
        assert "John Smith" in source
        assert "receipt.pdf" in source
        assert "photo.jpg" in source
        assert "compressed" in source
        assert "original" in source

    def test_escaping(self, tmp_path, default_strings):
        config = make_config(tmp_path)
        ticket_data = {
            "id": "339",
            "number": "656694",
            "subject": "Test #special *chars*",
            "user": {"name": "Test User", "email": "test@test.com"},
            "created": "1/3/26 9:20 PM",
            "message": "Price: $100",
        }

        source = generate_typst_source(ticket_data, [], config, default_strings)

        assert "\\#special" in source
        assert "\\*chars\\*" in source
        assert "\\$100" in source

    def test_no_logo(self, tmp_path, default_strings):
        config = make_config(tmp_path, logo=False)
        ticket_data = {
            "id": "1",
            "number": "100",
            "subject": "Test",
            "user": {"name": "User", "email": "u@test.com"},
            "created": "1/3/26 9:20 PM",
            "message": "Msg",
        }
        source = generate_typst_source(ticket_data, [], config, default_strings)
        assert "#image" not in source


class TestMergePdfs:
    def test_merge_two_pdfs(self, tmp_path):
        import pikepdf

        # Create two simple PDFs
        for i in range(2):
            pdf = pikepdf.Pdf.new()
            pdf.add_blank_page()
            pdf.save(tmp_path / f"page{i}.pdf")

        output = tmp_path / "merged.pdf"
        total = merge_pdfs(
            [tmp_path / "page0.pdf", tmp_path / "page1.pdf"],
            output,
        )

        assert total == 2
        assert output.exists()

        result = pikepdf.Pdf.open(output)
        assert len(result.pages) == 2

    def test_merge_single_pdf(self, tmp_path):
        import pikepdf

        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page()
        pdf.add_blank_page()
        pdf.save(tmp_path / "multi.pdf")

        output = tmp_path / "merged.pdf"
        total = merge_pdfs([tmp_path / "multi.pdf"], output)

        assert total == 2


class TestInferLabel:
    def test_dash_separator(self):
        assert infer_label("Expense claim - catering") == "catering"

    def test_comma_separator(self):
        assert infer_label("Expense claim, catering 4.1.") == "catering"

    def test_colon_separator(self):
        assert infer_label("Expense claim: travel") == "travel"

    def test_no_separator(self):
        assert infer_label("Catering") == "catering"

    def test_just_prefix(self):
        assert infer_label("Support", default_label="support") == "support"

    def test_empty_subject(self):
        assert infer_label("", default_label="ticket") == "ticket"

    def test_none_subject(self):
        assert infer_label(None, default_label="ticket") == "ticket"

    def test_with_trailing_date(self):
        assert infer_label("Expense claim - catering 4.1.") == "catering"

    def test_with_trailing_full_date(self):
        assert infer_label("Expense claim - catering 12.1.2026") == "catering"

    def test_supplies(self):
        assert infer_label("Expense claim - supplies") == "supplies"

    def test_multiple_words(self):
        assert infer_label("Expense claim - team building") == "team_building"

    def test_invoice(self):
        assert infer_label("Invoice - rent") == "rent"

    def test_long_text_after_comma(self):
        assert infer_label("Invoice, due date is 24.12.2025", default_label="invoice") == "invoice"

    def test_whitespace_only_after_separator(self):
        assert infer_label("Support - ", default_label="support") == "support"

    def test_default_label_used(self):
        assert infer_label("", default_label="custom") == "custom"
        assert infer_label(None, default_label="claim") == "claim"


class TestGenerateReceiptPdf:
    def test_missing_inbox(self, tmp_path, default_strings):
        config = make_config(tmp_path)
        with pytest.raises(FileNotFoundError, match="not found"):
            generate_receipt_pdf("999", config, default_strings)

    def test_missing_ticket_json(self, tmp_path, default_strings):
        config = make_config(tmp_path)
        inbox = tmp_path / "inbox" / "339"
        inbox.mkdir(parents=True)

        with pytest.raises(FileNotFoundError, match="ticket.json"):
            generate_receipt_pdf("339", config, default_strings)

    def test_already_exists(self, tmp_path, default_strings):
        config = make_config(tmp_path)
        # Set up inbox with ticket data and existing PDF
        inbox = tmp_path / "inbox" / "339"
        inbox.mkdir(parents=True)
        ticket_data = {
            "id": "339",
            "number": "656694",
            "subject": "Test",
            "user": {"name": "Test", "email": "test@test.com"},
            "created": "1/3/26 9:20 PM",
            "status": "Open",
            "message": "Test",
            "attachments": [],
        }
        (inbox / "ticket.json").write_text(json.dumps(ticket_data))

        # Create existing inbox PDF
        inbox_pdf = tmp_path / "inbox" / "339.pdf"
        inbox_pdf.touch()

        result = generate_receipt_pdf("339", config, default_strings)

        assert "already exists" in result
        assert "--force" in result
