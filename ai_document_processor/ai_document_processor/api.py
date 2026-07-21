import frappe
from frappe import _
from .utils import extract_pdf_text
from ai_document_processor.ai_services import generate
import json

@frappe.whitelist()
def generate_response(docname, user=None):
    doc = frappe.get_doc("AI Document", docname)
    
    if not doc.pdf_file:
        frappe.throw(_("Please upload a PDF file first."))
        
    if not doc.provider:
        frappe.throw(_("Please select an AI Provider."))
        
    if not doc.prompt:
        frappe.throw(_("Please select an AI Prompt."))
        
    try:
        # Update status
        doc.db_set("status", "Processing", update_modified=False)
        doc.db_set("error_log", "", update_modified=False)
        frappe.db.commit()
        
        # 1. Extract text
        extracted_text = extract_pdf_text(doc.pdf_file)
        doc.extracted_text = extracted_text
        
        # 2. Get provider and prompt
        provider = frappe.get_doc("AI Provider", doc.provider)
        prompt = frappe.get_doc("AI Prompt", doc.prompt)
        
        # 3. Call AI
        ai_response_text = generate(provider, prompt, extracted_text)
        doc.ai_response = ai_response_text
        
        # 4. Parse JSON and update fields
        try:
            parsed = json.loads(ai_response_text)
            
            if "title" in parsed:
                doc.seo_title = parsed["title"]
                
            if "summary" in parsed:
                doc.summary = parsed["summary"]
                
            if "hashtags" in parsed:
                hashtags = parsed["hashtags"]
                if isinstance(hashtags, list):
                    doc.generated_hashtags = " ".join([h if h.startswith('#') else f"#{h}" for h in hashtags])
                else:
                    doc.generated_hashtags = str(hashtags)
                    
            if "keywords" in parsed:
                keywords = parsed["keywords"]
                if isinstance(keywords, list):
                    doc.generated_keywords = ", ".join([str(k) for k in keywords])
                else:
                    doc.generated_keywords = str(keywords)
                    
            doc.json_response = json.dumps(parsed, indent=2) # Store full JSON
                
        except json.JSONDecodeError:
            doc.error_log = "Failed to parse JSON from AI response."
            doc.json_response = ai_response_text
        
        # Mark completed
        doc.db_set("status", "Completed", update_modified=False)
        frappe.db.commit()
        
        if user:
            frappe.publish_realtime('msgprint', 
                                    dict(message=_("AI Processing Completed Successfully for {0}").format(docname), title="Success", indicator="green"), 
                                    user=user)
        
        return "Success"
        
    except Exception as e:
        frappe.log_error("AI Document Processor Error", str(e))
        doc.db_set("status", "Failed", update_modified=False)
        doc.db_set("error_log", str(e), update_modified=False)
        frappe.db.commit() # Make sure to commit the failed status
        
        if user:
            frappe.publish_realtime('msgprint', 
                                    dict(message=_("Error during AI processing for {0}: {1}").format(docname, str(e)), title="Processing Failed", indicator="red"), 
                                    user=user)
        
        # DO NOT throw when running in background queue, just log it
        if not frappe.flags.in_background:
            frappe.throw(_("Error during AI processing. Please check Error Log."))

@frappe.whitelist()
def enqueue_generate_response(docname):
    frappe.enqueue(
        'ai_document_processor.ai_document_processor.api.generate_response',
        queue='long',
        timeout=1500,
        docname=docname,
        user=frappe.session.user
    )
    return "Queued"
