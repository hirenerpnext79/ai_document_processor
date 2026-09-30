import frappe
from frappe.model.document import Document

class AIProvider(Document):
    def validate(self):
        self.validate_defaults()

    def validate_defaults(self):
        access_list = self.get("access_list")
        if not access_list:
            return

        for access in access_list:
            if not access.is_default:
                continue
                
            if access.access_type == "User" and access.user:
                self.clear_other_defaults("User", access.user)
            elif access.access_type == "Role" and access.role:
                self.clear_other_defaults("Role", access.role)

    def clear_other_defaults(self, access_type, entity_name):
        field = "user" if access_type == "User" else "role"
        
        records = frappe.get_all(
            "AI Provider Access", 
            filters={
                "parent": ("!=", self.name),
                "access_type": access_type,
                field: entity_name,
                "is_default": 1
            }
        )
        
        for record in records:
            frappe.db.set_value("AI Provider Access", record.name, "is_default", 0)
