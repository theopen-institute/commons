frappe.ui.form.on("Material Request", {
	refresh(frm) {
		if (frm.is_new() || !["Purchase", "Material Issue"].includes(frm.doc.material_request_type)) return;
		frappe.call({
			method: "tbs_commons.procurement.budget.get_material_request_budget",
			args: { name: frm.doc.name },
			callback: ({ message: budget }) => {
				if (!budget) return;
				if (budget.missing || budget.inactive) {
					frm.dashboard.set_headline_alert(__("Finance must create and submit the department budget before this Material Request can be submitted."), "orange");
					return;
				}
				const money = (value) => format_currency(value, budget.currency);
				frm.dashboard.set_headline_alert(
					__("Budget: {0} · Submitted MR usage: {1} · Available: {2} · This MR: {3}",
						[budget.budget, budget.used, budget.available, budget.amount].map(money)),
					frm.doc.docstatus === 0 && budget.amount > budget.available ? "orange" : "blue"
				);
			},
		});
	},
});
