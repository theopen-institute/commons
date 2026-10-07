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
	const MAKE = "frappe.core.doctype.communication.email.make";
	const TEMPLATE = "Email Template";
	const GROUP = __("Email");

	// A complete document -- an MJML template, compiled -- carries its own CSS.
	const is_document = (html) => /^\s*(<!doctype|<html[\s>])/i.test(html || "");

	// The server inlines Frappe's email CSS into every HTML email unless told not
	// to (`add_css` on `communication.email.make`), and over a complete document
	// that restyles it. Core's composer once had an "Add CSS" box for this; since
	// 16.50 it has none and never sends the argument, so the server's default
	// always wins. So here, whichever composer sends it -- ours, a reply, core's
	// own "Use template" -- a complete HTML document goes with `add_css` off.
	// `send_email` builds its arguments inline and hands them to `frappe.call`
	// at once, so for that one synchronous call `frappe.call` is wrapped to add
	// the flag to that one request, and put back straight after. If core stops
	// sending through `send_email` or `make`, nothing is added and the server's
	// default applies, as it would without this.
	const Composer = frappe.views && frappe.views.CommunicationComposer;
	if (Composer && typeof Composer.prototype.send_email === "function") {
		const send_email = Composer.prototype.send_email;
		Composer.prototype.send_email = function (btn, form_values) {
			if (!form_values || !form_values.use_html || !is_document(form_values.html_content)) {
				return send_email.apply(this, arguments);
			}
			const call = frappe.call;
			frappe.call = function (opts) {
				if (opts && opts.method === MAKE && opts.args) opts.args.add_css = 0;
				return call.apply(this, arguments);
			};
			try {
				return send_email.apply(this, arguments);
			} finally {
				frappe.call = call;
			}
		};
	}

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
			(t) => t.reference_doctype === frm.doctype && applies(t.email_condition, frm.doc)
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
				// Chosen before core's own values go in: since 16.50 core offers
				// the doctype's default template in a banner whenever none is.
				await choose(this.dialog, template.name);
				await base.call(this);
				await finish(this, draft, template.name);
			},
		});
	};

	// Recorded on the Communication. `set_model_value`, not `set_value`, so a
	// composer that applies a template when its field changes (core's did,
	// before 16.50) doesn't add it to the message a second time.
	const choose = async (dialog, template_name) => {
		const field = dialog.fields_dict.email_template;
		if (field) await field.set_model_value(template_name);
	};

	const finish = async (composer, draft, template_name) => {
		const dialog = composer.dialog;

		// Again, in case core's restored draft of this email named another.
		await choose(dialog, template_name);

		// An HTML template goes into the HTML editor as written. Through the
		// rich-text editor first, its markup would not survive. Core keeps its
		// Use HTML switch hidden until an HTML template is applied: before
		// 16.50 `check_email_template_html` showed it, since then
		// `apply_email_template` does, which would fetch and insert the
		// template a second time -- so the switch is shown here instead.
		// A complete document's own CSS is kept at sending (`send_email`
		// above).
		if (draft.use_html) {
			if (typeof composer.check_email_template_html === "function") {
				await composer.check_email_template_html(template_name);
			} else if (dialog.fields_dict.use_html) {
				dialog.set_df_property("use_html", "hidden", 0);
			}
			await dialog.set_value("use_html", 1);
			await dialog.set_value("html_content", draft.message);
		}

		// The print format is picked in a hidden select; since 16.50 core shows
		// the choice on a card and in its printer menu, redrawn here.
		const print_field = dialog.fields_dict.select_print_format;
		if (draft.print_format && print_field) {
			const $select = $(print_field.input);
			if ($select.find(`option[value="${CSS.escape(draft.print_format)}"]`).length) {
				$select.val(draft.print_format).trigger("change");
				if (typeof composer.render_print_card_meta === "function") {
					composer.render_print_card_meta();
				}
				if (typeof composer.sync_print_menu === "function") composer.sync_print_menu();
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
		const doctype = frm.doc.reference_doctype;
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
			frm.set_df_property(
				"custom_recipient_fieldname",
				"options",
				recipient_options(doctype)
			)
		);
	};

	frappe.ui.form.on(TEMPLATE, {
		setup(frm) {
			frm.set_query("custom_print_format", () => ({
				filters: { doc_type: frm.doc.reference_doctype, disabled: 0 },
			}));
			frm.set_query("custom_sending_account", () => ({ filters: { enable_outgoing: 1 } }));
		},
		refresh: refresh_template_form,
		reference_doctype: refresh_template_form,
		email_condition: refresh_template_form,
		// Keeps this tab's menus current without a reload.
		after_save(frm) {
			const list = templates().filter((t) => t.name !== frm.doc.name);
			if (frm.doc.reference_doctype) {
				list.push({
					name: frm.doc.name,
					reference_doctype: frm.doc.reference_doctype,
					email_condition: frm.doc.email_condition,
				});
				list.sort((a, b) => a.name.localeCompare(b.name));
			}
			frappe.boot.commons_email_templates = list;
		},
	});

	// A Notification's email still waiting (`commons.email_extensions.scheduled`):
	// said above the form, with Send Now and Don't Send, each confirmed first.
	// Asked only on the doctypes some Notification delays for, which come with
	// the boot, so an ordinary form asks nothing.
	const SCHEDULED = "commons.email_extensions.scheduled";

	const show_waiting = async (frm) => {
		const delayed = frappe.boot.commons_delayed_doctypes || [];
		if (frm.is_new() || !delayed.includes(frm.doctype)) return;
		const asked_for = frm.docname;
		const rows = await frappe.xcall(
			`${SCHEDULED}.scheduled`,
			{ doctype: frm.doctype, name: asked_for },
			"GET"
		);
		if (frm.docname !== asked_for) return; // the form has moved on to another record meanwhile
		// The layout's message area appends a block per call, so a refresh
		// replaces the one drawn last time rather than adding another beside it.
		$(frm.layout.message).find(".cm-waiting").closest(".form-message").remove();
		if (!rows || !rows.length) return;
		const lines = rows.map(
			(row) => `<div class="cm-waiting" data-queue="${frappe.utils.escape_html(row.queue)}"
				style="display:flex;align-items:center;gap:var(--padding-sm);flex-wrap:wrap">
				<span>${__("Email {0} to {1} is scheduled for {2}.", [
					`<b>${frappe.utils.escape_html(row.subject || "")}</b>`,
					frappe.utils.escape_html(row.recipients || ""),
					frappe.utils.escape_html(frappe.datetime.str_to_user(row.send_after)),
				])}</span>
				<span style="margin-left:auto;display:flex;gap:var(--padding-xs)">
					<button type="button" class="btn btn-xs btn-default" data-action="send-now">${__(
						"Send Now"
					)}</button>
					<button type="button" class="btn btn-xs btn-default" data-action="dont-send">${__(
						"Don't Send"
					)}</button>
				</span>
			</div>`
		);
		frm.dashboard.set_headline_alert(lines.join(""), "blue");
		// The headline is drawn in the layout's message area, not the dashboard.
		$(frm.layout.wrapper)
			.off("click.cm-waiting")
			.on("click.cm-waiting", ".cm-waiting [data-action]", (e) => {
				const queue = $(e.currentTarget).closest(".cm-waiting").data("queue");
				const action = $(e.currentTarget).data("action");
				const [question, method] =
					action === "send-now"
						? [__("Send this email now?"), "send_now"]
						: [
								__("Don't send this email? It will be removed from the queue."),
								"dont_send",
						  ];
				frappe.confirm(question, async () => {
					await frappe.xcall(`${SCHEDULED}.${method}`, {
						doctype: frm.doctype,
						name: frm.docname,
						queue,
					});
					frappe.show_alert({
						message:
							action === "send-now"
								? __("Sending within a minute or so.")
								: __("Not sent."),
						indicator: "green",
					});
					frm.reload_doc();
				});
			});
	};

	frappe.ui.form.on("*", "refresh", (frm) => {
		show_waiting(frm).catch(() => {});
	});

	// A Notification saved in this tab updates where the forms above look.
	frappe.ui.form.on("Notification", {
		after_save(frm) {
			const delayed = new Set(frappe.boot.commons_delayed_doctypes || []);
			if (frm.doc.enabled && frm.doc.channel === "Email" && frm.doc.send_delay_minutes > 0) {
				delayed.add(frm.doc.document_type);
			}
			frappe.boot.commons_delayed_doctypes = [...delayed];
		},
	});

	// A Notification's Email Template (`commons.email_extensions.notification`):
	// the ones written for its doctype, and the ones written for none.
	frappe.ui.form.on("Notification", {
		setup(frm) {
			frm.set_query("email_template", () => ({
				filters: frm.doc.document_type
					? { reference_doctype: ["in", [frm.doc.document_type, ""]] }
					: {},
			}));
		},
	});
})();
