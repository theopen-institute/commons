// The desk half of `commons.print_templates`: Test PDF and Fill from a Record on
// the Web Template form, under a "Print Test" group in its toolbar.
//
// Test PDF prints what the editor holds, saved or not, so a layout can be tried
// without saving each change. The PDF comes back as base64 and is opened from a
// blob; the tab is opened at the click, before the request, because a browser
// only lets a click open a window while it is still handling that click.
//
// Fill from a Record runs the Context Prep in the editor against a real record
// and shows what it returned in a dialog. Nothing reaches the form until Save
// there, so the real names can be replaced before they are kept.
(() => {
	const TEST_PDF = "commons.print_templates.api.test_pdf";
	const FILL = "commons.print_templates.api.fill_test_values";
	const GROUP = __("Print Test");
	const SCRIPT_ROLE = "Script Manager";

	const may_run_prep = () =>
		frappe.session.user === "Administrator" || frappe.user.has_role(SCRIPT_ROLE);

	const test_pdf = async (frm) => {
		const tab = window.open("", "_blank");
		try {
			const r = await frappe.xcall(
				TEST_PDF,
				{
					template: frm.is_new() ? null : frm.doc.name,
					source: frm.doc.template || "",
					test_values: frm.doc.test_values || "",
				},
				"POST",
				{ freeze: true, freeze_message: __("Rendering…") }
			);
			if (r.error) {
				tab?.close();
				frappe.msgprint({
					title: __("The template did not render"),
					message: `<pre class="small">${frappe.utils.escape_html(r.error)}</pre>`,
					indicator: "red",
				});
				return;
			}
			const bytes = Uint8Array.from(atob(r.pdf), (c) => c.charCodeAt(0));
			const url = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
			if (tab) tab.location = url;
			else window.open(url, "_blank");
		} catch (e) {
			tab?.close();
			throw e;
		}
	};

	const fill_from_record = (frm) => {
		const load = async () => {
			const { ref_doctype, ref_name } = dialog.get_values(true);
			if (!ref_doctype || !ref_name) return;
			const json = await frappe.xcall(
				FILL,
				{
					doctype: ref_doctype,
					name: ref_name,
					context_prep: frm.doc.context_prep || "",
					label: frm.is_new() ? null : frm.doc.name,
				},
				"POST",
				{ freeze: true }
			);
			dialog.set_value("values", json);
		};

		const dialog = new frappe.ui.Dialog({
			title: __("Fill Test Values from a Record"),
			size: "large",
			fields: [
				{
					fieldname: "ref_doctype",
					fieldtype: "Link",
					options: "DocType",
					label: __("Document Type"),
					reqd: 1,
					onchange: () => dialog.set_value("ref_name", ""),
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "ref_name",
					fieldtype: "Dynamic Link",
					options: "ref_doctype",
					label: __("Record"),
					reqd: 1,
					onchange: load,
				},
				{ fieldtype: "Section Break" },
				{
					fieldname: "values",
					fieldtype: "Code",
					options: "JSON",
					label: __("Test Values"),
					reqd: 1,
					description: __(
						"What Context Prep returned for the record, from the prep as it is in the editor. Replace the real names before saving."
					),
				},
			],
			primary_action_label: __("Save"),
			primary_action: async ({ values }) => {
				try {
					const parsed = JSON.parse(values);
					if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
						throw new Error();
				} catch (e) {
					frappe.msgprint(__("Test Values must be a JSON object."));
					return;
				}
				await frm.set_value("test_values", values);
				await frm.save();
				if (!frm.is_dirty()) dialog.hide();
			},
		});
		dialog.show();
	};

	frappe.ui.form.on("Web Template", {
		refresh(frm) {
			frm.add_custom_button(__("Test PDF"), () => test_pdf(frm), GROUP);
			if (may_run_prep()) {
				frm.add_custom_button(
					__("Fill from a Record"),
					() => fill_from_record(frm),
					GROUP
				);
			}
		},
	});
})();
