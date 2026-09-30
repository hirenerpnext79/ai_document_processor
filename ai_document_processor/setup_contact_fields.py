import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def setup_fields():
    custom_fields = {
        "Contact": [
            {
                "fieldname": "ai_id_document",
                "label": "AI ID Document",
                "fieldtype": "Attach Image",
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
    create_custom_fields(custom_fields)
    print("Custom fields created successfully.")

