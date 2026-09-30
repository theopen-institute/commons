// Where a lending voucher's GL is not on the voucher's own date, whether the
// scripts that keep it there are in place, and the repair for repayments. Both
// checks run by default and share one list; the Check filter narrows it to one.
// Every repair opens a dialog that shows what will change and writes only on
// its button; nothing on the report itself writes.

const ALL = "All";
const DATES = "GL dates";
const SAFEGUARDS = "Safeguards";
const GL_DATE = "GL not on the voucher's date";
const API = "commons.banking.loan_dates.";
const CAN_REPAIR = () => frappe.user.has_role(["Accounts Manager", "System Manager"]);
const STATUS_COLOR = { OK: "green", Missing: "red", "Not covered": "orange", "Wrong date": "red" };

frappe.query_reports["Loan Date Audit"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "view",
			label: __("Check"),
			fieldtype: "Select",
			options: [ALL, DATES, SAFEGUARDS].join("\n"),
			default: ALL,
			reqd: 1,
		},
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
		{
			fieldname: "voucher_type",
			label: __("Voucher Type"),
			fieldtype: "Select",
			options: ["", "Loan Repayment", "Loan Write Off", "Loan Disbursement"].join("\n"),
		},
		{
			fieldname: "loan",
			label: __("Loan"),
			fieldtype: "Link",
			options: "Loan",
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company") },
			}),
		},
	],

	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "status" && data && data.status) {
			const color = STATUS_COLOR[data.status] || "gray";
			return `<span class="indicator-pill ${color}">${esc(data.status)}</span>`;
		}
		if (column.fieldname === "action" && data && data.voucher_no) {
			return `<button class="btn btn-xs btn-default lda-review"
				data-voucher-type="${esc(data.voucher_type)}"
				data-voucher-no="${esc(data.voucher_no)}"
				data-issue="${esc(data.issue)}">${__("Review")}</button>`;
		}
		return default_formatter(value, row, column, data);
	},

	onload(report) {
		$(report.page.wrapper).on("click", ".lda-review", (e) => {
			const { voucherType, voucherNo, issue } = e.currentTarget.dataset;
			if (voucherType === "Loan Repayment" && issue === GL_DATE && CAN_REPAIR()) {
				review_repayment(report, voucherNo);
			} else {
				explain(voucherType, voucherNo, issue);
			}
		});
		if (CAN_REPAIR()) {
			report.page.add_inner_button(__("Re-book All Shown…"), () => repair_all(report));
		}
	},
};

const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
const money = (v) => format_number(v || 0, null, 2);
const link = (doctype, name) =>
	`<a href="/app/${frappe.router.slug(doctype)}/${encodeURIComponent(
		name
	)}" target="_blank">${esc(name)}</a>`;

function table(headers, rows) {
	if (!rows.length) return `<p class="text-muted">${__("None")}</p>`;
	return `<table class="table table-bordered table-sm" style="font-size: var(--text-sm)">
		<thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>
		<tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody>
	</table>`;
}

function review_repayment(report, voucher_no) {
	frappe.call(API + "preview_repair", { voucher_no }).then(({ message: plan }) => {
		const d = new frappe.ui.Dialog({
			title: __("Re-book {0}", [voucher_no]),
			size: "large",
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
			primary_action_label: __("Re-book on {0}", [frappe.datetime.str_to_user(plan.date)]),
			primary_action() {
				d.disable_primary_action();
				frappe
					.call({ method: API + "repair_repayment", args: { voucher_no }, freeze: true })
					.then(() => {
						d.hide();
						frappe.show_alert({
							message: __("{0} re-booked", [voucher_no]),
							indicator: "green",
						});
						report.refresh();
					})
					.catch(() => d.enable_primary_action());
			},
		});
		d.fields_dict.body.$wrapper.html(`
			<p>${__("Loan Repayment {0} is for {1}. Its live GL:", [
				link("Loan Repayment", voucher_no),
				esc(frappe.datetime.str_to_user(plan.date)),
			])}</p>
			${table(
				[__("Date"), __("Account"), __("Debit"), __("Credit")],
				plan.gl.map((g) => [
					esc(frappe.datetime.str_to_user(g.posting_date)),
					esc(g.account),
					`<div class="text-right">${money(g.debit)}</div>`,
					`<div class="text-right">${money(g.credit)}</div>`,
				])
			)}
			${
				!plan.needed
					? `<p>${__("It is all on the repayment's date now.")}</p>`
					: plan.refused
					? `<div class="alert alert-warning">${esc(plan.refused)}</div>`
					: `<p class="text-muted small">${__(
							"Re-booking cancels these entries and books them again from the repayment, on {0}, as the repost script does. Amounts and accounts do not change. A comment is added to the repayment.",
							[esc(frappe.datetime.str_to_user(plan.date))]
					  )}</p>`
			}`);
		if (!plan.needed || plan.refused) d.get_primary_btn().hide();
		d.show();
	});
}

function explain(voucher_type, voucher_no, issue) {
	const why = {
		"Posting date is not the value date": __(
			"The repayment's posting date is not the date it is for, so the posting-date scripts were not working when it was saved. Lending books GL from the posting date, and a submitted document's posting date can't be edited, so this needs a person: cancel and amend it with the scripts in place."
		),
		"GFL income entry not on the repayment's date": __(
			"The Good Faith Loan income journal was booked on another day than the repayment. It is its own journal entry: cancel and amend it to the repayment's date."
		),
	}[issue];
	frappe.msgprint({
		title: esc(voucher_no),
		indicator: "orange",
		message: `<p>${esc(voucher_type)} ${link(voucher_type, voucher_no)}: ${esc(issue)}.</p>
			<p>${
				why ||
				__(
					"Lending dates a {0}'s GL on the day it is submitted, so booking it again would not move it. Cancel and amend it, or correct it with a journal entry.",
					[esc(voucher_type)]
				)
			}</p>`,
	});
}

function repair_all(report) {
	const rows = (frappe.query_report.data || []).filter(
		(r) => r.check === DATES && r.voucher_type === "Loan Repayment" && r.issue === GL_DATE
	);
	if (!rows.length) {
		frappe.msgprint(__("No repayments to re-book are shown."));
		return;
	}
	const vouchers = [...new Set(rows.map((r) => r.voucher_no))];
	frappe.confirm(
		__(
			"Re-book the GL of {0} repayment(s) on their own dates? Each is checked again on the server; any whose posting date is not its value date is skipped.",
			[vouchers.length]
		),
		() => {
			frappe
				.call({ method: API + "repair_repayments", args: { vouchers }, freeze: true })
				.then(({ message: results }) => {
					frappe.msgprint({
						title: __("Re-booked"),
						message: table(
							[__("Repayment"), __("Result")],
							results.map((r) => [
								esc(r.voucher_no),
								r.status === "failed"
									? `<span class="text-danger">${esc(r.error)}</span>`
									: esc(r.status),
							])
						),
					});
					report.refresh();
				});
		}
	);
}
