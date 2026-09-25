// The desk half of `commons.email_extensions`: an Email menu on every form of a
// doctype some Email Template names, and the template's own form made easier to
// fill in.
//
// The menu is a toolbar group, one item per template, drawn on each refresh
// (core clears custom buttons before every one). Which templates there are
// comes with the boot (`commons.email_extensions.api.extend_bootinfo`), so an
// ordinary form asks nothing; a template saved in this tab is folded into that
// list as it is saved. Picking one asks the server for the rendered email and
// opens core's own composer with it.
//
// The composer fills itself in asynchronously after it is constructed, and
// anything set on it from outside before that finishes is overwritten. So the
// template's values go in through the one seam it offers: its options are
// copied onto the instance before anything runs, which makes `set_values` an
// override, and ours finishes core's before adding the rest. The old
// per-doctype scripts clicked the composer's own buttons and set the recipients
// on a 200ms timer instead, which is why they filled some fields only some of
// the time.
(() => {
	const COMPOSE = "commons.email_extensions.api.compose";
	const TEMPLATE = "Email Template";
	const GROUP = __("Email");

	const templates = () => frappe.boot.commons_email_templates || [];

	// A template's Show When, read the way a field's Depends On is. One that does
	// not evaluate hides its template rather than the form's other templates.
	const applies = (condition, doc) => {
		if (!condition || !condition.trim()) return true;
		try {
			return Boolean(frappe.utils.eval(condition.trim(), { doc }));
		} catch (e) {
			console.warn(`Email Template "Show When" did not evaluate: ${condition}`, e);
			return false;
		}
	};

	const offered = (frm) =>
		templates().filter(
			(t) => t.email_doctype === frm.doctype && applies(t.email_condition, frm.doc)
		);

	const open = async (frm, template) => {
		// Written from the saved record, so unsaved edits would not be in it.
		if (frm.is_dirty()) {
			frappe.show_alert({
				message: __("Save the {0} first: the email is written from what is saved.", [
					__(frm.doctype),
				]),
				indicator: "orange",
			});
			return;
		}

		const draft = await frappe.xcall(
			COMPOSE,
			{ template: template.name, doctype: frm.doctype, name: frm.docname },
			"POST",
			{ freeze: true }
		);
		const base = frappe.views.CommunicationComposer.prototype.set_values;

		new frappe.views.CommunicationComposer({
			frm,
			title: template.name,
			subject: draft.subject,
			message: draft.use_html ? "" : draft.message,
			recipients: draft.recipients.join(", "),
			attach_document_print: draft.attach_document_print,
			async set_values() {
				// The account only when the user may send from it: the From
				// select offers nothing else, and core's own default is better
				// than an empty required field.
				if (draft.sender && (this.user_email_accounts || []).includes(draft.sender)) {
					this.sender = draft.sender;
				}
				await base.call(this);
				await finish(this, draft, template.name);
			},
		});
	};

	const finish = async (composer, draft, template_name) => {
		const dialog = composer.dialog;

		// Recorded on the Communication. `set_model_value`, as core does, so
		// the template isn't added to the message a second time.
		await dialog.fields_dict.email_template.set_model_value(template_name);
		await composer.check_email_template_html(template_name);

		// An HTML template goes into the HTML editor as written. Through the
		// rich-text editor first, its markup would not survive.
		if (draft.use_html) {
			await dialog.set_value("use_html", 1);
			await dialog.set_value("html_content", draft.message);
			// A complete document -- an MJML template -- carries its own CSS,
			// and Frappe's would be inlined over it.
			if (/^\s*(<!doctype|<html[\s>])/i.test(draft.message || "")) {
				await dialog.set_value("add_css", 0);
			}
		}

		if (draft.print_format) {
			const $select = $(dialog.fields_dict.select_print_format.input);
			if ($select.find(`option[value="${CSS.escape(draft.print_format)}"]`).length) {
				$select.val(draft.print_format).trigger("change");
			}
		}
	};

	frappe.ui.form.on("*", "refresh", (frm) => {
		if (frm.is_new() || frm.doctype === TEMPLATE) return;
		const offers = offered(frm);
		if (!offers.length || !frappe.model.can_email(null, frm)) return;

		offers.forEach((template) =>
			frm.add_custom_button(
				frappe.utils.escape_html(template.name),
				() => open(frm, template),
				GROUP
			)
		);
	});

	// The template's form
	// -------------------

	// The fields worth writing to about a document: addresses first, then the
	// links `recipients` can follow to one.
	const recipient_options = (doctype) => {
		const fields = (frappe.get_meta(doctype) || {}).fields || [];
		const option = (df) => ({
			value: df.fieldname,
			label: `${__(df.label || df.fieldname)} (${df.fieldname})`,
		});
		const addresses = fields.filter((df) => df.fieldtype === "Data" && df.options === "Email");
		const links = fields.filter((df) => ["Link", "Dynamic Link"].includes(df.fieldtype));
		return [
			...addresses.map(option),
			...links.map(option),
			{ value: "owner", label: `${__("Created By")} (owner)` },
		];
	};

	const refresh_template_form = (frm) => {
		const doctype = frm.doc.email_doctype;
		const field = frm.fields_dict.custom_recipient_fieldname;
		if (field) field.df.ignore_validation = 1; // several fields, comma-separated

		if (!doctype) {
			frm.set_intro("");
			frm.set_df_property("custom_recipient_fieldname", "options", []);
			return;
		}
		frm.set_intro(
			__("Offered under <b>Email</b> in the toolbar of every saved {0}{1}.", [
				__(doctype),
				frm.doc.email_condition ? __(" for which Show When holds") : "",
			]),
			"blue"
		);
		frappe.model.with_doctype(doctype, () =>
			frm.set_df_property("custom_recipient_fieldname", "options", recipient_options(doctype))
		);
	};

	frappe.ui.form.on(TEMPLATE, {
		setup(frm) {
			frm.set_query("custom_print_format", () => ({
				filters: { doc_type: frm.doc.email_doctype, disabled: 0 },
			}));
			frm.set_query("custom_sending_account", () => ({ filters: { enable_outgoing: 1 } }));
		},
		refresh: refresh_template_form,
		email_doctype: refresh_template_form,
		email_condition: refresh_template_form,
		// Keeps this tab's menus current without a reload.
		after_save(frm) {
			const list = templates().filter((t) => t.name !== frm.doc.name);
			if (frm.doc.email_doctype) {
				list.push({
					name: frm.doc.name,
					email_doctype: frm.doc.email_doctype,
					email_condition: frm.doc.email_condition,
				});
				list.sort((a, b) => a.name.localeCompare(b.name));
			}
			frappe.boot.commons_email_templates = list;
		},
	});

	// A Notification's Email Template (`commons.email_extensions.notification`):
	// the ones written for its doctype, and the ones written for none.
	frappe.ui.form.on("Notification", {
		setup(frm) {
			frm.set_query("email_template", () => ({
				filters: frm.doc.document_type
					? { email_doctype: ["in", [frm.doc.document_type, ""]] }
					: {},
			}));
		},
	});
})();
