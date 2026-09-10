frappe.ui.form.on("Contact", {
    refresh(frm) {
        frm.add_custom_button(__("AI Extract"), async () => {
            const file_url = frm.doc.id_document;
            const ai_provider = frm.doc.ai_provider;

            try {
                frappe.dom.freeze(__("Extracting data..."));

                const { message } = await frappe.call({
                    method: "ai_document_processor.api.process_contact_document",
                    args: {
                        file_url: file_url,
                        ai_provider: ai_provider
                    },
                });

                if (!message || Object.keys(message).length === 0) {
                    frappe.msgprint(__("No data could be extracted."));
                    return;
                }

                for (const [fieldname, value] of Object.entries(message)) {
                    if (!value) continue;

                    if (fieldname === "email_ids" && Array.isArray(value)) {
                        frm.clear_table("email_ids");
                        for (const email of value) {
                            if (email) {
                                let row = frm.add_child("email_ids");
                                row.email_id = email;
                                row.is_primary = 1;
                            }
                        }
                    } else if (fieldname === "phone_nos" && Array.isArray(value)) {
                        frm.clear_table("phone_nos");
                        for (const phone of value) {
                            if (phone) {
                                let row = frm.add_child("phone_nos");
                                row.phone = phone;
                                row.is_primary_phone = 1;
                            }
                        }
                    } else if (frm.fields_dict[fieldname] && !frm.doc[fieldname]) {
                        await frm.set_value(fieldname, value);
                    }
                }

                frm.refresh_fields();

                frappe.show_alert({
                    message: __("AI extraction completed"),
                    indicator: "green",
                });

            } catch (error) {
                console.error(error);
                // Validation errors from python are automatically handled via frappe.msgprint
                // so we don't necessarily need another error msgprint here unless it's an unhandled exception.
            } finally {
                frappe.dom.unfreeze();
            }
        });
    },
});
