// "Create Payment Entries" on a submitted payroll run: a draft Payment Entry
// for each employee picked, for what the run still owes them. Shown only once
// the run's accrual journal is submitted, while somebody is unpaid and with
// Payroll Settings' "Process Payroll Accounting Entry Based on Employee" on --
// the server answers with nobody otherwise. The Mode of Payment and Reference
// No it starts on are Commons Settings'. See `commons.banking.payroll_payments`.

frappe.ui.form.on("Payroll Entry", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || !frm.doc.salary_slips_submitted) return;
		if (!frappe.model.can_create("Payment Entry")) return;
		frappe
			.call("commons.banking.payroll_payments.get_unpaid_salaries", {
				payroll_entry: frm.doc.name,
			})
			.then(({ message }) => {
				if (!message?.employees?.length) return;
				frm.add_custom_button(__("Create Payment Entries"), () =>
					open_payments_dialog(frm, message)
				);
			});
	},
});

function open_payments_dialog(frm, unpaid) {
	const money = (v) => format_currency(v, frm.doc.currency);
	const rows = unpaid.employees
		.map(
			(e) => `<tr>
				<td><input type="checkbox" class="pay-employee" data-employee="${frappe.utils.escape_html(
					e.employee
				)}"
					${e.draft ? "disabled" : "checked"}></td>
				<td>${frappe.utils.escape_html(e.employee_name || e.employee)}
					<div class="text-muted small">${frappe.utils.escape_html(e.employee)}</div></td>
				<td class="text-right">${money(e.amount)}</td>
				<td>${e.draft ? frappe.utils.get_form_link("Payment Entry", e.draft, true) : ""}</td>
			</tr>`
		)
		.join("");

	const dialog = new frappe.ui.Dialog({
		title: __("Create Payment Entries"),
		size: "large",
		fields: [
			{
				fieldtype: "Date",
				fieldname: "posting_date",
				label: __("Posting Date"),
				default: frappe.datetime.get_today(),
				reqd: 1,
			},
			{
				fieldtype: "Link",
				fieldname: "mode_of_payment",
				label: __("Mode of Payment"),
				options: "Mode of Payment",
				default: unpaid.mode_of_payment,
			},
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Link",
				fieldname: "paid_from",
				label: __("Paid From"),
				options: "Account",
				default: unpaid.paid_from,
				reqd: 1,
				// `this` is the control; its layout is the dialog, which may
				// not be assigned yet when a default first fires this.
				onchange() {
					require_reference_for_bank(this.layout);
				},
				get_query: () => ({
					filters: {
						company: unpaid.company,
						account_type: ["in", ["Bank", "Cash"]],
						is_group: 0,
					},
				}),
			},
			{
				fieldtype: "Data",
				fieldname: "reference_no",
				label: __("Reference No"),
				default: unpaid.reference_no,
			},
			{ fieldtype: "Section Break" },
			{
				fieldtype: "HTML",
				fieldname: "employees",
				options: `<p class="text-muted">${__(
					"One draft Payment Entry per employee, for what this run still owes them. Employees with a draft already are left out."
				)}</p>
				<table class="table table-bordered">
					<thead><tr><th></th><th>${__("Employee")}</th><th class="text-right">${__("Owed")}</th><th>${__(
					"Draft"
				)}</th></tr></thead>
					<tbody>${rows}</tbody>
				</table>`,
			},
		],
		primary_action_label: __("Create"),
		primary_action(values) {
			const employees = [...dialog.$wrapper.find(".pay-employee:checked")].map(
				(el) => el.dataset.employee
			);
			if (!employees.length) {
				frappe.msgprint(__("Pick at least one employee."));
				return;
			}
			frappe
				.call({
					method: "commons.banking.payroll_payments.make_salary_payments",
					args: { payroll_entry: frm.doc.name, employees, ...values },
					freeze: true,
					freeze_message: __("Creating Payment Entries..."),
				})
				.then(({ message }) => {
					dialog.hide();
					frappe.msgprint({
						title: __("Draft Payment Entries"),
						message: message
							.map((name) => frappe.utils.get_form_link("Payment Entry", name, true))
							.join("<br>"),
						indicator: "green",
					});
					frm.reload_doc();
				});
		},
	});
	dialog.show();
	require_reference_for_bank(dialog);
}

// ERPNext refuses a payment from a Bank account without a Reference No
// (`PaymentEntry.validate_transaction_reference`), so the dialog asks for one
// before the drafts are made rather than failing on the first of them.
function require_reference_for_bank(dialog) {
	if (!dialog?.get_value) return;
	const account = dialog.get_value("paid_from");
	const set = (is_bank) => dialog.set_df_property("reference_no", "reqd", is_bank ? 1 : 0);
	if (!account) return set(false);
	frappe.db
		.get_value("Account", account, "account_type")
		.then(({ message }) => set(message?.account_type === "Bank"));
}
