// Copyright (c) 2026, Peter and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bank Reconciliation Settings", {
	refresh(frm) {
		// Lending's repayment types, from the controller's `onload`. None on a
		// site without Lending, where the field takes what is typed. Handed to
		// the control as well as its docfield, because an Autocomplete reads
		// its options only when it first draws.
		const options = frm.doc.__onload?.repayment_types || [];
		frm.fields_dict.default_repayment_type.df.options = options;
		frm.fields_dict.default_repayment_type.set_data?.(options);
	},
});
