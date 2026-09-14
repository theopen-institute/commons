
const MAKE_MATERIAL_REQUEST =
	"tbs_commons.procurement.doctype.procurement_request.procurement_request.make_material_request";

frappe.ui.form.on("Procurement Request", {
	setup(frm) {
		frm.set_query("item_code", "items", () => ({ filters: { disabled: 0 } }));
	},

	refresh(frm) {
		if (frm.doc.docstatus !== 1) {
			return;
		}

		// Everything asked for is already carried by a submitted Material
		// Request, so there is nothing left to map into a new one.
		if (!(frm.doc.items || []).some((row) => flt(row.uncommitted_qty) > 0)) {
			return;
		}

		if (!frappe.model.can_create("Material Request")) {
			return;
		}

		frm.add_custom_button(
			__("Material Request"),
			() => {
				frappe.model.open_mapped_doc({ method: MAKE_MATERIAL_REQUEST, frm: frm });
			},
			__("Create")
		);
		frm.page.set_inner_btn_group_as_primary(__("Create"));
	},
});

frappe.ui.form.on("Procurement Request Item", {
	reference_url(frm, cdt, cdn) {
		const link = with_scheme(locals[cdt][cdn].reference_url);
		if (link !== locals[cdt][cdn].reference_url) {
			frappe.model.set_value(cdt, cdn, "reference_url", link);
		}
	},

});

// Whitespace inside is the mark of something that was never a link. Left alone
// it fails the server's check, which is the answer wanted here -- adding a
// scheme would only turn a plain sentence into a passing "URL".
function with_scheme(url) {
	const link = (url || "").trim();
	if (!link || link.startsWith("/") || link.includes(" ")) return link;
	return /^[a-z][a-z0-9+.-]*:/i.test(link) ? link : `https://${link}`;
}