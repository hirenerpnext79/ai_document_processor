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
    document_type: function(frm) {
        update_file_label(frm);
        validate_attachment_extension(frm);
    },
    pdf_file: function(frm) {
        validate_attachment_extension(frm);
    },
    refresh: function (frm) {
        update_file_label(frm);
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

function update_file_label(frm) {
    const doc_type = frm.doc.document_type || 'PDF';
    const label_map = {
        'PDF': __('PDF File'),
        'Image': __('Image File'),
        'Excel': __('Excel File')
    };
    const label = label_map[doc_type] || __('Document File');
    frm.set_df_property('pdf_file', 'label', label);
}

function validate_attachment_extension(frm) {
    if (!frm.doc.pdf_file) return;
    const clean_url = frm.doc.pdf_file.split('?')[0];
    const ext = clean_url.split('.').pop().toLowerCase();
    const doc_type = frm.doc.document_type || 'PDF';
    
    if (doc_type === 'PDF' && ext !== 'pdf') {
        frappe.msgprint({
            title: __('File Type Mismatch'),
            message: __('The uploaded file does not appear to be a PDF (.pdf).'),
            indicator: 'orange'
        });
    } else if (doc_type === 'Image' && !['png', 'jpg', 'jpeg', 'webp', 'bmp', 'tiff', 'tif', 'jfif', 'gif'].includes(ext)) {
        frappe.msgprint({
            title: __('File Type Mismatch'),
            message: __('The uploaded file does not appear to be an Image (.png, .jpg, .jpeg, etc.).'),
            indicator: 'orange'
        });
    } else if (doc_type === 'Excel' && !['xlsx', 'xls', 'xlsm', 'csv'].includes(ext)) {
        frappe.msgprint({
            title: __('File Type Mismatch'),
            message: __('The uploaded file does not appear to be an Excel file (.xlsx, .xls, .csv).'),
            indicator: 'orange'
        });
    }
}
