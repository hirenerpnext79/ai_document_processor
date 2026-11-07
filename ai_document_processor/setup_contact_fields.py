import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def sync_custom_field_properties(custom_fields):
    try:
        for dt, fields in custom_fields.items():
            for field in fields:
                fieldname = field.get("fieldname")
                if not fieldname:
                    continue

                existing = frappe.db.get_value(
                    "Custom Field",
                    {"dt": dt, "fieldname": fieldname},
                    ["name", "fieldtype", "depends_on", "insert_after"],
                    as_dict=True,
                )
                if not existing:
                    continue

                updates = {}
                target_fieldtype = field.get("fieldtype")
                if target_fieldtype and existing.fieldtype != target_fieldtype:
                    updates["fieldtype"] = target_fieldtype

                target_depends_on = field.get("depends_on", "")
                if (existing.depends_on or "") != target_depends_on:
                    updates["depends_on"] = target_depends_on

                target_insert_after = field.get("insert_after", "")
                if (existing.insert_after or "") != target_insert_after:
                    updates["insert_after"] = target_insert_after

                if updates:
                    frappe.db.set_value("Custom Field", existing.name, updates, update_modified=False)
                    frappe.clear_cache(doctype=dt)
    except Exception as e:
        frappe.log_error(title="Sync Custom Field Properties Error", message=str(e))


def setup_fields():
    custom_fields = {
        "Contact": [
            {
                "fieldname": "ai_id_document",
                "label": "AI ID Document",
                "fieldtype": "Attach",
                "insert_after": "image",
            },
            {
                "fieldname": "visiting_card_address",
                "label": "Visiting Card Address",
                "fieldtype": "Text",
                "insert_after": "address",
                "read_only": 1,
            },
            {
                "fieldname": "token_usage",
                "label": "Token Usage",
                "fieldtype": "JSON",
                "insert_after": "visiting_card_address",
                "read_only": 1,
            },
        ],
        "Sales Order": [
            {
                "fieldname": "ai_po_document",
                "label": "AI PO Document",
                "fieldtype": "Attach",
                "insert_after": "po_no",
            },
            {
                "fieldname": "token_usage",
                "label": "Token Usage",
                "fieldtype": "JSON",
                "insert_after": "po_document",
                "read_only": 1,
            },
        ],
        "File": [
            {
                "fieldname": "is_processed_with_ai",
                "label": "Is Processed With AI?",
                "fieldtype": "Check",
                "insert_after": "is_private",
                "in_list_view": 1,
                "in_standard_filter": 1,
            },
            {
                "fieldname": "prompt",
                "label": "Prompt",
                "fieldtype": "Link",
                "options": "AI Prompt",
                "insert_after": "is_processed_with_ai",
                "depends_on": "eval:doc.is_processed_with_ai",
            },
            {
                "fieldname": "ai_doc_info",
                "label": "AI Doc Info",
                "fieldtype": "Tab Break",
                "insert_after": "uploaded_to_google_drive",
            },
            {
                "fieldname": "doc_title",
                "label": "Doc Title",
                "fieldtype": "Data",
                "insert_after": "ai_doc_info",
                "read_only": 1,
            },
            {
                "fieldname": "doc_tags",
                "label": "Doc Tags",
                "fieldtype": "Long Text",
                "insert_after": "doc_title",
                "read_only": 1,
            },
            {
                "fieldname": "column_break_ai_info",
                "label": "",
                "fieldtype": "Column Break",
                "insert_after": "doc_tags",
            },
            {
                "fieldname": "doc_datetime",
                "label": "Doc Date/Time",
                "fieldtype": "Datetime",
                "insert_after": "column_break_ai_info",
                "read_only": 1,
            },
            {
                "fieldname": "doc_short_summary",
                "label": "Doc Short Summary",
                "fieldtype": "Small Text",
                "insert_after": "doc_datetime",
                "read_only": 1,
            },
        ],
    }
    sync_custom_field_properties(custom_fields)
    create_custom_fields(custom_fields)
