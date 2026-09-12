// The POS Extra Fields picker offers whatever Sales Order and Sales Invoice have in
// common ON THIS SITE, so the list cannot live in the doctype as static Select options.
// It shipped as a Select with no options at all, which rendered an empty, unpickable,
// required dropdown. The candidates were already computed server-side and already
// whitelisted - nothing ever handed them to the form.
async function loadExtraFieldCandidates(frm) {
    const grid = frm.fields_dict.custom_pos_extra_fields?.grid;
    if (!grid) return;

    try {
        const { message } = await frappe.call({
            method: 'klik_pos.api.pos_profile.get_pos_extra_field_candidates',
        });
        const options = (message || []).map((f) => ({
            value: f.fieldname,
            label: f.label || f.fieldname,
            description: f.fieldname,
        }));
        if (!options.length) return;

        // Also reaches rows added later: update_docfield_property writes the parent
        // docfields, which every new grid row is built from.
        grid.update_docfield_property('so_si_commonfield', 'options', options);
        frm.refresh_field('custom_pos_extra_fields');
    } catch (e) {
        console.error('klik_pos: could not load POS extra field candidates', e);
    }
}

frappe.ui.form.on('POS Profile', {
    onload(frm) {
        loadExtraFieldCandidates(frm);
    },

    hide_images(frm) {
        if (!frm.doc.custom_default_view) {
            frm.set_value('custom_default_view', frm.doc.hide_images ? 'List View' : 'Grid View');
        }
    },

    refresh(frm) {
        frm.add_custom_button(__('Install Walk-in Party Fields'), () => {
            frappe.confirm(
                __('Add Walk-in Name / Tax ID / Phone fields to Quotation, Sales Order, Delivery Note and Sales Invoice?'),
                () => {
                    frappe.call({
                        method: 'klik_pos.setup.walkin_fields.install_walkin_party_fields',
                        freeze: true,
                        freeze_message: __('Installing walk-in fields...'),
                        callback: (r) => {
                            if (!r.exc) {
                                frappe.show_alert({
                                    message: __('Walk-in fields installed on: {0}',
                                        [(r.message.installed_on || []).join(', ')]),
                                    indicator: 'green',
                                });
                            }
                        },
                    });
                }
            );
        }, __('Setup'));
    }
});