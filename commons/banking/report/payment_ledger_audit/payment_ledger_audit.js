// Where the payment ledger disagrees with the GL, and the repair. Every repair
// opens a dialog that shows what will change and writes only on its button;
// nothing on the report itself writes.

const LEDGER = "Payment ledger vs GL";
const OUTSTANDING = "Invoice outstanding vs payment ledger";
const API = "commons.banking.ledger_audit.";
const CAN_REPAIR = () => frappe.user.has_role(["Accounts Manager", "System Manager"]);

frappe.query_reports["Payment Ledger Audit"] = {
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
			options: [LEDGER, OUTSTANDING].join("\n"),
			default: LEDGER,
			reqd: 1,
		},
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
		{
			fieldname: "account",
			label: __("Account"),
			fieldtype: "Link",
			options: "Account",
			get_query: () => ({
				filters: {
					company: frappe.query_report.get_filter_value("company"),
					account_type: ["in", ["Receivable", "Payable"]],
				},
			}),
		},
		{
			fieldname: "party_type",
			label: __("Party Type"),
			fieldtype: "Link",
			options: "Party Type",
			on_change: () => frappe.query_report.set_filter_value("party", ""),
		},
		{
			fieldname: "party",
			label: __("Party"),
			fieldtype: "Dynamic Link",
			options: "party_type",
		},
		{
			fieldname: "voucher_type",
			label: __("Voucher Type"),
			fieldtype: "Link",
			options: "DocType",
			on_change: () => frappe.query_report.set_filter_value("voucher_no", ""),
		},
		{
			fieldname: "voucher_no",
			label: __("Voucher"),
			fieldtype: "Dynamic Link",
			options: "voucher_type",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "action" && data && data.voucher_no && CAN_REPAIR()) {
			return `<button class="btn btn-xs btn-default pla-review"
				data-voucher-type="${frappe.utils.escape_html(data.voucher_type)}"
				data-voucher-no="${frappe.utils.escape_html(data.voucher_no)}">${__("Review")}</button>`;
		}
		return default_formatter(value, row, column, data);
	},

	onload(report) {
		$(report.page.wrapper).on("click", ".pla-review", (e) => {
			const { voucherType, voucherNo } = e.currentTarget.dataset;
			if (report.get_filter_value("view") === OUTSTANDING) {
				review_outstanding(report, voucherType, voucherNo);
			} else {
				review_voucher(report, voucherType, voucherNo);
			}
		});
		if (CAN_REPAIR()) {
			report.page.add_inner_button(__("Repair All Shown…"), () => repair_all(report));
		}
	},
};

const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
const money = (v) => format_number(v || 0, null, 2);

function table(headers, rows) {
	if (!rows.length) return `<p class="text-muted">${__("None")}</p>`;
	return `<table class="table table-bordered table-sm" style="font-size: var(--text-sm)">
		<thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>
		<tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody>
	</table>`;
}

function ple_rows(rows) {
	return table(
		[__("Account"), __("Party"), __("Settles"), __("Amount")],
		rows.map((r) => [
			esc(r.account),
			esc(r.party || "–"),
			esc(r.against_voucher_no),
			`<div class="text-right">${money(r.amount)}</div>`,
		])
	);
}

function review_voucher(report, voucher_type, voucher_no) {
	frappe.call(API + "preview_repair", { voucher_type, voucher_no }).then(({ message: plan }) => {
		const d = new frappe.ui.Dialog({
			title: __("Repair {0}", [voucher_no]),
			size: "large",
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
			primary_action_label: __("Repair Payment Ledger"),
			primary_action() {
				d.disable_primary_action();
				frappe
					.call({
						method: API + "repair_voucher",
						args: { voucher_type, voucher_no },
						freeze: true,
					})
					.then(() => {
						d.hide();
						frappe.show_alert({
							message: __("{0} repaired", [voucher_no]),
							indicator: "green",
						});
						report.refresh();
					})
					.catch(() => d.enable_primary_action());
			},
		});
		d.fields_dict.body.$wrapper.html(voucher_body(voucher_type, voucher_no, plan));
		if (plan.refused || !plan.issues.length) d.get_primary_btn().hide();
		d.show();
	});
}

function voucher_body(voucher_type, voucher_no, plan) {
	if (!plan.issues.length) {
		return `<p>${__("The payment ledger and the GL agree for this voucher now.")}</p>`;
	}
	const link = `<a href="/app/${frappe.router.slug(voucher_type)}/${encodeURIComponent(
		voucher_no
	)}" target="_blank">${esc(voucher_no)}</a>`;
	return `
		<p>${__("{0} {1} is {2}.", [esc(voucher_type), link, esc(plan.issues[0].voucher_status)])}</p>
		<h6>${__("What disagrees")}</h6>
		${table(
			[__("Issue"), __("Account"), __("Party"), __("GL"), __("Payment Ledger")],
			plan.issues.map((r) => [
				esc(r.issue),
				esc(r.account),
				esc(r.party || "–"),
				`<div class="text-right">${money(r.gl_amount)}</div>`,
				`<div class="text-right">${money(r.ple_amount)}</div>`,
			])
		)}
		${
			plan.refused
				? `<div class="alert alert-warning">${esc(plan.refused)}</div>`
				: `<h6>${__(
						"Rows to mark delinked (they stop counting, and stay for the record)"
				  )}</h6>
				${ple_rows(plan.delink)}
				<h6>${__("Rows to add, rebuilt from the document")}</h6>
				${ple_rows(plan.add)}
				<p class="text-muted small">${__(
					"Only the payment ledger changes. The GL is not touched. Outstanding amounts of affected invoices are recomputed, and a comment is added to the voucher."
				)}</p>`
		}`;
}

function review_outstanding(report, voucher_type, voucher_no) {
	const row = (frappe.query_report.data || []).find(
		(r) => r.voucher_type === voucher_type && r.voucher_no === voucher_no
	);
	const d = new frappe.ui.Dialog({
		title: __("Recompute outstanding for {0}", [voucher_no]),
		fields: [{ fieldtype: "HTML", fieldname: "body" }],
		primary_action_label: __("Recompute"),
		primary_action() {
			d.disable_primary_action();
			frappe
				.call({
					method: API + "repair_outstanding",
					args: { voucher_type, voucher_no },
					freeze: true,
				})
				.then(({ message }) => {
					d.hide();
					frappe.show_alert({
						message: __("{0}: {1} → {2}", [
							voucher_no,
							money(message.before),
							money(message.after),
						]),
						indicator: "green",
					});
					report.refresh();
				})
				.catch(() => d.enable_primary_action());
		},
	});
	d.fields_dict.body.$wrapper.html(`
		<p>${__("The invoice says {0} is outstanding; its payment ledger rows add up to {1}.", [
			money(row && row.recorded),
			money(row && row.ledger),
		])}</p>
		<p class="text-muted small">${__(
			"Recompute sets the invoice's outstanding amount and status from the payment ledger, as ERPNext does after every payment. Repair any payment ledger discrepancy for this invoice first, or the recomputed amount will be wrong too."
		)}</p>`);
	d.show();
}

function repair_all(report) {
	if (report.get_filter_value("view") === OUTSTANDING) {
		frappe.msgprint(__("Recompute invoices one at a time with Review."));
		return;
	}
	const rows = frappe.query_report.data || [];
	const issues = [...new Set(rows.map((r) => r.issue))];
	if (!issues.length) {
		frappe.msgprint(__("Nothing to repair."));
		return;
	}
	const d = new frappe.ui.Dialog({
		title: __("Repair payment ledger"),
		size: "large",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "intro",
				options: `<p>${__(
					"Each voucher is checked again on the server and repaired on its own. Vouchers whose document disagrees with its GL are skipped and listed. Only the payment ledger changes."
				)}</p>`,
			},
			{
				fieldtype: "MultiCheck",
				fieldname: "issues",
				label: __("Repair these issues"),
				columns: 1,
				options: issues.map((i) => ({
					label: `${i} (${rows.filter((r) => r.issue === i).length})`,
					value: i,
					checked: !i.endsWith("no party"),
				})),
			},
			{ fieldtype: "HTML", fieldname: "result" },
		],
		primary_action_label: __("Repair"),
		primary_action(values) {
			const chosen = new Set(values.issues || []);
			const seen = new Set();
			const vouchers = rows
				.filter((r) => chosen.has(r.issue))
				.filter(
					(r) =>
						!seen.has(r.voucher_type + "\u0000" + r.voucher_no) &&
						seen.add(r.voucher_type + "\u0000" + r.voucher_no)
				)
				.map((r) => ({ voucher_type: r.voucher_type, voucher_no: r.voucher_no }));
			if (!vouchers.length) return;
			frappe.confirm(
				__("Repair the payment ledger of {0} voucher(s)?", [vouchers.length]),
				() => {
					d.disable_primary_action();
					frappe
						.call({
							method: API + "repair_vouchers",
							args: { vouchers },
							freeze: true,
						})
						.then(({ message: results }) => {
							d.get_primary_btn().hide();
							d.fields_dict.issues.$wrapper.hide();
							d.fields_dict.result.$wrapper.html(
								table(
									[__("Voucher"), __("Result")],
									results.map((r) => [
										esc(r.voucher_no),
										r.status === "failed"
											? `<span class="text-danger">${esc(r.error)}</span>`
											: esc(r.status),
									])
								)
							);
							report.refresh();
						})
						.catch(() => d.enable_primary_action());
				}
			);
		},
	});
	d.show();
}
