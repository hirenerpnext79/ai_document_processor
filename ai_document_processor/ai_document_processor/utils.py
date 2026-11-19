import csv
import io
import os
import re
import zipfile
import xml.etree.ElementTree as ET
import requests
import frappe
from frappe import _

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif", ".jfif", ".gif")
EXCEL_EXTENSIONS = (".xlsx", ".xls", ".xlsm", ".csv")
WORD_EXTENSIONS = (".docx", ".doc", ".rtf")
PPT_EXTENSIONS = (".pptx",)
TEXT_EXTENSIONS = (".txt", ".md", ".json", ".xml", ".log")

GOOGLE_WORKSPACE_EXPORTS = {
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
}

MIME_TO_EXTENSION = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel.sheet.macroenabled.12": ".xlsm",
    "application/vnd.ms-excel": ".xls",
    "text/csv": ".csv",
    "application/csv": ".csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/msword": ".doc",
    "application/rtf": ".rtf",
    "text/rtf": ".rtf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "text/plain": ".txt",
    "application/json": ".json",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/gif": ".gif",
}


def get_file_extension(file_url):
    if not file_url:
        return ""
    clean_url = str(file_url).split("?")[0].split("#")[0]
    return os.path.splitext(clean_url)[1].lower()


def is_google_drive_url(url):
    if not url or not isinstance(url, str):
        return False
    return "drive.google.com" in url or "docs.google.com" in url


def extract_google_drive_id(url):
    if not url:
        return None
    clean_url = str(url).strip()
    if "/d/" in clean_url:
        return clean_url.split("/d/")[1].split("/")[0].split("?")[0].split("#")[0]
    if "id=" in clean_url:
        return clean_url.split("id=")[1].split("&")[0].split("#")[0]
    return None


def parse_content_disposition_filename(header_val):
    if not header_val:
        return ""
    utf8_match = re.search(r"filename\*\s*=\s*UTF-8''([^;]+)", header_val, re.IGNORECASE)
    if utf8_match:
        return requests.utils.unquote(utf8_match.group(1)).strip().strip('"')
    match = re.search(r'filename\s*=\s*"?([^";]+)"?', header_val, re.IGNORECASE)
    if match:
        return match.group(1).strip().strip('"')
    return ""


def get_google_drive_auth_headers():
    headers = {}
    try:
        gd = frappe.get_doc("Google Drive")
        token = gd.get_access_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    except Exception:
        pass
    return headers


def fetch_google_drive_metadata(file_id, headers):
    if not file_id or not headers:
        return {}
    try:
        meta_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?fields=name,mimeType,createdTime,modifiedTime"
        response = requests.get(meta_url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.json() or {}
    except Exception as e:
        frappe.log_error(title="Google Drive Metadata Error", message=str(e))
    return {}


def get_google_docs_public_export_url(url, file_id):
    lower_url = str(url).lower()
    if "docs.google.com/spreadsheets/" in lower_url:
        return f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx", ".xlsx"
    if "docs.google.com/document/" in lower_url:
        return f"https://docs.google.com/document/d/{file_id}/export?format=docx", ".docx"
    if "docs.google.com/presentation/" in lower_url:
        return f"https://docs.google.com/presentation/d/{file_id}/export/pptx", ".pptx"
    return None, ""


def is_html_response(response):
    content_type = (response.headers.get("Content-Type") or "").lower()
    if content_type.startswith("text/html"):
        return True
    sample = (response.content or b"")[:256].lstrip().lower()
    return sample.startswith((b"<!doctype html", b"<html"))


def download_google_drive_file_with_meta(url):
    file_id = extract_google_drive_id(url)
    if not file_id:
        return None, {}

    headers = get_google_drive_auth_headers()
    meta = fetch_google_drive_metadata(file_id, headers)
    mime_type = (meta.get("mimeType") or "").strip()
    file_meta = {
        "file_name": meta.get("name") or "",
        "content_type": mime_type,
        "created_time": meta.get("createdTime"),
        "modified_time": meta.get("modifiedTime"),
    }

    if mime_type in GOOGLE_WORKSPACE_EXPORTS:
        export_mime, export_ext = GOOGLE_WORKSPACE_EXPORTS[mime_type]
        try:
            export_url = f"https://www.googleapis.com/drive/v3/files/{file_id}/export?mimeType={export_mime}"
            response = requests.get(export_url, headers=headers, timeout=30)
            if response.status_code == 200 and not is_html_response(response):
                file_meta["content_type"] = export_mime
                if file_meta["file_name"] and not get_file_extension(file_meta["file_name"]):
                    file_meta["file_name"] = f"{file_meta['file_name']}{export_ext}"
                return response.content, file_meta
        except Exception as e:
            frappe.log_error(title="Google Drive Export Error", message=str(e))

    if headers:
        try:
            api_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
            response = requests.get(api_url, headers=headers, timeout=30)
            if response.status_code == 200 and not is_html_response(response):
                if not file_meta["content_type"]:
                    file_meta["content_type"] = (response.headers.get("Content-Type") or "").split(";")[0].strip()
                if not file_meta["file_name"]:
                    file_meta["file_name"] = parse_content_disposition_filename(response.headers.get("Content-Disposition"))
                return response.content, file_meta
        except Exception as e:
            frappe.log_error(title="Google Drive Download Error", message=str(e))

    public_export_url, export_ext = get_google_docs_public_export_url(url, file_id)
    if public_export_url:
        try:
            response = requests.get(public_export_url, timeout=30)
            if response.status_code == 200 and not is_html_response(response):
                file_meta["content_type"] = (response.headers.get("Content-Type") or "").split(";")[0].strip()
                file_meta["file_name"] = (
                    file_meta["file_name"]
                    or parse_content_disposition_filename(response.headers.get("Content-Disposition"))
                    or f"google_file{export_ext}"
                )
                return response.content, file_meta
        except Exception as e:
            frappe.log_error(title="Google Docs Export Fallback Error", message=str(e))

    for fallback_url in (
        f"https://drive.google.com/uc?export=download&id={file_id}",
        f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t",
    ):
        try:
            response = requests.get(fallback_url, timeout=30)
            if response.status_code == 200 and not is_html_response(response):
                file_meta["content_type"] = (
                    file_meta["content_type"]
                    or (response.headers.get("Content-Type") or "").split(";")[0].strip()
                )
                file_meta["file_name"] = (
                    file_meta["file_name"]
                    or parse_content_disposition_filename(response.headers.get("Content-Disposition"))
                )
                return response.content, file_meta
        except Exception as e:
            frappe.log_error(title="Google Drive Fallback Error", message=str(e))

    return None, file_meta


def download_google_drive_file(url):
    content, _ = download_google_drive_file_with_meta(url)
    return content


def get_file_content_with_meta(file_url):
    if not file_url:
        return None, {}

    try:
        if is_google_drive_url(file_url):
            return download_google_drive_file_with_meta(file_url)

        if str(file_url).startswith(("http://", "https://")):
            response = requests.get(file_url, timeout=30)
            if response.status_code == 200:
                meta = {
                    "content_type": (response.headers.get("Content-Type") or "").split(";")[0].strip(),
                    "file_name": parse_content_disposition_filename(response.headers.get("Content-Disposition")),
                }
                return response.content, meta

        file_doc = None
        if frappe.db.exists("File", {"file_url": file_url}):
            file_doc = frappe.get_doc("File", {"file_url": file_url})
        elif frappe.db.exists("File", file_url):
            file_doc = frappe.get_doc("File", file_url)

        if file_doc:
            try:
                full_path = file_doc.get_full_path()
                if full_path and os.path.exists(full_path) and os.path.isfile(full_path):
                    with open(full_path, "rb") as f:
                        return f.read(), {"file_name": file_doc.file_name or ""}
            except Exception:
                pass
            content = file_doc.get_content()
            if content:
                if isinstance(content, str):
                    content = content.encode("utf-8", errors="surrogateescape")
                return content, {"file_name": file_doc.file_name or ""}

        clean_path = str(file_url).lstrip("/")
        for prefix in ("public", "private", ""):
            path = frappe.get_site_path(prefix, clean_path) if prefix else frappe.get_site_path(clean_path)
            if os.path.exists(path) and os.path.isfile(path):
                with open(path, "rb") as f:
                    return f.read(), {"file_name": os.path.basename(path)}
    except Exception as e:
        frappe.log_error(title="Get File Content Error", message=str(e))

    return None, {}


def get_file_content(file_url):
    content, _ = get_file_content_with_meta(file_url)
    return content


def is_xlsx_content(content):
    if not (isinstance(content, (bytes, bytearray)) and content.startswith((b"PK\x03\x04", b"PK\x05\x06"))):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            return any(name.startswith("xl/") for name in zf.namelist())
    except Exception:
        return False


def is_xls_content(content):
    return isinstance(content, (bytes, bytearray)) and content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")


def detect_extension_from_bytes(content):
    if not isinstance(content, (bytes, bytearray)) or not content:
        return ""

    if content.lstrip().startswith(b"%PDF-"):
        return ".pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if content.startswith(b"BM"):
        return ".bmp"
    if content.startswith((b"II*\x00", b"MM\x00*")):
        return ".tiff"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ".webp"
    if content.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                names = zf.namelist()
                if any(name.startswith("xl/") for name in names):
                    return ".xlsx"
                if any(name.startswith("word/") for name in names):
                    return ".docx"
                if any(name.startswith("ppt/") for name in names):
                    return ".pptx"
        except Exception:
            pass
    if is_xls_content(content):
        return ".xls"
    if content.lstrip().startswith(b"{\\rtf"):
        return ".rtf"
    return ""


def detect_file_extension(file_url=None, content=None, file_name=None, content_type=None):
    byte_ext = detect_extension_from_bytes(content)
    if byte_ext:
        return byte_ext

    for candidate in (file_name, file_url):
        ext = get_file_extension(candidate)
        if ext:
            return ext

    if content_type:
        clean_mime = str(content_type).split(";")[0].strip().lower()
        if clean_mime in MIME_TO_EXTENSION:
            return MIME_TO_EXTENSION[clean_mime]

    if isinstance(content, (bytes, bytearray)) and content and b"\x00" not in content[:4096]:
        return ".txt"

    return ""


def resolve_document_type_from_ext(ext):
    if ext == ".pdf":
        return "PDF"
    if ext in IMAGE_EXTENSIONS:
        return "Image"
    if ext in EXCEL_EXTENSIONS:
        return "Excel"
    if ext in WORD_EXTENSIONS:
        return "Word"
    if ext in PPT_EXTENSIONS:
        return "Presentation"
    if ext in TEXT_EXTENSIONS:
        return "Text"
    return "PDF"


def extract_pdf_page_ocr(page):
    try:
        from PIL import Image
        import pytesseract

        pix = page.get_pixmap(dpi=150)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return pytesseract.image_to_string(img)
    except Exception as e:
        frappe.log_error(title="PDF Page OCR Error", message=str(e))
        return ""


def extract_pdf_text(file_url, content=None):
    content = content if content is not None else get_file_content(file_url)
    if not content:
        frappe.throw(_("File not found or empty: {0}").format(file_url))

    if isinstance(content, str):
        content = content.encode("utf-8", errors="surrogateescape")

    try:
        import fitz
    except ImportError as e:
        frappe.log_error(title="PyMuPDF Import Failed", message=str(e))
        frappe.throw(_("No PDF extraction library is installed. Please run 'pip install pymupdf' in your bench environment."))

    try:
        doc = fitz.open(stream=content, filetype="pdf")
        text = ""
        for page in doc:
            page_text = page.get_text()
            if not page_text or not page_text.strip():
                page_text = extract_pdf_page_ocr(page)
            text += (page_text or "") + "\n"

        extracted_text = text.strip()
        if not extracted_text:
            frappe.throw(_("No readable text could be extracted from the PDF."))
        return extracted_text
    except frappe.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(title="PyMuPDF Extraction Failed", message=str(e))
        frappe.throw(_("Failed to extract text from PDF: {0}").format(str(e)))


def extract_image_text(file_url, content=None):
    content = content if content is not None else get_file_content(file_url)
    if not content:
        frappe.throw(_("File not found or empty: {0}").format(file_url))

    if isinstance(content, str):
        content = content.encode("utf-8", errors="surrogateescape")

    try:
        from PIL import Image
        import pytesseract
    except ImportError as e:
        frappe.log_error(title="OCR Libraries Missing", message=str(e))
        frappe.throw(_("OCR libraries (pytesseract or Pillow) are not installed. Please install them."))

    try:
        image = Image.open(io.BytesIO(content))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        text = pytesseract.image_to_string(image)
        extracted_text = (text or "").strip()
        if not extracted_text:
            frappe.throw(_("No readable text could be extracted from the uploaded image."))
        return extracted_text
    except frappe.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(title="Image OCR Extraction Failed", message=str(e))
        frappe.throw(_("Failed to extract text from Image: {0}").format(str(e)))


def format_sheets_as_text(sheets_data):
    output_lines = []
    for sheet_name, rows in sheets_data:
        output_lines.append(f"=== Sheet: {sheet_name} ===")
        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf, lineterminator="\n")
        for r in rows:
            writer.writerow(r)
        output_lines.append(csv_buf.getvalue().strip())
        output_lines.append("")
    return "\n".join(output_lines).strip()


def read_xlsx_sheets(content, data_only=True):
    import openpyxl

    wb = openpyxl.load_workbook(filename=io.BytesIO(content), data_only=data_only, read_only=True)
    try:
        sheets_data = []
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            rows = []
            for row in sheet.iter_rows(values_only=True):
                if row and any(c is not None and str(c).strip() != "" for c in row):
                    rows.append([str(c).strip() if c is not None else "" for c in row])
            if rows:
                sheets_data.append((sheet_name, rows))
        return sheets_data
    finally:
        wb.close()


def decode_text_bytes(content):
    if isinstance(content, str):
        return content
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1", errors="replace")


def extract_csv_text(content):
    if is_xlsx_content(content) or is_xls_content(content):
        frappe.throw(_("Binary Excel file cannot be parsed as CSV."))

    try:
        decoded = decode_text_bytes(content)
        reader = csv.reader(io.StringIO(decoded))
        rows = []
        for row in reader:
            if row and any(c is not None and str(c).strip() != "" for c in row):
                rows.append([str(c).strip() if c is not None else "" for c in row])

        if not rows:
            frappe.throw(_("CSV file is empty or contains no readable data."))

        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        for r in rows:
            writer.writerow(r)
        return output.getvalue().strip()
    except frappe.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(title="CSV Extraction Failed", message=str(e))
        frappe.throw(_("Failed to extract data from CSV: {0}").format(str(e)))


def extract_xlsx_text(content):
    try:
        import openpyxl  # noqa: F401
    except ImportError as e:
        frappe.log_error(title="openpyxl Missing", message=str(e))
        frappe.throw(_("openpyxl library is not installed. Please run 'pip install openpyxl'."))

    try:
        sheets_data = read_xlsx_sheets(content, data_only=True)
        if not sheets_data:
            sheets_data = read_xlsx_sheets(content, data_only=False)

        if not sheets_data:
            frappe.throw(_("Excel file contains no readable data."))

        return format_sheets_as_text(sheets_data)
    except frappe.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(title="Excel XLSX Extraction Failed", message=str(e))
        frappe.throw(_("Failed to extract data from Excel file: {0}").format(str(e)))


def extract_xls_text(content):
    try:
        import xlrd
    except ImportError as e:
        frappe.log_error(title="xlrd Missing", message=str(e))
        frappe.throw(_("xlrd library is not installed. Please run 'pip install xlrd'."))

    try:
        wb = xlrd.open_workbook(file_contents=content)
        sheets_data = []
        for sheet in wb.sheets():
            rows = []
            for row_idx in range(sheet.nrows):
                row = sheet.row_values(row_idx)
                if row and any(c is not None and str(c).strip() != "" for c in row):
                    rows.append([str(c).strip() if c is not None else "" for c in row])
            if rows:
                sheets_data.append((sheet.name, rows))

        if not sheets_data:
            frappe.throw(_("Excel file contains no readable data."))

        return format_sheets_as_text(sheets_data)
    except frappe.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(title="Excel XLS Extraction Failed", message=str(e))
        frappe.throw(_("Failed to extract data from XLS file: {0}").format(str(e)))


def extract_excel_text(file_url, content=None, ext=None):
    content = content if content is not None else get_file_content(file_url)
    if not content:
        frappe.throw(_("File not found or empty: {0}").format(file_url))

    if is_xlsx_content(content):
        return extract_xlsx_text(content)
    if is_xls_content(content):
        return extract_xls_text(content)

    resolved_ext = ext or get_file_extension(file_url)
    if resolved_ext == ".csv":
        return extract_csv_text(content)
    if resolved_ext == ".xls":
        return extract_xls_text(content)
    if resolved_ext in (".xlsx", ".xlsm"):
        return extract_xlsx_text(content)

    return extract_csv_text(content)


def extract_docx_text(content):
    try:
        lines = []
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            if "word/document.xml" not in zf.namelist():
                frappe.throw(_("Invalid Word document structure."))
            root = ET.fromstring(zf.read("word/document.xml"))
            for para in root.iter():
                if para.tag.endswith("}p") or para.tag == "p":
                    texts = [
                        node.text for node in para.iter()
                        if (node.tag.endswith("}t") or node.tag == "t") and node.text
                    ]
                    line = "".join(texts).strip()
                    if line:
                        lines.append(line)
        extracted = "\n".join(lines).strip()
        if not extracted:
            frappe.throw(_("No readable text could be extracted from the Word document."))
        return extracted
    except frappe.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(title="Word DOCX Extraction Failed", message=str(e))
        frappe.throw(_("Failed to extract text from Word document: {0}").format(str(e)))


def extract_rtf_text(raw_bytes):
    try:
        if isinstance(raw_bytes, bytes):
            rtf_text = raw_bytes.decode("latin-1", errors="replace")
        else:
            rtf_text = str(raw_bytes)

        pattern = re.compile(r"\\([a-z]{1,32})(-?\d+)? ?|\\\'([0-9a-f]{2})|\\([^a-z])|([{}])|[\r\n]+|(.)", re.I)
        destinations_to_skip = {
            "fonttbl", "colortbl", "stylesheet", "info", "pict", "header", "footer",
            "themedata", "colorscheme", "datastore", "xmlopen", "latentstyles",
        }
        stack = []
        ignorable = False
        out = []

        for match in pattern.finditer(rtf_text):
            word, arg, hex_code, char, brace, raw_char = match.groups()
            if brace:
                if brace == "{":
                    stack.append(ignorable)
                elif brace == "}":
                    if stack:
                        ignorable = stack.pop()
            elif hex_code:
                if not ignorable:
                    try:
                        out.append(bytes.fromhex(hex_code).decode("cp1252", errors="replace"))
                    except Exception:
                        pass
            elif char:
                if not ignorable:
                    if char in ("{", "}", "\\"):
                        out.append(char)
                    elif char == "~":
                        out.append(" ")
                    elif char in ("-", "_"):
                        out.append("-")
                if char == "*":
                    ignorable = True
            elif word:
                word = word.lower()
                if word in ("par", "line", "row"):
                    if not ignorable:
                        out.append("\n")
                elif word in ("tab", "cell"):
                    if not ignorable:
                        out.append("\t")
                elif word == "u":
                    if not ignorable and arg:
                        code = int(arg)
                        if code < 0:
                            code += 65536
                        out.append(chr(code))
                elif word in destinations_to_skip:
                    ignorable = True
            elif raw_char:
                if not ignorable:
                    out.append(raw_char)

        text = "".join(out)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n", "\n\n", text)
        result = text.strip()
        if not result:
            frappe.throw(_("No readable text could be extracted from RTF document."))
        return result
    except frappe.ValidationError:
        raise
    except Exception as error:
        frappe.log_error(title="RTF Extraction Failed", message=str(error))
        frappe.throw(_("Failed to extract text from RTF: {0}").format(str(error)))


def extract_word_text(content, ext=None):
    if isinstance(content, str):
        content = content.encode("utf-8", errors="surrogateescape")

    if content.lstrip().startswith(b"{\\rtf") or ext == ".rtf":
        return extract_rtf_text(content)

    if content.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        return extract_docx_text(content)

    if content.lstrip().startswith((b"<html", b"<!DOCTYPE", b"<!doctype")):
        from frappe.utils import strip_html
        return strip_html(content.decode("utf-8", errors="replace")).strip()

    try:
        return extract_docx_text(content)
    except Exception:
        pass

    try:
        return extract_rtf_text(content)
    except Exception:
        pass

    return extract_plain_text(content)


def extract_pptx_text(content):
    try:
        slides_text = []
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            slide_files = sorted(
                name for name in zf.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            )
            for idx, slide_name in enumerate(slide_files, start=1):
                root = ET.fromstring(zf.read(slide_name))
                texts = [
                    node.text.strip() for node in root.iter()
                    if (node.tag.endswith("}t") or node.tag == "t") and node.text and node.text.strip()
                ]
                if texts:
                    slides_text.append(f"=== Slide {idx} ===\n" + "\n".join(texts))
        extracted = "\n\n".join(slides_text).strip()
        if not extracted:
            frappe.throw(_("No readable text could be extracted from the presentation."))
        return extracted
    except frappe.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(title="PowerPoint PPTX Extraction Failed", message=str(e))
        frappe.throw(_("Failed to extract text from presentation: {0}").format(str(e)))


def extract_plain_text(content):
    try:
        extracted = decode_text_bytes(content).strip()
        if not extracted:
            frappe.throw(_("File contains no readable text."))
        return extracted
    except frappe.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(title="Plain Text Extraction Failed", message=str(e))
        frappe.throw(_("Failed to extract text from file: {0}").format(str(e)))


def extract_document_text(file_url, document_type=None, file_name=None, content=None, file_meta=None):
    if not file_url:
        frappe.throw(_("Please upload a file first."))

    meta = file_meta or {}
    if content is None:
        content, meta = get_file_content_with_meta(file_url)
    if not content:
        frappe.throw(_("File not found or empty: {0}").format(file_url))

    if isinstance(content, str):
        content = content.encode("utf-8", errors="surrogateescape")

    resolved_name = file_name or meta.get("file_name")
    ext = detect_file_extension(
        file_url=file_url,
        content=content,
        file_name=resolved_name,
        content_type=meta.get("content_type"),
    )

    doc_type = document_type or resolve_document_type_from_ext(ext)
    if document_type and ext:
        detected_type = resolve_document_type_from_ext(ext)
        if document_type == "PDF" and detected_type != "PDF":
            doc_type = detected_type

    if doc_type == "Image":
        return extract_image_text(file_url, content=content)
    if doc_type == "Excel":
        return extract_excel_text(file_url, content=content, ext=ext)
    if doc_type == "Word":
        return extract_word_text(content, ext=ext)
    if doc_type == "Presentation":
        return extract_pptx_text(content)
    if doc_type == "Text":
        return extract_plain_text(content)
    return extract_pdf_text(file_url, content=content)
