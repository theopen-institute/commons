// Copyright (c) 2026, Peter and contributors
// For license information, please see license.txt

const MAKE_MATERIAL_REQUEST =
	"tbs_commons.procurement.doctype.procurement_request.procurement_request.make_material_request";

frappe.ui.form.on("Procurement Request", {
	setup(frm) {
		// item_code is optional here, but when one is given it should be a live item.
		frm.set_query("item_code", "items", () => ({ filters: { disabled: 0 } }));
	},

	refresh(frm) {
		if (!frm.is_new()) {
			frappe.call({
				method: "tbs_commons.procurement.budget.get_request_budget",
				args: { name: frm.doc.name },
				callback: ({ message: budget }) => {
					if (!budget) return;
					if (budget.missing || budget.inactive) {
						frm.dashboard.set_headline_alert(__("No submitted department budget covers this period. Procurement approval can proceed; Material Request submission will require one."), "orange");
						return;
					}
					const money = (value) => format_currency(value, budget.currency);
					frm.dashboard.set_headline_alert(
						__("Budget: {0} · Submitted MR usage: {1} · Available: {2} · Outstanding procurement: {3} · Projected available: {4}",
							[budget.budget, budget.used, budget.available, budget.provisional, budget.projected_available].map(money)),
						budget.projected_available < 0 ? "orange" : "blue"
					);
				},
			});
		}
		if (frm.doc.docstatus !== 1) {
			return;
		}

		close_the_item_list(frm);

		// The same gate `make_material_request` applies server-side: approval has
		// happened, and something is still left to order. `per_ordered` is a
		// virtual field, so this reads the count as of this form load.
		const approved = frm.doc.status === "Approved";
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

});

frappe.ui.form.on("Procurement Request Item", {
	qty: (frm) => set_totals(frm),
	estimated_rate: (frm) => set_totals(frm),
	verified_rate: (frm) => set_totals(frm),
	items_add: (frm) => set_totals(frm),
	items_remove: (frm) => set_totals(frm),

	async item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const item_code = row.item_code;
		const lookup = (row.__buying_rate_lookup || 0) + 1;
		row.__buying_rate_lookup = lookup;
		await frappe.model.set_value(cdt, cdn, "verified_rate", 0);
		if (!item_code) return;

		const { message } = await frappe.call({
			method: "tbs_commons.procurement.doctype.procurement_request.procurement_request.get_verified_buying_price",
			args: {
				item_code,
				currency: frm.doc.currency,
				request: frm.is_new() ? null : frm.doc.name,
			},
		});
		// A slow response must not put another item's price on the current row.
		if (row.item_code === item_code && row.__buying_rate_lookup === lookup) {
			await frappe.model.set_value(cdt, cdn, {
				verified_rate: flt(message.verified_rate),
				uom: message.uom || row.uom,
			});
		}
	},
});

// Preview the virtual total as quantities and rates change.
function set_totals(frm) {
	const items = frm.doc.items || [];
	frm.set_value(
		"total_qty",
		items.reduce((total, row) => total + flt(row.qty), 0)
	);
	frm.set_value(
		"total_estimated_cost",
		items.reduce(
			(total, row) => total + flt(row.qty) * (flt(row.verified_rate) || flt(row.estimated_rate)),
			0
		)
	);
}

// A submitted request is a fixed list. Keep the grid controls closed even on
// sites whose cached metadata has not yet picked up that restriction.
function close_the_item_list(frm) {
	frm.set_df_property("items", "cannot_add_rows", true);
	frm.set_df_property("items", "cannot_delete_rows", true);
}
