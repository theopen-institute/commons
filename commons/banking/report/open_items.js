/* global erpnext */
// Shared by Open Receivables and Open Payables (each includes this file).
// Account, then party, then voucher; the report opens with the accounts alone
// (the tree footer below the table expands it level by level).

frappe.provide("commons.open_items");

commons.open_items.register = function (report_name, account_type) {
	frappe.query_reports[report_name] = {
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
				fieldname: "as_on",
				label: __("Issued On or Before"),
				fieldtype: "Date",
				reqd: 1,
				default: frappe.datetime.get_today(),
				description: __(
					"Vouchers issued on or before this date that are still open today. A voucher settled later is not shown."
				),
			},
			{
				fieldname: "group_by",
				label: __("Group By"),
				fieldtype: "Select",
				options: ["Account", "Party"].join("\n"),
				default: "Account",
				description: __("What the rows at the top of the tree are."),
			},
			{
				fieldname: "account",
				label:
					account_type === "Receivable"
						? __("Receivable Account")
						: __("Payable Account"),
				fieldtype: "Link",
				options: "Account",
				get_query: () => ({
					filters: {
						company: frappe.query_report.get_filter_value("company"),
						account_type: account_type,
					},
				}),
			},
			{
				fieldname: "party_type",
				label: __("Party Type"),
				fieldtype: "Link",
				options: "Party Type",
				get_query: () => ({ filters: { account_type: account_type } }),
				on_change: () => frappe.query_report.set_filter_value("party", []),
			},
			{
				fieldname: "party",
				label: __("Party"),
				fieldtype: "MultiSelectList",
				get_data: (txt) => {
					const party_type = frappe.query_report.get_filter_value("party_type");
					return party_type ? frappe.db.get_link_options(party_type, txt) : [];
				},
			},
			{
				fieldname: "cost_center",
				label: __("Cost Center"),
				fieldtype: "MultiSelectList",
				get_data: (txt) =>
					frappe.db.get_link_options("Cost Center", txt, {
						company: frappe.query_report.get_filter_value("company"),
					}),
			},
			{
				fieldname: "project",
				label: __("Project"),
				fieldtype: "MultiSelectList",
				get_data: (txt) =>
					frappe.db.get_link_options("Project", txt, {
						company: frappe.query_report.get_filter_value("company"),
					}),
			},
		],

		initial_depth: 0,

		formatter(value, row, column, data, default_formatter) {
			if (column.fieldname === "label" && data && data.row_type) {
				return commons.open_items.label(data);
			}
			value = default_formatter(value, row, column, data);
			if (data && data.row_type && data.row_type !== "voucher") {
				value = `<b>${value}</b>`;
			}
			return value;
		},
	};

	// Accounting dimensions go after Project, as filters of their own.
	erpnext.utils.add_dimensions(report_name, 8);
};

commons.open_items.label = function (data) {
	const esc = frappe.utils.escape_html;
	const link = (doctype, name, text) =>
		`<a href="/app/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}">${esc(
			text
		)}</a>`;
	if (data.row_type === "voucher") {
		return link(data.voucher_type, data.voucher_no, data.voucher_no);
	}
	// Only the rows at the top say how many of the next level they hold.
	const count = (n, text) => (n ? ` <span class="text-muted">· ${__(text, [n])}</span>` : "");
	if (data.row_type === "party") {
		return `<b>${link(data.party_type, data.party, data.label)}</b>${count(
			data.accounts,
			"{0} accounts"
		)}`;
	}
	if (data.row_type === "account") {
		return `<b>${link("Account", data.account, data.label)}</b>${count(
			data.parties,
			"{0} parties"
		)}`;
	}
	return `<b>${esc(data.label)}</b>`;
};
