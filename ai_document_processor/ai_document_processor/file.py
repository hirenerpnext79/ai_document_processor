import datetime
import json
import re
import time
import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime
from ai_document_processor.api import get_default_ai_provider
from ai_document_processor.ai_services import generate
from .utils import extract_document_text, get_file_content, get_file_extension


def parse_ai_json_response(response_text):
    if not response_text:
        return {}

    clean_text = response_text.strip()
    if clean_text.startswith("```"):
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_text)
        if match:
            clean_text = match.group(1).strip()

    try:
        return json.loads(clean_text)
    except Exception:
        first_brace = clean_text.find("{")
        last_brace = clean_text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            try:
                return json.loads(clean_text[first_brace : last_brace + 1])
            except Exception:
                pass

    return {}


def parse_extracted_date(date_str):
    if not date_str:
        return None

    try:
        cleaned = str(date_str).strip()
        return get_datetime(cleaned)
    except Exception:
        pass

    try:
        digits = re.sub(r"\D", "", str(date_str)[:16])
        if len(digits) >= 8:
            return get_datetime(digits[:8])
    except Exception:
        pass

    return None


def parse_pdf_date_property(date_str):
    if not date_str:
        return None

    clean = str(date_str).strip()
    if clean.startswith("D:"):
        clean = clean[2:]

    digits = re.sub(r"\D", "", clean[:16])
    if len(digits) >= 14:
        try:
            return datetime.datetime.strptime(digits[:14], "%Y%m%d%H%M%S")
        except Exception:
            pass
    if len(digits) >= 8:
        try:
            return datetime.datetime.strptime(digits[:8], "%Y%m%d")
        except Exception:
            pass

    return None


def extract_pdf_doc_property_date(content):
    try:
        import fitz
        doc = fitz.open(stream=content, filetype="pdf")
        meta = doc.metadata or {}
        for key in ["creationDate", "modDate"]:
            val = meta.get(key)
            if val:
                dt = parse_pdf_date_property(val)
                if dt:
                    return dt
    except Exception as e:
        frappe.log_error(title="Extract PDF Date Property Error", message=str(e))
    return None


def extract_excel_doc_property_date(content):
    try:
        import io
        import openpyxl
        wb = openpyxl.load_workbook(filename=io.BytesIO(content), read_only=True)
        props = getattr(wb, "properties", None)
        if props:
            if getattr(props, "created", None):
                return get_datetime(props.created)
            if getattr(props, "modified", None):
                return get_datetime(props.modified)
    except Exception as e:
        frappe.log_error(title="Extract Excel Date Property Error", message=str(e))
    return None


def extract_image_doc_property_date(content):
    try:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(content))
        exif_data = img.getexif() if hasattr(img, "getexif") else None
        if exif_data:
            for tag_id in [36867, 306, 36868]:
                val = exif_data.get(tag_id)
                if val:
                    try:
                        clean_val = str(val).strip().replace(":", "-", 2)
                        return get_datetime(clean_val)
                    except Exception:
                        pass
    except Exception as e:
        frappe.log_error(title="Extract Image Date Property Error", message=str(e))
    return None


def extract_actual_doc_created_date(file_url, content=None):
    if not content:
        content = get_file_content(file_url)
    if not content:
        return None

    ext = get_file_extension(file_url)
    if ext == ".pdf":
        return extract_pdf_doc_property_date(content)
    elif ext in [".xlsx", ".xlsm"]:
        return extract_excel_doc_property_date(content)
    elif ext in [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif"]:
        return extract_image_doc_property_date(content)

    return None


def resolve_doc_datetime(file_url, ai_date_str=None, file_doc=None, content=None):
    actual_doc_date = extract_actual_doc_created_date(file_url, content=content)
    if actual_doc_date:
        return actual_doc_date

    if ai_date_str:
        ai_dt = parse_extracted_date(ai_date_str)
        if ai_dt:
            return ai_dt

    if file_doc and file_doc.creation:
        return file_doc.creation

    return now_datetime()


def get_ai_prompt(custom_prompt=None):
    if custom_prompt:
        return custom_prompt

    return (
        "Analyze the provided document text and extract the following metadata in strict JSON format:\n"
        "{\n"
        '  "title": "A concise and descriptive document title",\n'
        '  "summary": "A 2 to 3 sentence summary of the key content, parties, and purpose",\n'
        '  "tags": ["tag1", "tag2", "tag3"],\n'
        '  "date": "YYYY-MM-DD HH:MM:SS or YYYY-MM-DD (the primary date mentioned or created in the document, or null if not found)"\n'
        "}\n"
        "Respond ONLY with valid JSON. Do not include markdown code block formatting or extra commentary."
    )


def execute_file_ai_generation(file_url, custom_prompt=None, provider_name=None):
    try:
        extracted_text = extract_document_text(file_url)
    except Exception as e:
        frappe.log_error(title="File Text Extraction Failed", message=str(e))
        return {}

    if not extracted_text:
        return {}

    ai_provider = provider_name or get_default_ai_provider()
    if not ai_provider:
        active_providers = frappe.get_all("AI Provider", filters={"is_active": 1}, pluck="name", limit=1)
        if active_providers:
            ai_provider = active_providers[0]

    if not ai_provider:
        frappe.throw(_("No enabled AI Provider found"))

    provider_doc = frappe.get_doc("AI Provider", ai_provider)
    prompt_text = get_ai_prompt(custom_prompt)
    prompt_doc = frappe._dict(prompt=prompt_text)

    last_error = None
    for attempt in range(3):
        try:
            ai_response_text, usage_metadata = generate(provider_doc, prompt_doc, extracted_text[:15000])
            parsed_data = parse_ai_json_response(ai_response_text)
            parsed_data["_usage"] = usage_metadata
            return parsed_data
        except Exception as e:
            last_error = e
            time.sleep(2)

    frappe.log_error(title="File AI Generation Failed", message=str(last_error))
    return {}


def apply_ai_metadata_to_file(doc, metadata, file_url=None):
    title = metadata.get("title", "")
    summary = metadata.get("summary", "")
    tags = metadata.get("tags", [])
    date_val = metadata.get("date", "")

    formatted_tags = ", ".join(tags) if isinstance(tags, list) else str(tags)
    url = file_url or doc.file_url
    formatted_dt = resolve_doc_datetime(url, ai_date_str=date_val, file_doc=doc)

    doc.doc_title = title
    doc.doc_short_summary = summary
    doc.doc_tags = formatted_tags
    doc.doc_datetime = formatted_dt
    doc.is_processed_with_ai = 1


def resolve_file_doc(file_source):
    if hasattr(file_source, "doctype") and file_source.doctype == "File":
        return file_source

    if isinstance(file_source, str):
        if frappe.db.exists("File", file_source):
            return frappe.get_doc("File", file_source)
        if frappe.db.exists("File", {"file_url": file_source}):
            return frappe.get_doc("File", {"file_url": file_source})

    return None


def process_file_with_ai(file_source, prompt=None, ai_provider=None, save=True):
    file_doc = resolve_file_doc(file_source)
    file_url = file_doc.file_url if file_doc else (file_source if isinstance(file_source, str) else None)

    if not file_url:
        return {"status": "Failed", "error": "No file URL found"}

    selected_prompt = prompt
    if not selected_prompt and file_doc and file_doc.prompt:
        prompt_val = file_doc.prompt
        if frappe.db.exists("AI Prompt", prompt_val):
            selected_prompt = frappe.db.get_value("AI Prompt", prompt_val, "prompt")
        else:
            selected_prompt = prompt_val

    metadata = execute_file_ai_generation(file_url, custom_prompt=selected_prompt, provider_name=ai_provider)
    if not metadata:
        return {"status": "Failed", "error": "AI could not generate metadata"}

    if file_doc:
        apply_ai_metadata_to_file(file_doc, metadata, file_url=file_url)
        if save and not file_doc.is_new():
            try:
                file_doc.flags.ignore_links = True
                file_doc.save(ignore_permissions=True)
            except Exception:
                file_doc.db_set({
                    "doc_title": file_doc.doc_title,
                    "doc_short_summary": file_doc.doc_short_summary,
                    "doc_tags": file_doc.doc_tags,
                    "doc_datetime": file_doc.doc_datetime,
                    "is_processed_with_ai": 1
                })
            frappe.db.commit()

    return {
        "status": "Success",
        "title": metadata.get("title", ""),
        "summary": metadata.get("summary", ""),
        "tags": metadata.get("tags", []),
        "datetime": file_doc.doc_datetime if file_doc else metadata.get("date", ""),
        "usage": metadata.get("_usage", {})
    }


def should_auto_process_file(doc):
    if not doc.is_processed_with_ai:
        return False

    if doc.is_new():
        return True

    doc_before_save = doc.get_doc_before_save()
    if not doc_before_save:
        return True

    if doc.is_processed_with_ai and not doc_before_save.is_processed_with_ai:
        return True

    if doc.file_url != doc_before_save.file_url:
        return True

    if not doc.doc_title:
        return True

    return False


def auto_process_file_with_ai(doc, method=None):
    try:
        if not should_auto_process_file(doc):
            return

        process_file_with_ai(doc, save=False)
    except Exception as e:
        frappe.log_error(title="Auto Process File AI Error", message=str(e))


@frappe.whitelist()
def process_file(file_name, prompt=None, ai_provider=None):
    return process_file_with_ai(file_name, prompt=prompt, ai_provider=ai_provider, save=True)
