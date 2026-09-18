
const MAKE_MATERIAL_REQUEST =
	"tbs_commons.requests.doctype.procurement_request.procurement_request.make_material_request";
const GET_CONVERSION_FACTOR = "erpnext.stock.get_item_details.get_conversion_factor";

frappe.ui.form.on("Procurement Request", {
	setup(frm) {
		// Lets the Connections tab show a "+" next to Material Request: it
		// hands the click to the Create button added below, instead of the
		// generic new-doc dialog that would know nothing about the mapping.
		frm.custom_make_buttons = { "Material Request": "Material Request" };

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

		// The grid turns read-only on submit, and its refresh disables the row
		// tick boxes along with it -- but submitted is exactly when this button
		// runs. The boxes only choose which rows to carry over, they edit
		// nothing, so turn them back on. This runs after `refresh_fields`, so
		// it outlasts the grid refresh that disabled them.
		frm.fields_dict.items.grid.toggle_checkboxes(true);
	},
});

frappe.ui.form.on("Procurement Request Item", {
	async item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const item_code = row.item_code;

		// Clearing the code leaves the row as the requester typed it: a row with
		// no item is exactly the free-text line this doctype allows, and its
		// quantity, UOM and prices are the only description of it there is.
		if (!item_code) return;

		const requested_uom = row.uom;
		const requested_qty = flt(row.qty);
		const requested_rate = flt(row.estimated_rate);

		const item = (
			await frappe.db.get_value("Item", item_code, ["valuation_rate", "stock_uom"])
		).message;
		if (!item || row.item_code !== item_code) return;

		await frappe.model.set_value(cdt, cdn, "verified_rate", flt(item.valuation_rate));
		await frappe.model.set_value(cdt, cdn, "uom", item.stock_uom);

		if (!requested_uom || requested_uom === item.stock_uom) return;

		// Stock units per the UOM that was asked for. An item with no conversion
		// to the unit the requester used answers 1, which is also the answer for
		// a unit that really is one stock unit -- either way the numbers below
		// come out unchanged, so an unconvertible row keeps what was typed.
		const { message } = await frappe.call({
			method: GET_CONVERSION_FACTOR,
			args: { item_code: item_code, uom: requested_uom },
		});
		const factor = flt(message && message.conversion_factor);
		if (!factor || factor === 1 || row.item_code !== item_code) return;

		// The same request said a different way: more of a smaller unit, each
		// costing proportionally less, for the same quantity and the same money.
		await frappe.model.set_value(cdt, cdn, "qty", requested_qty * factor);
		await frappe.model.set_value(cdt, cdn, "estimated_rate", requested_rate / factor);
	},

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