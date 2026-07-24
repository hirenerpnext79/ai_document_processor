import frappe
from frappe import _
import os

def extract_pdf_text(file_url):
    try:
        import fitz  # PyMuPDF
    except ImportError:
        frappe.throw(_("PyMuPDF (fitz) is not installed in the environment. Please run 'pip install pymupdf' in your bench environment."))

    file_path = frappe.get_site_path('public', file_url.lstrip('/'))
    if not os.path.exists(file_path):
        file_path = frappe.get_site_path('private', file_url.lstrip('/'))
        
    if not os.path.exists(file_path):
        frappe.throw(_("File not found: {0}").format(file_url))
        
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text()
        
    return text

