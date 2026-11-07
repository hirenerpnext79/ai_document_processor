from frappe.model.document import Document


class AIDocument(Document):
    def validate(self):
        if not self.document_type:
            self.document_type = "PDF"
