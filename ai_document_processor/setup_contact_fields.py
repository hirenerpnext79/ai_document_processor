import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def sync_custom_field_types(custom_fields):
    try:
        for dt, fields in custom_fields.items():
            for field in fields:
                fieldname = field.get("fieldname")
                target_fieldtype = field.get("fieldtype")
                if not fieldname or not target_fieldtype:
                    continue

                existing = frappe.db.get_value(
                    "Custom Field",
                    {"dt": dt, "fieldname": fieldname},
                    ["name", "fieldtype"],
                    as_dict=True,
                )
                if existing and existing.fieldtype != target_fieldtype:
                    frappe.db.set_value(
                        "Custom Field",
                        existing.name,
                        "fieldtype",
                        target_fieldtype,
                        update_modified=False,
                    )
                    frappe.clear_cache(doctype=dt)
    except Exception as e:
        frappe.log_error(f"Error syncing custom field types: {str(e)}", "sync_custom_field_types")


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
                "read_only": 1
            },
            {
                "fieldname": "token_usage",
                "label": "Token Usage",
                "fieldtype": "JSON",
                "insert_after": "visiting_card_address",
                "read_only": 1
            }
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
                "read_only": 1
            }
        ]
    }
    sync_custom_field_types(custom_fields)
    create_custom_fields(custom_fields)
    print("Custom fields created successfully.")

