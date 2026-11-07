frappe.ui.form.on('File', {
    refresh: function (frm) {
        toggle_prompt_field(frm);
        if (!frm.is_new() && frm.doc.file_url && !frm.doc.is_folder) {
            frm.add_custom_button(__('Process with AI'), function () {
                process_file_with_ai_action(frm);
            });
        }
    },
    is_processed_with_ai: function (frm) {
        toggle_prompt_field(frm);
    }
});

function toggle_prompt_field(frm) {
    const is_checked = Boolean(frm.doc.is_processed_with_ai);
    frm.toggle_display('prompt', is_checked);
}

function process_file_with_ai_action(frm) {
    frappe.call({
        method: 'ai_document_processor.file.process_file',
        args: {
            file_name: frm.doc.name,
            prompt: frm.doc.prompt || null
        },
        freeze: true,
        freeze_message: __('Processing File with AI...'),
        callback: function (r) {
            if (!r.exc && r.message && r.message.status === 'Success') {
                frappe.show_alert({
                    message: __('File metadata extracted successfully!'),
                    indicator: 'green'
                });
                frm.reload_doc();
            } else {
                const error_msg = (r.message && r.message.error) || __('AI processing failed. Check Error Log for details.');
                frappe.msgprint({
                    title: __('AI Processing Failed'),
                    message: error_msg,
                    indicator: 'red'
                });
            }
        }
    });
}
