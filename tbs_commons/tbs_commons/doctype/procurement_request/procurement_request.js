// Copyright (c) 2026, Peter and contributors
// For license information, please see license.txt

const MAKE_MATERIAL_REQUEST =
	"tbsapp.tbs_app.doctype.procurement_request.procurement_request.make_material_request";

frappe.ui.form.on("Procurement Request", {
	setup(frm) {
		// item_code is optional here, but when one is given it should be a live item.
		frm.set_query("item_code", "items", () => ({ filters: { disabled: 0 } }));
	},

	refresh(frm) {
		if (frm.doc.docstatus !== 1) {
			return;
		}

		close_the_item_list(frm);

		// The same gate `make_material_request` applies server-side: approval has
		// happened, and something is still left to order. `per_ordered` is a
		// virtual field, so this reads the count as of this form load.
		const approved = ["Approved", "Partially Ordered"].includes(frm.doc.status);
		if (!approved || flt(frm.doc.per_ordered) >= 100) {
			return;
		}

		if (!frappe.model.can_create("Material Request")) {
			return;
		}

		// Everything still outstanding comes over, and the buyer adjusts the
		// quantities and drops what they are not ordering yet on the Material
		// Request itself -- where the warehouse and the stock rules are anyway.
		// Ticking rows in the grid first narrows it to those: `open_mapped_doc`
		// sends the selection along.
		frm.add_custom_button(
			__("Material Request"),
			() => {
				// Nothing returned on purpose: Frappe disables the button until
				// whatever a handler returns settles, and what this returns is a
				// jqXHR, which has no `finally` for it to wait on.
				frappe.model.open_mapped_doc({ method: MAKE_MATERIAL_REQUEST, frm: frm });
			},
			__("Create")
		);
		frm.page.set_inner_btn_group_as_primary(__("Create"));
	},

	schedule_date(frm) {
		// Fill the blanks only. A row that names its own date meant it.
		if (!frm.doc.schedule_date) {
			return;
		}

		(frm.doc.items || [])
			.filter((row) => !row.schedule_date)
			.forEach((row) =>
				frappe.model.set_value(row.doctype, row.name, "schedule_date", frm.doc.schedule_date)
			);
	},
});

frappe.ui.form.on("Procurement Request Item", {
	qty: (frm, cdt, cdn) => set_estimates(frm, cdt, cdn),
	estimated_rate: (frm, cdt, cdn) => set_estimates(frm, cdt, cdn),
	items_remove: (frm) => set_totals(frm),

	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code) {
			return;
		}
		if (!row.schedule_date) {
			frappe.model.set_value(cdt, cdn, "schedule_date", frm.doc.schedule_date);
		}
	},
});

// A preview of what the server recomputes on save, so an approver sees the
// number move as they type.
function set_estimates(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "estimated_amount", flt(row.qty) * flt(row.estimated_rate));
	set_totals(frm);
}

function set_totals(frm) {
	const items = frm.doc.items || [];
	frm.set_value(
		"total_qty",
		items.reduce((total, row) => total + flt(row.qty), 0)
	);
	frm.set_value(
		"total_estimated_cost",
		items.reduce((total, row) => total + flt(row.estimated_amount), 0)
	);
}

// `allow_on_submit` on the items table is what keeps the Item Code fillable
// after approval. It also hands the grid back its add and remove buttons, which
// an approved list of things has no business showing -- the server refuses both
// either way, so this is about not offering them.
function close_the_item_list(frm) {
	frm.set_df_property("items", "cannot_add_rows", true);
	frm.set_df_property("items", "cannot_delete_rows", true);
}
