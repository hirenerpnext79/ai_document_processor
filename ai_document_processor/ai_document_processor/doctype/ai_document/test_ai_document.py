import datetime
import io
import unittest
import openpyxl
from PIL import Image
from ai_document_processor.file import (
    parse_ai_json_response,
    parse_extracted_date,
    parse_pdf_date_property,
    extract_excel_doc_property_date,
    extract_image_doc_property_date,
    extract_actual_doc_created_date,
    resolve_doc_datetime,
    apply_ai_metadata_to_file,
    normalize_ai_metadata,
)
import frappe


class TestAIDocument(unittest.TestCase):
    def test_parse_ai_json_response_with_codeblock(self):
        sample = '```json\n{"title": "Test Title", "summary": "Test Summary", "tags": ["a", "b"]}\n```'
        result = parse_ai_json_response(sample)
        self.assertEqual(result.get("title"), "Test Title")
        self.assertEqual(result.get("summary"), "Test Summary")
        self.assertEqual(result.get("tags"), ["a", "b"])

    def test_parse_ai_json_response_raw(self):
        sample = '{"title": "Raw Title", "summary": "Raw Summary"}'
        result = parse_ai_json_response(sample)
        self.assertEqual(result.get("title"), "Raw Title")

    def test_normalize_ai_metadata_custom_prompt_keys(self):
        sample = {
            "Doc Title": "Invoice Title",
            "Doc Short Summary": "Detailed summary",
            "Doc Tags": ["Tag1", "Tag2"],
            "Doc Date/Time": "2026-09-30T00:00:00"
        }
        result = normalize_ai_metadata(sample)
        self.assertEqual(result.get("title"), "Invoice Title")
        self.assertEqual(result.get("summary"), "Detailed summary")
        self.assertEqual(result.get("tags"), ["Tag1", "Tag2"])
        self.assertEqual(result.get("date"), "2026-09-30T00:00:00")

    def test_normalize_ai_metadata_snake_case(self):
        sample = {
            "doc_title": "Snake Title",
            "doc_short_summary": "Snake summary",
            "doc_tags": "TagA, TagB",
            "doc_date_time": "2026-10-01"
        }
        result = normalize_ai_metadata(sample)
        self.assertEqual(result.get("title"), "Snake Title")
        self.assertEqual(result.get("summary"), "Snake summary")
        self.assertEqual(result.get("tags"), ["TagA", "TagB"])
        self.assertEqual(result.get("date"), "2026-10-01")

    def test_parse_pdf_date_property(self):
        pdf_date_str = "D:20260929142943+05'30'"
        dt = parse_pdf_date_property(pdf_date_str)
        self.assertEqual(dt, datetime.datetime(2026, 9, 29, 14, 29, 43))

    def test_extract_excel_doc_property_date(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["A", "B"])
        expected_dt = datetime.datetime(2025, 6, 15, 11, 20, 0)
        wb.properties.created = expected_dt
        bio = io.BytesIO()
        wb.save(bio)
        extracted = extract_excel_doc_property_date(bio.getvalue())
        self.assertEqual(extracted, expected_dt)

    def test_extract_image_doc_property_date(self):
        img = Image.new("RGB", (50, 50), color="red")
        exif = img.getexif()
        exif[36867] = "2024:11:10 08:30:00"
        bio = io.BytesIO()
        img.save(bio, format="JPEG", exif=exif)
        extracted = extract_image_doc_property_date(bio.getvalue())
        self.assertEqual(str(extracted), "2024-11-10 08:30:00")

    def test_resolve_doc_datetime_priority(self):
        wb = openpyxl.Workbook()
        prop_dt = datetime.datetime(2025, 1, 1, 10, 0, 0)
        wb.properties.created = prop_dt
        bio = io.BytesIO()
        wb.save(bio)

        resolved_with_prop = resolve_doc_datetime("sheet.xlsx", ai_date_str="2026-05-01", content=bio.getvalue())
        self.assertEqual(resolved_with_prop, prop_dt)

        resolved_without_prop = resolve_doc_datetime("text.txt", ai_date_str="2026-05-01 12:00:00", content=b"plain")
        self.assertEqual(str(resolved_without_prop), "2026-05-01 12:00:00")

    def test_apply_ai_metadata_to_file(self):
        fake_file = frappe._dict(
            file_url="/files/fake.txt",
            creation=datetime.datetime(2026, 1, 1),
            is_processed_with_ai=0,
            doc_title="",
            doc_short_summary="",
            doc_tags="",
            doc_datetime=None
        )
        metadata = {
            "title": "Invoice Doc",
            "summary": "Short summary",
            "tags": ["Finance", "Tax"],
            "date": "2026-07-20 10:00:00"
        }
        apply_ai_metadata_to_file(fake_file, metadata, file_url="/files/fake.txt")
        self.assertEqual(fake_file.doc_title, "Invoice Doc")
        self.assertEqual(fake_file.doc_short_summary, "Short summary")
        self.assertEqual(fake_file.doc_tags, "Finance, Tax")
        self.assertEqual(fake_file.is_processed_with_ai, 1)
        self.assertEqual(str(fake_file.doc_datetime), "2026-07-20 10:00:00")
