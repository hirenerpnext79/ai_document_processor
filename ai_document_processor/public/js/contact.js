frappe.ui.form.on('Contact', {
    before_save: function(frm) {
        if (frm.doc.ai_id_document && (frm.is_new() || frm.doc.ai_id_document !== frm.doc.__onload?.ai_id_document)) {
            setTimeout(() => {
                if ($('.freeze-message').length) {
                    $('.freeze-message').text(__('AI Document Processing....'));
                }
            }, 50);
        }
    }
});
