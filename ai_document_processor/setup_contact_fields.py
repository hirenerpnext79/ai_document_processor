import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def setup_fields():
    custom_fields = {
        "Contact": [
            {
                "fieldname": "id_document",
                "label": "ID Document",
                "fieldtype": "Attach Image",
                "insert_after": "image",
            },
            {
                "fieldname": "ai_provider",
                "label": "AI Provider",
                "fieldtype": "Link",
                "options": "AI Provider",
                "insert_after": "id_document",
            }
        ]
    }
    create_custom_fields(custom_fields)
    print("Custom fields created successfully.")
