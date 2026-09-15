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
					__("Annual budget: {0} · Spent: {1} · Committed: {2} · Remaining: {3} · Open requests: {4}",
						[budget.annual, budget.spent, budget.committed, budget.remaining, budget.open_requests].map(money)),
					frm.doc.docstatus === 0 && budget.amount > budget.remaining ? "orange" : "blue"
				);
			},
		});
	},
});
