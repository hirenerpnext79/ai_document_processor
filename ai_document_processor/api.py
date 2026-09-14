import frappe
import json
import io
import pytesseract
from PIL import Image
from frappe import _
from ai_document_processor.ai_services import generate

@frappe.whitelist()
def process_contact_document(file_url=None, ai_provider=None):
    if not file_url:
        frappe.throw(_("Please upload an ID Document first."), title=_("Document Required"))

    if not ai_provider:
        frappe.throw(_("Please select an AI Provider first."), title=_("AI Provider Required"))

    file_doc = frappe.get_doc("File", {"file_url": file_url})
    file_content = file_doc.get_content()

    try:
        image = Image.open(io.BytesIO(file_content))
        extracted_text = pytesseract.image_to_string(image)
        extracted_text = extracted_text.strip()
    except Exception as e:
        frappe.log_error(f"OCR Extraction Failed: {str(e)}", "Contact Document OCR Error")
        return {}

    if not extracted_text:
        return {}

    prompt_text = f"""
    Extract the following contact information from the OCR text provided below.
    Return ONLY a valid JSON object matching this exact schema, with no additional text or markdown formatting.
    Missing values should be empty strings.

    {{
      "first_name": "",
      "middle_name": "",
      "last_name": "",
      "salutation": "",
      "designation": "",
      "gender": "",
      "company_name": "",
      "visiting_card_address": "",
      "email_ids": ["email1", "email2"],
      "phone_nos": ["phone1", "phone2"]
    }}

    OCR Text:
    {extracted_text}
    """

    if ai_provider:
        provider_doc = frappe.get_doc("AI Provider", ai_provider)
    else:
        provider_doc = frappe.get_all(
            "AI Provider",
            filters={
                "status": "Active"
            },
            fields=["*"],
            limit=1
        )
        if provider_doc:
            provider_doc = frappe.get_doc("AI Provider", provider_doc[0].name)

    if not provider_doc:
        frappe.throw(_("No enabled AI Provider found"))
   
    try:
        class Prompt:
            prompt = prompt_text
            
        result, usage = generate(provider_doc, Prompt(), extracted_text)        

        data = json.loads(result)
        data["token_usage"] = json.dumps(usage) if usage else "{}"
        return data
    except Exception as e:
        frappe.log_error(f"LLM Extraction Failed: {str(e)}", "Contact Document LLM Error")
        return {}

@frappe.whitelist()
def process_sales_order_document(file_url=None, ai_provider=None):
    if not file_url:
        frappe.throw(_("Please upload a PO Document first."), title=_("Document Required"))

    if not ai_provider:
        frappe.throw(_("Please select an AI Provider first."), title=_("AI Provider Required"))

    file_doc = frappe.get_doc("File", {"file_url": file_url})
    file_content = file_doc.get_content()

    try:
        image = Image.open(io.BytesIO(file_content))
        extracted_text = pytesseract.image_to_string(image)
        extracted_text = extracted_text.strip()
    except Exception as e:
        frappe.log_error(f"OCR Extraction Failed: {str(e)}", "Sales Order Document OCR Error")
        return {}

    if not extracted_text:
        return {}

    prompt_text = f"""
    Extract the following Sales Order information from the OCR text provided below.
    Return ONLY a valid JSON object matching this exact schema, with no additional text or markdown formatting.
    Missing values should be empty strings. The 'items' array should contain objects with the specified fields.
    For numbers like qty and rate, return them as numbers if possible, otherwise strings.

    {{
      "customer": "",
      "po_no": "",
      "delivery_date": "",
      "items": [
        {{
          "item_code": "",
          "delivery_date": "",
          "item_name": "",
          "description": "",
          "qty": 0,
          "uom": "",
          "rate": 0
        }}
      ]
    }}

    OCR Text:
    {extracted_text}
    """

    if ai_provider:
        provider_doc = frappe.get_doc("AI Provider", ai_provider)
    else:
        provider_doc = frappe.get_all(
            "AI Provider",
            filters={
                "status": "Active"
            },
            fields=["*"],
            limit=1
        )
        if provider_doc:
            provider_doc = frappe.get_doc("AI Provider", provider_doc[0].name)

    if not provider_doc:
        frappe.throw(_("No enabled AI Provider found"))
   
    try:
        class Prompt:
            prompt = prompt_text
            
        result, usage = generate(provider_doc, Prompt(), extracted_text)        

        data = json.loads(result)
        data["token_usage"] = json.dumps(usage) if usage else "{}"
        return data
    except Exception as e:
        frappe.log_error(f"LLM Extraction Failed: {str(e)}", "Sales Order Document LLM Error")
        return {}

def auto_extract_contact(doc, method):
    if not doc.id_document:
        return

    should_extract = False
    if doc.is_new():
        should_extract = True
    else:
        doc_before_save = doc.get_doc_before_save()
        if doc_before_save and doc.id_document != doc_before_save.id_document:
            should_extract = True
            
    if not should_extract:
        return
        
    if not doc.ai_provider:
        frappe.throw(_("Please select an AI Provider before saving the document for auto-extraction."))
        
    data = process_contact_document(doc.id_document, doc.ai_provider)
    if not data:
        return
        
    for fieldname, value in data.items():
        if not value: continue
        
        if fieldname == "email_ids" and isinstance(value, list):
            doc.set("email_ids", [])
            for email in value:
                if email:
                    doc.append("email_ids", {"email_id": email, "is_primary": 1})
        elif fieldname == "phone_nos" and isinstance(value, list):
            doc.set("phone_nos", [])
            for phone in value:
                if phone:
                    doc.append("phone_nos", {"phone": phone, "is_primary_phone": 1})
        elif fieldname == "visiting_card_address" and not doc.visiting_card_address:
            doc.visiting_card_address = value
        elif fieldname == "first_name" and not doc.first_name:
            doc.first_name = value
        elif fieldname == "middle_name" and not doc.middle_name:
            doc.middle_name = value
        elif fieldname == "last_name" and not doc.last_name:
            doc.last_name = value
        elif fieldname == "salutation" and not doc.salutation:
            doc.salutation = value
        elif fieldname == "designation" and not doc.designation:
            doc.designation = value
        elif fieldname == "gender" and not doc.gender:
            doc.gender = value
        elif fieldname == "company_name" and not doc.company_name:
            doc.company_name = value
        elif fieldname == "token_usage" and not doc.token_usage:
            doc.token_usage = value

def auto_extract_sales_order(doc, method):
    if not doc.po_document:
        return

    should_extract = False
    if doc.is_new():
        should_extract = True
    else:
        doc_before_save = doc.get_doc_before_save()
        if doc_before_save and doc.po_document != doc_before_save.po_document:
            should_extract = True
            
    if not should_extract:
        return
        
    if not doc.ai_provider:
        frappe.throw(_("Please select an AI Provider before saving the document for auto-extraction."))
        
    data = process_sales_order_document(doc.po_document, doc.ai_provider)
    if not data:
        return
        
    for fieldname, value in data.items():
        if not value: continue
        
        if fieldname == "items" and isinstance(value, list):
            doc.set("items", [])
            for item in value:
                if item.get("item_code") or item.get("item_name") or item.get("description"):
                    row = doc.append("items", {})
                    if item.get("item_code"): row.item_code = item.get("item_code")
                    if item.get("delivery_date"): row.delivery_date = item.get("delivery_date")
                    if item.get("item_name"): row.item_name = item.get("item_name")
                    if item.get("description"): row.description = item.get("description")
                    if item.get("qty"): row.qty = item.get("qty")
                    if item.get("uom"): row.uom = item.get("uom")
                    if item.get("rate"): row.rate = item.get("rate")
        elif fieldname == "customer" and not doc.customer:
            doc.customer = value
        elif fieldname == "po_no" and not doc.po_no:
            doc.po_no = value
        elif fieldname == "delivery_date" and not doc.delivery_date:
            doc.delivery_date = value
        elif fieldname == "token_usage" and not doc.token_usage:
            doc.token_usage = value

