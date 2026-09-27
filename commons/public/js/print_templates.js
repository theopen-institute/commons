// The desk half of `commons.print_templates`: Test PDF on the Web Template form.
//
// It opens a dialog asking for the template's inputs, one control per row of
// its Fields table -- a Student picker for Student Statement -- and Generate
// PDF runs the Context Prep in the editor on them and prints the template in
// the editor, as a Print Format passing the same inputs would. A template with
// no Fields reads the printed document instead, so for it the dialog asks for
// a document type and record.
//
// Add Letter Head puts a Letter Head above the template and its footer below,
// as Frappe's standard format would.
//
// Edit Prepared Values is for a test the inputs cannot express -- a made-up
// name, an edge case, a real statement with the names taken out: Run Context
// Prep puts the prep's output in the box as JSON, and while the box holds
// anything, Generate PDF prints that instead of running the prep again.
//
// Nothing is kept: not on the template, not on the server. The dialog stays
// open, so a change can be printed again, and each template's dialog is kept
// until the page is reloaded (or its Fields change), so reopening it finds the
// last inputs. Where the inputs miss the Fields -- a required one left empty, a
// Link to nothing -- it says so under the form, and prints anyway.
//
// The PDF comes back as base64 and is opened from a blob. Its tab is opened at
// the click, before the request, because a browser only lets a click open a
// window while it is still handling that click.
(() => {
	const TEST_PDF = "commons.print_templates.api.test_pdf";
	const PREPARE = "commons.print_templates.api.prepare_values";
	const SCRIPT_ROLE = "Script Manager";
	// Input controls are prefixed, so a template's input can be called anything
	// without colliding with the dialog's own fields.
	const PREFIX = "input__";

	const may_run_prep = () =>
		frappe.session.user === "Administrator" || frappe.user.has_role(SCRIPT_ROLE);

	const scrub = (label) => frappe.scrub(label || "");

	// The Fields rows as the editor holds them, saved or not.
	const declared = (frm) =>
		(frm.doc.fields || []).map((f) => ({
			label: f.label,
			fieldname: f.fieldname || scrub(f.label),
			fieldtype: f.fieldtype,
			reqd: f.reqd,
			options: f.options,
			default: f.default,
		}));

	const LAYOUT = ["Section Break", "Column Break"];
	const has_inputs = (fields) => fields.some((f) => !LAYOUT.includes(f.fieldtype));

	// One dialog control per input, read the way core's values editor reads the
	// table: rows up to the first Table Break are single inputs, and a Table
	// Break is a list whose columns are the rows after it.
	const control = (f) =>
		f.fieldtype === "JSON" ? { ...f, fieldtype: "Code", options: "JSON" } : { ...f };

	const input_controls = (fields) => {
		const singles = [];
		const tables = [];
		for (const f of fields) {
			if (f.fieldtype === "Table Break") {
				tables.push({ ...f, columns: [] });
			} else if (tables.length) {
				if (!LAYOUT.includes(f.fieldtype)) tables[tables.length - 1].columns.push(f);
			} else {
				singles.push(
					LAYOUT.includes(f.fieldtype)
						? f
						: { ...control(f), fieldname: PREFIX + f.fieldname }
				);
			}
		}
		return [
			...singles,
			...tables.map((t) => ({
				label: t.label,
				fieldname: PREFIX + t.fieldname,
				fieldtype: "Table",
				reqd: t.reqd,
				data: [],
				fields: t.columns.map((c, i) => ({ ...control(c), in_list_view: i <= 3 })),
			})),
		];
	};

	// The inputs as a Print Format would pass them: declared names only, list
	// rows without the grid's own bookkeeping, JSON parsed.
	const read_inputs = (dialog, fields) => {
		const raw = dialog.get_values(true) || {};
		const inputs = {};
		let table = null;
		for (const f of fields) {
			if (f.fieldtype === "Table Break") {
				table = f;
				inputs[f.fieldname] = (raw[PREFIX + f.fieldname] || []).map((row) => {
					const clean = {};
					for (const c of fields.slice(fields.indexOf(f) + 1)) {
						if (c.fieldtype === "Table Break") break;
						if (!LAYOUT.includes(c.fieldtype))
							clean[c.fieldname] = parse_json_input(c, row[c.fieldname]);
					}
					return clean;
				});
			} else if (!table && !LAYOUT.includes(f.fieldtype)) {
				const value = parse_json_input(f, raw[PREFIX + f.fieldname]);
				if (value !== undefined && value !== null && value !== "")
					inputs[f.fieldname] = value;
			}
		}
		return inputs;
	};

	const parse_json_input = (f, value) => {
		if (f.fieldtype !== "JSON" || typeof value !== "string" || !value.trim()) return value;
		try {
			return JSON.parse(value);
		} catch (e) {
			return value; // left as text; the server's check says what is wrong with it
		}
	};

	const show_warnings = (dialog, warnings) => {
		const $w = dialog.fields_dict.warnings.$wrapper;
		if (!warnings || !warnings.length) {
			$w.empty();
			return;
		}
		$w.html(`<div class="alert alert-warning small" style="margin: 0">
			<div style="font-weight: 600; margin-bottom: 4px">${__(
				"The inputs do not match the Fields table:"
			)}</div>
			<ul style="margin: 0; padding-left: 18px">${warnings
				.map((w) => `<li>${frappe.utils.escape_html(w)}</li>`)
				.join("")}</ul>
		</div>`);
	};

	// What every request carries: the template as the editor holds it, and the
	// inputs (or record) the dialog was given.
	const request = (frm, dialog, fields) => {
		const args = {
			template: frm.is_new() ? null : frm.doc.name,
			fields,
		};
		if (may_run_prep()) args.context_prep = frm.doc.context_prep || "";
		if (has_inputs(fields)) {
			args.inputs = read_inputs(dialog, fields);
		} else {
			const { ref_doctype, ref_name } = dialog.get_values(true) || {};
			if (ref_doctype && ref_name)
				Object.assign(args, { doctype: ref_doctype, name: ref_name });
		}
		return args;
	};

	const generate = async (frm, dialog, fields) => {
		const edited = (dialog.get_value("values") || "").trim();
		if (edited) {
			try {
				const parsed = JSON.parse(edited);
				if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
					throw new Error();
			} catch (e) {
				frappe.msgprint(__("The prepared values must be a JSON object."));
				return;
			}
		}
		const tab = window.open("", "_blank");
		try {
			const r = await frappe.xcall(
				TEST_PDF,
				{
					...request(frm, dialog, fields),
					source: frm.doc.template || "",
					values: edited,
					letter_head: dialog.get_value("letter_head") || null,
				},
				"POST",
				{ freeze: true, freeze_message: __("Rendering…") }
			);
			if (!edited) show_warnings(dialog, r.warnings);
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

	const run_prep = async (frm, dialog, fields) => {
		const r = await frappe.xcall(PREPARE, request(frm, dialog, fields), "POST", {
			freeze: true,
		});
		dialog.set_value("values", r.values);
		show_warnings(dialog, r.warnings);
	};

	const make_dialog = (frm, fields) => {
		const source_fields = has_inputs(fields)
			? input_controls(fields)
			: [
					{
						fieldname: "ref_doctype",
						fieldtype: "Link",
						options: "DocType",
						label: __("Document Type"),
						description: __(
							"This template declares no inputs, so its Context Prep reads the printed document."
						),
						onchange: () => dialog.set_value("ref_name", ""),
					},
					{ fieldtype: "Column Break" },
					{
						fieldname: "ref_name",
						fieldtype: "Dynamic Link",
						options: "ref_doctype",
						label: __("Document"),
					},
			  ];

		const dialog = new frappe.ui.Dialog({
			title: __("Test PDF"),
			size: "large",
			fields: [
				...source_fields,
				{ fieldtype: "Section Break" },
				{
					fieldname: "letter_head",
					fieldtype: "Link",
					options: "Letter Head",
					label: __("Add Letter Head"),
					description: __(
						"Optional. Placed as Frappe's standard format places it. A real print only has one if its Print Format includes it."
					),
				},
				{ fieldname: "warnings", fieldtype: "HTML" },
				{
					fieldtype: "Section Break",
					label: __("Edit Prepared Values"),
					collapsible: 1,
				},
				{
					fieldname: "run_prep",
					fieldtype: "Button",
					label: __("Run Context Prep"),
					click: () => run_prep(frm, dialog, fields),
				},
				{
					fieldname: "values",
					fieldtype: "Code",
					options: "JSON",
					label: __("Prepared Values"),
					description: __(
						"While this holds anything, Generate PDF prints it as it is instead of running the Context Prep. Clear it to print from the inputs again. Nothing here is saved."
					),
				},
			],
			primary_action_label: __("Generate PDF"),
			primary_action: () => generate(frm, dialog, fields),
		});
		return dialog;
	};

	// By template name, and rebuilt when its Fields change: core reuses one form
	// object for every record of a doctype, and the controls are the Fields.
	const dialogs = new Map();

	const open_test = (frm) => {
		const fields = declared(frm);
		const signature = JSON.stringify(fields);
		const kept = dialogs.get(frm.docname);
		if (!kept || kept.signature !== signature) {
			dialogs.set(frm.docname, { signature, dialog: make_dialog(frm, fields) });
		}
		dialogs.get(frm.docname).dialog.show();
	};

	frappe.ui.form.on("Web Template", {
		refresh(frm) {
			frm.add_custom_button(__("Test PDF"), () => open_test(frm));
		},
	});
})();
