import csv
import io
import os
import requests
import frappe
from frappe import _


def get_file_extension(file_url):
    if not file_url:
        return ""
    clean_url = str(file_url).split("?")[0]
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
        return clean_url.split("/d/")[1].split("/")[0].split("?")[0]
    if "id=" in clean_url:
        return clean_url.split("id=")[1].split("&")[0]
    return None


def download_google_drive_file(url):
    file_id = extract_google_drive_id(url)
    if not file_id:
        return None

    headers = {}
    try:
        gd = frappe.get_doc("Google Drive")
        token = gd.get_access_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    except Exception:
        pass

    try:
        api_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
        response = requests.get(api_url, headers=headers, timeout=30)
        if response.status_code == 200:
            return response.content
    except Exception as e:
        frappe.log_error(title="Google Drive Download Error", message=str(e))

    try:
        fallback_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        response = requests.get(fallback_url, timeout=30)
        if response.status_code == 200 and not response.headers.get("Content-Type", "").startswith("text/html"):
            return response.content
    except Exception as e:
        frappe.log_error(title="Google Drive Fallback Error", message=str(e))

    return None


def get_file_content(file_url):
    if not file_url:
        return None

    try:
        if is_google_drive_url(file_url):
            return download_google_drive_file(file_url)

        if str(file_url).startswith(("http://", "https://")):
            response = requests.get(file_url, timeout=30)
            if response.status_code == 200:
                return response.content

        if frappe.db.exists("File", {"file_url": file_url}):
            file_doc = frappe.get_doc("File", {"file_url": file_url})
            content = file_doc.get_content()
            if content:
                return content

        clean_path = str(file_url).lstrip("/")
        for prefix in ["public", "private", ""]:
            path = frappe.get_site_path(prefix, clean_path) if prefix else frappe.get_site_path(clean_path)
            if os.path.exists(path) and os.path.isfile(path):
                with open(path, "rb") as f:
                    return f.read()
    except Exception as e:
        frappe.log_error(title="Get File Content Error", message=str(e))

    return None


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


def extract_pdf_text(file_url):
    content = get_file_content(file_url)
    if not content:
        frappe.throw(_("File not found or empty: {0}").format(file_url))

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
    except Exception as e:
        frappe.log_error(title="PyMuPDF Extraction Failed", message=str(e))
        frappe.throw(_("Failed to extract text from PDF: {0}").format(str(e)))


def extract_image_text(file_url):
    content = get_file_content(file_url)
    if not content:
        frappe.throw(_("File not found or empty: {0}").format(file_url))

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
    except Exception as e:
        frappe.log_error(title="Image OCR Extraction Failed", message=str(e))
        frappe.throw(_("Failed to extract text from Image: {0}").format(str(e)))


def extract_csv_text(content):
    try:
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError:
            decoded = content.decode("latin-1", errors="replace")

        stream = io.StringIO(decoded)
        reader = csv.reader(stream)
        rows = []
        for row in reader:
            if row and any(c is not None and str(c).strip() != "" for c in row):
                rows.append([str(c).strip() if c is not None else "" for c in row])

        if not rows:
            frappe.throw(_("CSV file is empty or contains no readable data."))

        output = io.StringIO()
        writer = csv.writer(output)
        for r in rows:
            writer.writerow(r)
        return output.getvalue().strip()
    except Exception as e:
        frappe.log_error(title="CSV Extraction Failed", message=str(e))
        frappe.throw(_("Failed to extract data from CSV: {0}").format(str(e)))


def extract_xlsx_text(content):
    try:
        import openpyxl
    except ImportError as e:
        frappe.log_error(title="openpyxl Missing", message=str(e))
        frappe.throw(_("openpyxl library is not installed. Please run 'pip install openpyxl'."))

    try:
        wb = openpyxl.load_workbook(filename=io.BytesIO(content), data_only=True, read_only=True)
        sheets_data = []
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            rows = []
            for row in sheet.iter_rows(values_only=True):
                if row and any(c is not None and str(c).strip() != "" for c in row):
                    rows.append([str(c).strip() if c is not None else "" for c in row])
            if rows:
                sheets_data.append((sheet_name, rows))

        if not sheets_data:
            frappe.throw(_("Excel file contains no readable data."))

        output_lines = []
        for sheet_name, rows in sheets_data:
            output_lines.append(f"=== Sheet: {sheet_name} ===")
            csv_buf = io.StringIO()
            writer = csv.writer(csv_buf)
            for r in rows:
                writer.writerow(r)
            output_lines.append(csv_buf.getvalue().strip())
            output_lines.append("")

        return "\n".join(output_lines).strip()
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

        output_lines = []
        for sheet_name, rows in sheets_data:
            output_lines.append(f"=== Sheet: {sheet_name} ===")
            csv_buf = io.StringIO()
            writer = csv.writer(csv_buf)
            for r in rows:
                writer.writerow(r)
            output_lines.append(csv_buf.getvalue().strip())
            output_lines.append("")

        return "\n".join(output_lines).strip()
    except Exception as e:
        frappe.log_error(title="Excel XLS Extraction Failed", message=str(e))
        frappe.throw(_("Failed to extract data from XLS file: {0}").format(str(e)))


def extract_excel_text(file_url):
    content = get_file_content(file_url)
    if not content:
        frappe.throw(_("File not found or empty: {0}").format(file_url))

    ext = get_file_extension(file_url)
    if ext == ".csv":
        return extract_csv_text(content)
    elif ext == ".xls":
        try:
            return extract_xls_text(content)
        except Exception:
            return extract_xlsx_text(content)
    else:
        try:
            return extract_xlsx_text(content)
        except Exception:
            try:
                return extract_xls_text(content)
            except Exception:
                return extract_csv_text(content)


def extract_document_text(file_url, document_type=None):
    if not file_url:
        frappe.throw(_("Please upload a file first."))

    doc_type = document_type
    if not doc_type:
        ext = get_file_extension(file_url)
        if ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif", ".jfif", ".gif"]:
            doc_type = "Image"
        elif ext in [".xlsx", ".xls", ".xlsm", ".csv"]:
            doc_type = "Excel"
        else:
            doc_type = "PDF"

    if doc_type == "Image":
        return extract_image_text(file_url)
    elif doc_type == "Excel":
        return extract_excel_text(file_url)
    else:
        return extract_pdf_text(file_url)
