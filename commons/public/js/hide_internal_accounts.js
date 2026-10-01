// "Hide Internal Accounts" on the reports `commons.banking.financial_statements`
// can leave internal accounts out of, when Commons Settings offers it.
//
// ERPNext's report scripts build their filters when each report is first opened,
// several of them sharing one array, so the checkbox is added to a copy of the
// report's list just before the query report draws it, and to no other report.
// Hidden with a Report Template, which reads the books through ERPNext's own
// engine rather than the functions the server half replaces.
(() => {
	const QueryReport = frappe.views && frappe.views.QueryReport;
	if (!QueryReport || typeof QueryReport.prototype.setup_filters !== "function") return;

	const REPORTS = ["Profit and Loss Statement", "Gross and Net Profit Report"];
	const FIELDNAME = "hide_internal_accounts";

	const setup_filters = QueryReport.prototype.setup_filters;
	QueryReport.prototype.setup_filters = function () {
		const settings = this.report_settings;
		if (
			settings &&
			REPORTS.includes(this.report_name) &&
			frappe.boot.commons_features?.hide_internal_accounts
		) {
			const filters = settings.filters || [];
			if (!filters.some((df) => df.fieldname === FIELDNAME)) {
				settings.filters = [
					...filters,
					{
						fieldname: FIELDNAME,
						label: __("Hide Internal Accounts"),
						fieldtype: "Check",
						default: 0,
						depends_on: "eval:!doc.report_template",
					},
				];
			}
		}
		return setup_filters.apply(this, arguments);
	};
})();
