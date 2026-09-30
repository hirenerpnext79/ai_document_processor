frappe.ui.form.on('AI Document', {
    onload: function(frm) {
        frm.set_query("provider", function() {
            return {
                query: "ai_document_processor.api.get_provider_query"
            };
        });
        
        if (!frm.doc.provider && frm.is_new()) {
            frappe.call({
                method: "ai_document_processor.api.get_default_ai_provider",
                callback: function(r) {
                    if (r.message) {
                        frm.set_value("provider", r.message);
                    }
                }
            });
        }
    },
    refresh: function (frm) {
        if (!frm.is_new() && frm.doc.pdf_file && frm.doc.provider && frm.doc.prompt && ['Pending', 'Failed'].includes(frm.doc.status)) {
            frm.add_custom_button(__('Generate AI Response'), function () {
                frappe.call({
                    method: 'ai_document_processor.ai_document_processor.api.enqueue_generate_response',
                    args: {
                        docname: frm.doc.name
                    },
                    freeze: true,
                    freeze_message: __('Queuing Document for AI Processing...'),
                    callback: function (r) {
                        if (!r.exc) {
                            frappe.msgprint(__('AI Processing has been queued in the background! Please refresh after a while.'));
                            frm.reload_doc();
                        }
                    }
                });
            }).addClass('btn-primary');
        }
    }
});
