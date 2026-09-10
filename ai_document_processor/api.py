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
      "address": "",
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
        class DummyPrompt:
            prompt = prompt_text
        result, usage = generate(provider_doc, DummyPrompt(), extracted_text)        
        if "```json" in result:
            result = result.split("```json")[1].split("```")[0].strip()
        elif "```" in result:
            result = result.split("```")[1].split("```")[0].strip()
        print(result)
        print(usage)
        data = json.loads(result)
        print(data)
        return data
    except Exception as e:
        frappe.log_error(f"LLM Extraction Failed: {str(e)}", "Contact Document LLM Error")
        return {}



