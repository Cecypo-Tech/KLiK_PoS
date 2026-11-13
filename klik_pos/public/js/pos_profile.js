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

// The line panel list offers the built-in facts plus every field Item has ON THIS SITE
// (custom ones included), so its choices come from the server, like the extra fields above.
let lineInfoDefaults = [];
async function loadLineInfoChoices(frm) {
    const grid = frm.fields_dict.custom_line_info?.grid;
    if (!grid) return;
    try {
        const { message } = await frappe.call({ method: 'klik_pos.api.item.line_info.get_line_info_choices' });
        if (!message) return;
        lineInfoDefaults = message.defaults || [];
        const options = [...message.builtins, ...message.item_fields].map((f) => ({
            value: f.value,
            label: f.label,
            description: f.value,
        }));
        grid.update_docfield_property('info', 'options', options);
        frm.refresh_field('custom_line_info');
    } catch (e) {
        console.error('klik_pos: could not load line panel choices', e);
    }
}

function addLineInfoResetButton(frm) {
    const field = frm.fields_dict.custom_line_info;
    if (!field || field.$wrapper.find('.klik-line-info-reset').length) return;
    $(`<button class="btn btn-xs btn-default klik-line-info-reset" style="margin-bottom: 8px">${__('Reset to default')}</button>`)
        .prependTo(field.$wrapper)
        .on('click', () => {
            if (!lineInfoDefaults.length) return;
            frm.clear_table('custom_line_info');
            lineInfoDefaults.forEach((info) => frm.add_child('custom_line_info', { info }));
            frm.refresh_field('custom_line_info');
            frm.dirty();
        });
}

frappe.ui.form.on('POS Profile', {
    onload(frm) {
        loadExtraFieldCandidates(frm);
        loadLineInfoChoices(frm);
    },

    hide_images(frm) {
        if (!frm.doc.custom_default_view) {
            frm.set_value('custom_default_view', frm.doc.hide_images ? 'List View' : 'Grid View');
        }
    },

    refresh(frm) {
        addLineInfoResetButton(frm);
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