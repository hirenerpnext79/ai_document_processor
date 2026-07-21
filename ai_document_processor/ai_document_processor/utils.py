import frappe
import fitz  # PyMuPDF
import os

def extract_pdf_text(file_url):
    file_path = frappe.get_site_path('public', file_url.lstrip('/'))
    if not os.path.exists(file_path):
        file_path = frappe.get_site_path('private', file_url.lstrip('/'))
        
    if not os.path.exists(file_path):
        frappe.throw(f"File not found: {file_url}")
        
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text()
        
    return text
