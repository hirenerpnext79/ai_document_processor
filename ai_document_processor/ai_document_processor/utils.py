import frappe
from frappe import _
import os

def extract_pdf_text(file_url):
    file_path = frappe.get_site_path('public', file_url.lstrip('/'))
    if not os.path.exists(file_path):
        file_path = frappe.get_site_path('private', file_url.lstrip('/'))
        
    if not os.path.exists(file_path):
        frappe.throw(_("File not found: {0}").format(file_url))

    text = ""
    
    try:
        import fitz
        doc = fitz.open(file_path)
        for page in doc:
            text += page.get_text() + "\n"
    except ImportError as e:
        frappe.log_error(title="PyMuPDF Import Failed", message=str(e))
        frappe.throw(_("No PDF extraction library is installed. Please run 'pip install pymupdf' in your bench environment."))
    except Exception as e:
        frappe.log_error(title="PyMuPDF Extraction Failed", message=str(e))
        frappe.throw(_("Failed to extract text from PDF."))

    return text
