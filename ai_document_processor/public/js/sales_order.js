frappe.ui.form.on('Sales Order', {
    before_save: function(frm) {
        if (frm.doc.ai_po_document && (frm.is_new() || frm.doc.ai_po_document !== frm.doc.__onload?.ai_po_document)) {
            setTimeout(() => {
                if ($('.freeze-message').length) {
                    $('.freeze-message').text(__('AI Document Processing....'));
                }
            }, 50);
        }
    }
});
