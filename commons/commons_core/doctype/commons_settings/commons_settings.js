// Data Sync tab: copy the default rules into the table to start editing from.
// The rows are only a draft until the form is saved.
frappe.ui.form.on("Commons Settings", {
	async data_sync_fill_defaults(frm) {
		const rows = await frappe.xcall("commons.data_sync.rules.defaults");
		const have = new Set((frm.doc.data_sync_doctypes || []).map((r) => r.document_type));
		const missing = rows.filter((r) => !have.has(r.document_type));
		if (!missing.length) {
			frappe.show_alert({
				message: __("Every default doctype is already listed."),
				indicator: "blue",
			});
			return;
		}
		missing.forEach((row) => frm.add_child("data_sync_doctypes", row));
		frm.refresh_field("data_sync_doctypes");
		frm.dirty();
		frappe.show_alert({
			message: __("Added {0} doctypes. Save to keep them.", [missing.length]),
			indicator: "green",
		});
	},
});
