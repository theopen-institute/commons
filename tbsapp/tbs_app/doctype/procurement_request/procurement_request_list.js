// Copyright (c) 2026, Peter and contributors
// For license information, please see license.txt

frappe.listview_settings["Procurement Request"] = {
	// No `per_ordered`: it is a virtual field, counted per document, and a
	// list query can only ask for columns.
	add_fields: ["status", "transaction_date"],

	get_indicator(doc) {
		const colours = {
			Draft: "red",
			"Pending Approval": "orange",
			Approved: "blue",
			Rejected: "red",
			"Partially Ordered": "yellow",
			Ordered: "green",
			Cancelled: "grey",
		};

		return [__(doc.status), colours[doc.status] || "grey", `status,=,${doc.status}`];
	},
};
