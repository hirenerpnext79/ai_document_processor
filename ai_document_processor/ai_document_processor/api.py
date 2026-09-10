import frappe
from frappe import _
from .utils import extract_pdf_text
from ai_document_processor.ai_services import generate
import json

def validate_doc(doc):
    if not doc.pdf_file:
        frappe.throw(_("Please upload a PDF file first."))
    if not doc.provider:
        frappe.throw(_("Please select an AI Provider."))
    if not doc.prompt:
        frappe.throw(_("Please select an AI Prompt."))

def process_ai_response(doc, ai_response_text, usage_metadata=None):
    doc.ai_response = ai_response_text
    if usage_metadata:
        if isinstance(usage_metadata, (dict, list)):
            doc.usage_token = json.dumps(usage_metadata, indent=2)
        else:
            doc.usage_token = str(usage_metadata)
    try:
        parsed = json.loads(ai_response_text)
        doc.seo_title = parsed.get("title", doc.seo_title)
        doc.summary = parsed.get("summary", doc.summary)
        
        hashtags = parsed.get("hashtags", [])
        doc.generated_hashtags = " ".join([h if h.startswith('#') else f"#{h}" for h in hashtags]) if isinstance(hashtags, list) else str(hashtags)
        
        keywords = parsed.get("keywords", [])
        doc.generated_keywords = ", ".join(map(str, keywords)) if isinstance(keywords, list) else str(keywords)
        
        doc.json_response = json.dumps(parsed, indent=2)
    except json.JSONDecodeError:
        doc.error_log = "Failed to parse JSON from AI response."
        doc.json_response = ai_response_text

@frappe.whitelist()
def generate_response(docname, user=None):
    doc = frappe.get_doc("AI Document", docname)
    validate_doc(doc)
        
    try:
        doc.db_set("status", "Processing", update_modified=False)
        doc.db_set("error_log", "", update_modified=False)
        frappe.db.commit()
        
        pdf_library = doc.get("pdf_library")
        doc.extracted_text = extract_pdf_text(doc.pdf_file, pdf_library=pdf_library)
        provider = frappe.get_doc("AI Provider", doc.provider)
        prompt = frappe.get_doc("AI Prompt", doc.prompt)
        
        ai_response_text, usage_metadata = generate(provider, prompt, doc.extracted_text)
        process_ai_response(doc, ai_response_text, usage_metadata)
        
        doc.status = "Completed"
        doc.completed_at = frappe.utils.now_datetime()
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        
        if user:
            frappe.publish_realtime('msgprint', dict(message=_("AI Processing Completed Successfully for {0}").format(docname), title="Success", indicator="green"), user=user)
        
        return "Success"
        
    except Exception as e:
        frappe.log_error("AI Document Processor Error", str(e))
        doc.db_set("status", "Failed", update_modified=False)
        doc.db_set("error_log", str(e), update_modified=False)
        frappe.db.commit()
        
        if user:
            frappe.publish_realtime('msgprint', dict(message=_("Error during AI processing for {0}: {1}").format(docname, str(e)), title="Processing Failed", indicator="red"), user=user)
        
        if not frappe.flags.in_background:
            frappe.throw(_("Error during AI processing. Please check Error Log."))

@frappe.whitelist()
def enqueue_generate_response(docname):
    frappe.db.set_value("AI Document", docname, "processed_at", frappe.utils.now_datetime())
    frappe.enqueue(
        'ai_document_processor.ai_document_processor.api.generate_response',
        queue='long',
        timeout=1500,
        docname=docname,
        user=frappe.session.user
    )
    return "Queued"
