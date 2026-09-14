frappe.ui.form.on('Sales Order', {
    refresh(frm) {
        frm.add_custom_button(__('AI Extract'), async () => {
            await frm.cscript.perform_ai_extraction(frm);
        });
    },


    async perform_ai_extraction(frm) {
        if (frm._is_extracting) return;
        
        const file_url = frm.doc.po_document;
        const ai_provider = frm.doc.ai_provider;

        if (!ai_provider) {
            frappe.msgprint(__('Please select an AI Provider first.'));
            return;
        }

        try {
            frm._is_extracting = true;
            frappe.dom.freeze(__('Extracting data...'));

            const { message } = await frappe.call({
                method: 'ai_document_processor.api.process_sales_order_document',
                args: {
                    file_url: file_url,
                    ai_provider: ai_provider
                },
            });

            if (!message || Object.keys(message).length === 0) {
                frappe.msgprint(__('No data could be extracted.'));
                return;
            }

            for (const [fieldname, value] of Object.entries(message)) {
                if (!value) continue;

                if (fieldname === 'items' && Array.isArray(value)) {
                    frm.clear_table('items');
                    for (const item of value) {
                        if (item.item_code || item.item_name || item.description) {
                            let row = frm.add_child('items');
                            if (item.item_code) row.item_code = item.item_code;
                            if (item.delivery_date) row.delivery_date = item.delivery_date;
                            if (item.item_name) row.item_name = item.item_name;
                            if (item.description) row.description = item.description;
                            if (item.qty) row.qty = item.qty;
                            if (item.uom) row.uom = item.uom;
                            if (item.rate) row.rate = item.rate;
                        }
                    }
                } else if (frm.fields_dict[fieldname] && !frm.doc[fieldname]) {
                    await frm.set_value(fieldname, value);
                }
            }

            frm.refresh_fields();

            frappe.show_alert({
                message: __('AI extraction completed'),
                indicator: 'green',
            });

        } catch (error) {
            console.error(error);
        } finally {
            frm._is_extracting = false;
            frappe.dom.unfreeze();
        }
    }
});
