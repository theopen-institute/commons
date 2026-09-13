// Copyright (c) 2026, Peter and contributors
// For license information, please see license.txt

frappe.listview_settings["Procurement Request"] = {
	// No `per_ordered`: it is a virtual field, counted per document, and a
	// list query can only ask for columns.
	add_fields: ["status", "transaction_date", "requested_by", "approver", "department"],

	get_indicator(doc) {
		const colours = {
			Draft: "red",
			Pending: "orange",
			"Under Review": "blue",
			Approved: "blue",
			Rejected: "red",
			Completed: "green",
			Canceled: "grey",
		};

		return [__(doc.status), colours[doc.status] || "grey", `status,=,${doc.status}`];
	},
};
