import datetime
import glob
import json
import os
import re
import subprocess
import time
import frappe
from frappe import _
from frappe.model.document import BaseDocument
from frappe.utils import get_datetime, now_datetime
from ai_document_processor.api import get_default_ai_provider
from ai_document_processor.ai_services import generate
from .utils import extract_document_text, get_file_content, get_file_extension


def get_clean_error_message(exception_obj):
    if not exception_obj:
        return _("Unknown error occurred")

    try:
        data = exception_obj.response.json()
        err = data.get("error")
        if err:
            msg = err.get("message") if isinstance(err, dict) else str(err)
            code = err.get("code") if isinstance(err, dict) else exception_obj.response.status_code
            return f"{code}: {msg}"
    except Exception:
        pass

    return str(exception_obj)


def normalize_ai_metadata(data):
    if not isinstance(data, dict):
        return {}

    clean_keys = {re.sub(r"[\s_\-/]+", "", str(k)).lower(): v for k, v in data.items()}

    title = clean_keys.get("doctitle") or clean_keys.get("title") or clean_keys.get("name") or ""
    summary = clean_keys.get("docshortsummary") or clean_keys.get("summary") or clean_keys.get("description") or ""

    raw_tags = clean_keys.get("doctags") or clean_keys.get("tags") or clean_keys.get("keywords") or []
    if isinstance(raw_tags, str):
        tags = [t.strip() for t in re.split(r"[,;\n]+", raw_tags) if t.strip()]
    elif isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    else:
        tags = []

    date_val = clean_keys.get("docdatetime") or clean_keys.get("datetime") or clean_keys.get("date")

    normalized = {
        "title": str(title).strip(),
        "summary": str(summary).strip(),
        "tags": tags,
        "date": str(date_val).strip() if date_val else None,
    }

    if "_usage" in data:
        normalized["_usage"] = data["_usage"]

    if "_final_prompt" in data:
        normalized["_final_prompt"] = data["_final_prompt"]

    return normalized


def parse_ai_json_response(response_text):
    if not response_text:
        return {}

    clean_text = response_text.strip()
    if clean_text.startswith("```"):
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_text)
        if match:
            clean_text = match.group(1).strip()

    try:
        return normalize_ai_metadata(json.loads(clean_text))
    except Exception:
        pass

    first_brace = clean_text.find("{")
    last_brace = clean_text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            return normalize_ai_metadata(json.loads(clean_text[first_brace : last_brace + 1]))
        except Exception:
            pass

    fallback = {}
    for line in clean_text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fallback[k.strip()] = v.strip()

    return normalize_ai_metadata(fallback) if fallback else {}


def to_naive_datetime(dt):
    if not dt:
        return None

    try:
        if isinstance(dt, str):
            clean_str = dt.strip()
            try:
                dt = get_datetime(clean_str)
            except Exception:
                digits = re.sub(r"\D", "", clean_str[:16])
                if len(digits) >= 8:
                    dt = get_datetime(digits[:8])

        if isinstance(dt, datetime.datetime):
            if dt.tzinfo is not None:
                try:
                    from frappe.utils import convert_utc_to_system_timezone
                    dt = convert_utc_to_system_timezone(dt)
                except Exception:
                    try:
                        dt = dt.astimezone()
                    except Exception:
                        pass
                if getattr(dt, "tzinfo", None) is not None:
                    dt = dt.replace(tzinfo=None)
            return dt

        if isinstance(dt, datetime.date):
            return datetime.datetime.combine(dt, datetime.time.min)
    except Exception:
        pass

    return None


def parse_extracted_date(date_str):
    if not date_str:
        return None

    clean_str = str(date_str).strip()
    try:
        dt = get_datetime(clean_str)
        if dt:
            return to_naive_datetime(dt)
    except Exception:
        pass

    try:
        digits = re.sub(r"\D", "", clean_str[:16])
        if len(digits) >= 8:
            dt = get_datetime(digits[:8])
            if dt:
                return to_naive_datetime(dt)
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
    wb = None
    try:
        import io
        import openpyxl
        wb = openpyxl.load_workbook(filename=io.BytesIO(content), read_only=True)
        props = wb.properties
        if props:
            if props.created:
                return to_naive_datetime(props.created)
            if props.modified:
                return to_naive_datetime(props.modified)
    except Exception as e:
        frappe.log_error(title="Extract Excel Date Property Error", message=str(e))
    finally:
        if wb:
            wb.close()
    return None


def parse_image_exif_date(date_val):
    if not date_val:
        return None

    try:
        clean = str(date_val).strip()
        if re.match(r"^\d{4}:\d{2}:\d{2}", clean):
            clean = clean.replace(":", "-", 2)
        return to_naive_datetime(get_datetime(clean))
    except Exception:
        pass

    return parse_extracted_date(date_val)


def extract_image_doc_property_date(content):
    try:
        import io
        from PIL import Image

        img = Image.open(io.BytesIO(content))

        if hasattr(img, "_getexif"):
            try:
                raw_exif = img._getexif()
                if raw_exif:
                    for tag_id in [36867, 36868, 306]:
                        val = raw_exif.get(tag_id)
                        if val:
                            dt = parse_image_exif_date(val)
                            if dt:
                                return dt
            except Exception:
                pass

        if hasattr(img, "getexif"):
            try:
                exif = img.getexif()
                if exif:
                    for tag_id in [36867, 36868, 306]:
                        val = exif.get(tag_id)
                        if val:
                            dt = parse_image_exif_date(val)
                            if dt:
                                return dt

                    sub_ifd = exif.get_ifd(0x8769)
                    if sub_ifd:
                        for tag_id in [36867, 36868, 306]:
                            val = sub_ifd.get(tag_id)
                            if val:
                                dt = parse_image_exif_date(val)
                                if dt:
                                    return dt
            except Exception:
                pass

        info = getattr(img, "info", {}) or {}
        for key in ["Creation Time", "date:create", "date:modify", "timestamp"]:
            val = info.get(key)
            if val:
                dt = parse_extracted_date(val)
                if dt:
                    return dt
    except Exception as e:
        frappe.log_error(title="Extract Image Date Property Error", message=str(e))

    return None


def extract_openxml_doc_property_date(content):
    try:
        import io
        import zipfile
        import xml.etree.ElementTree as ET

        with zipfile.ZipFile(io.BytesIO(content)) as z:
            if "docProps/core.xml" in z.namelist():
                xml_data = z.read("docProps/core.xml")
                root = ET.fromstring(xml_data)
                for elem in root.iter():
                    if elem.tag.endswith("created") and elem.text:
                        dt = parse_extracted_date(elem.text.strip())
                        if dt:
                            return dt
                    if elem.tag.endswith("modified") and elem.text:
                        dt = parse_extracted_date(elem.text.strip())
                        if dt:
                            return dt
    except Exception as e:
        frappe.log_error(title="Extract OpenXML Date Property Error", message=str(e))

    return None


def get_windows_file_creation_time(file_name):
    if not file_name:
        return None

    try:
        patterns = []
        if os.name == "nt":
            user_profile = os.environ.get("USERPROFILE", "")
            if user_profile:
                for folder in ["Downloads", "Desktop", "Pictures", "Documents"]:
                    patterns.append(os.path.join(user_profile, folder, file_name))
        else:
            for folder in ["Downloads", "Desktop", "Pictures", "Documents"]:
                patterns.append(f"/mnt/c/Users/*/{folder}/{file_name}")

        candidates = []
        for pat in patterns:
            if "*" in pat:
                candidates.extend(glob.glob(pat))
            elif os.path.exists(pat):
                candidates.append(pat)

        for cand in candidates:
            if os.path.exists(cand):
                if os.name == "nt":
                    st = os.stat(cand)
                    return datetime.datetime.fromtimestamp(st.st_ctime)

                win_path = cand.replace("/mnt/c/", "C:\\").replace("/", "\\")
                cmd = [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    f"(Get-Item '{win_path}').CreationTime.ToString('yyyy-MM-dd HH:mm:ss')",
                ]
                out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
                if out:
                    return get_datetime(out)
    except Exception as e:
        frappe.log_error(title="Get Windows Creation Time Error", message=str(e))

    return None


def get_disk_file_time(file_url):
    if not file_url:
        return None

    try:
        full_path = None
        if frappe.db.exists("File", {"file_url": file_url}):
            f_doc = frappe.get_doc("File", {"file_url": file_url})
            try:
                p = f_doc.get_full_path()
                if p and os.path.exists(p):
                    full_path = p
            except Exception:
                pass

        if not full_path:
            clean_path = str(file_url).lstrip("/")
            for prefix in ["public", "private", ""]:
                p = frappe.get_site_path(prefix, clean_path) if prefix else frappe.get_site_path(clean_path)
                if os.path.exists(p) and os.path.isfile(p):
                    full_path = p
                    break

        if full_path and os.path.exists(full_path):
            try:
                out = subprocess.check_output(
                    ["stat", "-c", "%w", full_path],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
                if out and out != "-":
                    dt = parse_extracted_date(out[:19])
                    if dt:
                        return dt
            except Exception:
                pass

            st = os.stat(full_path)
            if hasattr(st, "st_birthtime"):
                return datetime.datetime.fromtimestamp(st.st_birthtime)
            return datetime.datetime.fromtimestamp(st.st_mtime)
    except Exception as e:
        frappe.log_error(title="Get Disk File Time Error", message=str(e))

    return None


def extract_actual_doc_created_date(file_url, content=None, file_name=None):
    if not content:
        content = get_file_content(file_url)

    ext = get_file_extension(file_url)
    if content:
        if ext == ".pdf":
            dt = extract_pdf_doc_property_date(content)
            if dt:
                return to_naive_datetime(dt)
        elif ext in [".xlsx", ".xlsm"]:
            dt = extract_excel_doc_property_date(content)
            if dt:
                return to_naive_datetime(dt)
        elif ext in [".docx", ".pptx"]:
            dt = extract_openxml_doc_property_date(content)
            if dt:
                return to_naive_datetime(dt)
        elif ext in [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif"]:
            dt = extract_image_doc_property_date(content)
            if dt:
                return to_naive_datetime(dt)

    check_name = file_name or (os.path.basename(file_url) if file_url else None)
    if check_name:
        win_dt = get_windows_file_creation_time(check_name)
        if win_dt:
            return to_naive_datetime(win_dt)

    disk_date = get_disk_file_time(file_url)
    if disk_date:
        return to_naive_datetime(disk_date)

    return None


def resolve_doc_datetime(file_url, ai_date_str=None, file_doc=None, content=None, **kwargs):
    file_name = file_doc.file_name if file_doc else None
    actual_doc_date = extract_actual_doc_created_date(file_url, content=content, file_name=file_name)
    if actual_doc_date:
        return to_naive_datetime(actual_doc_date)

    if ai_date_str:
        ai_dt = parse_extracted_date(ai_date_str)
        if ai_dt:
            return to_naive_datetime(ai_dt)

    if file_doc and file_doc.creation:
        return to_naive_datetime(file_doc.creation)

    try:
        return to_naive_datetime(now_datetime())
    except Exception:
        return datetime.datetime.now()


def get_ai_prompt(custom_prompt=None):
    if custom_prompt:
        return custom_prompt.strip()

    return (
        "Analyze the provided document text and extract the document metadata as JSON with "
        "doc_title, doc_short_summary, doc_tags, doc_date_time."
    )


def execute_file_ai_generation(file_url, custom_prompt=None, provider_name=None):
    try:
        extracted_text = extract_document_text(file_url)
    except Exception as e:
        err_msg = get_clean_error_message(e)
        frappe.log_error(title="File Text Extraction Failed", message=err_msg)
        return {"error": f"{_('Text Extraction Failed')}: {err_msg}"}

    if not extracted_text:
        return {"error": _("No readable text could be extracted from this document.")}

    ai_provider = provider_name or get_default_ai_provider()
    if not ai_provider:
        frappe.throw(_("No enabled AI Provider found"))

    provider_doc = frappe.get_doc("AI Provider", ai_provider)
    prompt_text = get_ai_prompt(custom_prompt)
    prompt_doc = frappe._dict(prompt=prompt_text)

    candidate_models = [provider_doc.model, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-lite-latest"]
    tried_models = set()
    last_error = None

    for model_name in candidate_models:
        if not model_name or model_name in tried_models:
            continue
        tried_models.add(model_name)
        provider_doc.model = model_name

        for attempt in range(2):
            try:
                ai_response_text, usage_metadata = generate(provider_doc, prompt_doc, extracted_text[:15000])
                parsed_data = parse_ai_json_response(ai_response_text)
                parsed_data["_usage"] = usage_metadata
                parsed_data["_final_prompt"] = prompt_text
                return parsed_data
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                if "429" in err_str or "quota" in err_str or "exhausted" in err_str:
                    break
                time.sleep(1)

    clean_err = get_clean_error_message(last_error)
    frappe.log_error(title="File AI Generation Failed", message=clean_err)
    return {"error": clean_err}


def apply_ai_metadata_to_file(doc, metadata, file_url=None):
    title = metadata.get("title", "")
    summary = metadata.get("summary", "")
    tags = metadata.get("tags", [])
    date_val = metadata.get("date", "")
    usage_data = metadata.get("_usage", {})

    formatted_tags = ", ".join(tags) if isinstance(tags, list) else str(tags)
    url = file_url or doc.file_url
    formatted_dt = resolve_doc_datetime(url, ai_date_str=date_val, file_doc=doc)

    doc.doc_title = title
    doc.doc_short_summary = summary
    doc.doc_tags = formatted_tags
    doc.doc_datetime = to_naive_datetime(formatted_dt)
    doc.is_processed_with_ai = 1
    doc.token_usage = json.dumps(usage_data, indent=2) if usage_data else ""


def resolve_file_doc(file_source):
    if isinstance(file_source, BaseDocument):
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
        return {"status": "Failed", "error": _("No file URL found")}

    raw_prompt = prompt or (file_doc.prompt if file_doc else None)
    selected_prompt = None
    if raw_prompt:
        selected_prompt = frappe.db.get_value("AI Prompt", raw_prompt, "prompt") or raw_prompt

    metadata = execute_file_ai_generation(file_url, custom_prompt=selected_prompt, provider_name=ai_provider)
    final_prompt = metadata.get("_final_prompt", selected_prompt) if metadata else selected_prompt
    if not metadata or metadata.get("error"):
        error_message = metadata.get("error") if metadata else _("AI could not generate metadata")
        return {
            "status": "Failed",
            "error": error_message,
            "prompt": final_prompt
        }

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
                    "doc_datetime": to_naive_datetime(file_doc.doc_datetime),
                    "token_usage": file_doc.token_usage,
                    "is_processed_with_ai": 1
                })
            frappe.db.commit()

    tags_result = (
        [t.strip() for t in file_doc.doc_tags.split(",") if t.strip()]
        if file_doc and file_doc.doc_tags
        else metadata.get("tags", [])
    )
    dt_result = str(to_naive_datetime(file_doc.doc_datetime)) if file_doc and file_doc.doc_datetime else str(resolve_doc_datetime(file_url, ai_date_str=metadata.get("date")))
    usage_data = metadata.get("_usage", {})

    return {
        "status": "Success",
        "title": file_doc.doc_title if file_doc else metadata.get("title", ""),
        "summary": file_doc.doc_short_summary if file_doc else metadata.get("summary", ""),
        "tags": tags_result,
        "datetime": dt_result,
        "prompt": final_prompt,
        "usage": usage_data,
        "token_usage": file_doc.token_usage if file_doc else usage_data
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

    return not doc.doc_title


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
