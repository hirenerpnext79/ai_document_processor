import io
import json
import os
import requests
import frappe
from frappe import _

try:
    from PIL import Image
    import pytesseract
    HAS_OCR_LIBS = True
except ImportError:
    HAS_OCR_LIBS = False

from ai_document_processor.ai_services import generate

@frappe.whitelist()
def get_default_ai_provider(user=None):
    if not user:
        user = frappe.session.user
        
    roles = frappe.get_roles(user)
    
    provider = frappe.get_all(
        "AI Provider Access",
        filters={
            "access_type": "User",
            "user": user,
            "is_default": 1
        },
        pluck="parent",
        limit=1,
        ignore_permissions=True
    )

    if provider and frappe.db.get_value("AI Provider", provider[0], "is_active") == 1:
        return provider[0]

    if roles:
        provider = frappe.get_all(
            "AI Provider Access",
            filters={
                "access_type": "Role",
                "role": ("in", roles),
                "is_default": 1
            },
            pluck="parent",
            limit=1,
            ignore_permissions=True
        )

        if provider and frappe.db.get_value("AI Provider", provider[0], "is_active") == 1:
            return provider[0]

    latest_active = frappe.get_all(
        "AI Provider",
        filters={"is_active": 1},
        order_by="creation desc",
        limit=1,
        pluck="name",
        ignore_permissions=True
    )

    if latest_active:
        return latest_active[0]

    return None

def is_google_drive_url(url):
    if not url or not isinstance(url, str):
        return False
    return "drive.google.com" in url or "docs.google.com" in url

def extract_file_id(url):
    if not url:
        return None
    clean = str(url).strip()
    if "/d/" in clean:
        return clean.split("/d/")[1].split("/")[0].split("?")[0]
    if "id=" in clean:
        return clean.split("id=")[1].split("&")[0]
    return None

def download_google_drive_file(url):
    file_id = extract_file_id(url)
    if not file_id:
        return None

    token = None
    try:
        gd = frappe.get_doc("Google Drive")
        token = gd.get_access_token()
    except Exception:
        token = None

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        api_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
        response = requests.get(api_url, headers=headers, timeout=30)
        if response.status_code == 200:
            return response.content
    except Exception as e:
        frappe.log_error(message=f"Google Drive API Download Error: {str(e)}", title="Google Drive Download Failed")

    try:
        fallback_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        response = requests.get(fallback_url, timeout=30)
        if response.status_code == 200 and not response.headers.get("Content-Type", "").startswith("text/html"):
            return response.content
    except Exception:
        pass

    return None

def _get_file_content(file_url):
    if not file_url:
        return None

    if is_google_drive_url(file_url):
        return download_google_drive_file(file_url)

    if file_url.startswith(("http://", "https://")):
        try:
            response = requests.get(file_url, timeout=30)
            if response.status_code == 200:
                return response.content
        except Exception as e:
            frappe.log_error(message=f"File URL Download Error: {str(e)}", title="File Download Error")
            return None

    if frappe.db.exists("File", {"file_url": file_url}):
        file_doc = frappe.get_doc("File", {"file_url": file_url})
        return file_doc.get_content()

    for folder in ["public", "private"]:
        path = frappe.get_site_path(folder, file_url.lstrip("/"))
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()

    return None

def _extract_text_from_file(file_url, doc_type_name):
    if not file_url:
        frappe.throw(_("Please upload a Document first."), title=_("Document Required"))

    file_content = _get_file_content(file_url)
    if not file_content:
        frappe.throw(_("Could not fetch file content from {0}").format(file_url), title=_("File Not Found"))

    if not HAS_OCR_LIBS:
        frappe.msgprint(_("OCR libraries (pytesseract or PIL) are not installed. Skipping extraction."), indicator="orange", alert=True)
        return None

    try:
        image = Image.open(io.BytesIO(file_content))
        extracted_text = pytesseract.image_to_string(image)
        return extracted_text.strip()
    except Exception as e:
        frappe.msgprint(_("OCR Extraction Failed. Skipping extraction. Check Error Log for details."), indicator="orange", alert=True)
        frappe.log_error(message=f"OCR Extraction Failed: {str(e)}", title=f"{doc_type_name} OCR Error")
        return None

def _generate_llm_response(prompt_text, extracted_text, doc_type_name, ai_provider=None):
    provider_name = ai_provider or get_default_ai_provider()
    
    if not provider_name:
        frappe.throw(_("No enabled AI Provider found"))
        
    provider_doc = frappe.get_doc("AI Provider", provider_name)
   
    try:
        prompt_doc = frappe._dict(prompt=prompt_text)
        result, usage = generate(provider_doc, prompt_doc, extracted_text)        

        data = json.loads(result)
        usage_data = usage if usage else {}
        usage_data["ai_provider"] = provider_doc.name
        data["token_usage"] = json.dumps(usage_data)
        return data
    except Exception as e:
        frappe.log_error(message=f"LLM Extraction Failed: {str(e)}", title=f"{doc_type_name} LLM Error")
        frappe.msgprint(_("LLM Extraction Failed: {0}").format(str(e)), title=_("Extraction Error"), indicator="red")
        return {}

@frappe.whitelist()
def process_contact_document(file_url=None, ai_provider=None):
    extracted_text = _extract_text_from_file(file_url, "Contact Document")
    if not extracted_text:
        return {}

    prompt_text = f"""
    Extract the following contact information from the OCR text provided below.
    Return ONLY a valid JSON object matching this exact schema, with no additional text or markdown formatting.
    Missing values should be empty strings.
    For 'salutation', use ONLY one of the following values if applicable: "Prof", "Master", "Miss", "Madam", "Mrs", "Dr", "Mx", "Ms", "Mr".
    For 'last_name', extract ONLY the person's surname (e.g. SAVALIYA).
    For 'company_name', extract ONLY the company name (e.g. HNS). CRITICAL: Do NOT join or include the person's last name inside the company name!

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

    return _generate_llm_response(prompt_text, extracted_text, "Contact Document", ai_provider)

@frappe.whitelist()
def process_sales_order_document(file_url=None, ai_provider=None):
    extracted_text = _extract_text_from_file(file_url, "Sales Order Document")
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

    return _generate_llm_response(prompt_text, extracted_text, "Sales Order Document", ai_provider)

def _should_auto_extract(doc, file_field):
    if not doc.get(file_field):
        return False

    if doc.is_new():
        return True
        
    doc_before_save = doc.get_doc_before_save()
    if doc_before_save and doc.get(file_field) != doc_before_save.get(file_field):
        return True
        
    return False

def auto_extract_contact(doc, method):
    try:
        if not _should_auto_extract(doc, "ai_id_document"):
            return

        file_url = doc.ai_id_document
        data = process_contact_document(file_url, doc.get("ai_provider"))
        if not data:
            return

        for fieldname, value in data.items():
            if not value:
                continue

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
            elif fieldname in ["visiting_card_address", "first_name", "middle_name", "last_name", "salutation", "designation", "gender", "company_name", "token_usage"]:
                if not doc.get(fieldname):
                    doc.set(fieldname, value)
    except Exception as e:
        frappe.log_error(message=f"Contact Auto Extraction Error: {str(e)}", title="Contact Auto Extraction Error")

def auto_extract_sales_order(doc, method):
    try:
        if not _should_auto_extract(doc, "ai_po_document"):
            return

        file_url = doc.ai_po_document
        data = process_sales_order_document(file_url, doc.get("ai_provider"))
        if not data:
            return

        for fieldname, value in data.items():
            if not value:
                continue

            if fieldname == "items" and isinstance(value, list):
                doc.set("items", [])
                for item in value:
                    if item.get("item_code") or item.get("item_name") or item.get("description"):
                        row = doc.append("items", {})
                        for item_field in ["item_code", "delivery_date", "item_name", "description", "qty", "uom", "rate"]:
                            if item.get(item_field):
                                row.set(item_field, item.get(item_field))

            elif fieldname in ["customer", "po_no", "delivery_date", "token_usage"]:
                if not doc.get(fieldname):
                    doc.set(fieldname, value)
    except Exception as e:
        frappe.log_error(message=f"Sales Order Auto Extraction Error: {str(e)}", title="Sales Order Auto Extraction Error")

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_provider_query(doctype, txt, searchfield, start, page_len, filters):
    user = frappe.session.user
    roles = frappe.get_roles(user)
    
    allowed_by_user = frappe.get_all(
        "AI Provider Access",
        filters={"access_type": "User", "user": user},
        pluck="parent",
        ignore_permissions=True
    )
    
    allowed_by_role = []
    if roles:
        allowed_by_role = frappe.get_all(
            "AI Provider Access",
            filters={"access_type": "Role", "role": ("in", roles)},
            pluck="parent",
            ignore_permissions=True
        )
        
    allowed_providers = list(set(allowed_by_user + allowed_by_role))
    
    searchfield = searchfield or "name"
    start = int(start) if start else 0
    page_len = int(page_len) if page_len else 20
    
    query_filters = [
        [searchfield, "like", f"%{txt}%"],
        ["is_active", "=", 1]
    ]
    
    if allowed_providers:
        query_filters.append(["name", "in", allowed_providers])
    
    return frappe.get_all(
        "AI Provider",
        filters=query_filters,
        fields=["name", "provider_name"],
        limit_start=start,
        limit_page_length=page_len,
        as_list=True,
        ignore_permissions=True
    )
