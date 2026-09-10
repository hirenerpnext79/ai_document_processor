import frappe
from frappe import _
import os

def extract_pdf_text(file_url, pdf_library=None):
    file_path = frappe.get_site_path('public', file_url.lstrip('/'))
    if not os.path.exists(file_path):
        file_path = frappe.get_site_path('private', file_url.lstrip('/'))
        
    if not os.path.exists(file_path):
        frappe.throw(_("File not found: {0}").format(file_url))

    text = ""
    success = False

    # Try 1: pdfplumber - Great for layouts and tables
    if not success and (not pdf_library or pdf_library == "pdfplumber"):
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
            success = True
        except ImportError as e:
            frappe.log_error(title="pdfplumber Import Failed", message=str(e))
        except Exception as e:
            frappe.log_error(title="pdfplumber Extraction Failed", message=str(e))

    # Try 2: pypdf - Modern pure python
    if not success and (not pdf_library or pdf_library == "pypdf"):
        try:
            import pypdf
            with open(file_path, 'rb') as f:
                reader = pypdf.PdfReader(f)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
            success = True
        except ImportError as e:
            frappe.log_error(title="pypdf Import Failed", message=str(e))
        except Exception as e:
            frappe.log_error(title="pypdf Extraction Failed", message=str(e))

    # Try 3: PyPDF2 - Legacy pure python
    if not success and (not pdf_library or pdf_library == "PyPDF2"):
        try:
            import PyPDF2
            with open(file_path, 'rb') as f:
                if hasattr(PyPDF2, 'PdfReader'):
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        extracted = page.extract_text()
                        if extracted:
                            text += extracted + "\n"
                else:
                    reader = PyPDF2.PdfFileReader(f)
                    for i in range(reader.getNumPages()):
                        page = reader.getPage(i)
                        extracted = page.extractText()
                        if extracted:
                            text += extracted + "\n"
            success = True
        except ImportError as e:
            frappe.log_error(title="PyPDF2 Import Failed", message=str(e))
        except Exception as e:
            frappe.log_error(title="PyPDF2 Extraction Failed", message=str(e))

    # Try 4: PyMuPDF (fitz) - Fastest and most accurate
    if not success and (not pdf_library or pdf_library == "PyMuPDF"):
        try:
            import fitz
            doc = fitz.open(file_path)
            for page in doc:
                text += page.get_text() + "\n"
            success = True
        except ImportError as e:
            frappe.log_error(title="PyMuPDF Import Failed", message=str(e))
        except Exception as e:
            frappe.log_error(title="PyMuPDF Extraction Failed", message=str(e))

    if not success:
        frappe.throw(_("No PDF extraction library is installed or selected library failed. Please run 'pip install pymupdf pypdf pdfplumber' in your bench environment."))

    return text
