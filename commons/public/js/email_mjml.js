// The Email Template form's MJML half (`commons.email_extensions.mjml`): a live
// preview beside the source, at desktop and phone width, rendered against a real
// document of the template's doctype when there is one to read.
//
// The preview is what compiles on the server and nothing else -- the same mrml,
// the same Jinja protection -- so what it shows is what a save would store. It
// is drawn in a sandboxed iframe (no scripts), because a compiled email is a
// whole document with its own <style>, and loose in the desk it would restyle
// the desk.
(() => {
	const PREVIEW = "commons.email_extensions.mjml.preview";
	const WIDTHS = { desktop: "100%", phone: "375px" };

	// What ticking "Design with MJML" starts from: the template's current text in
	// a plain one-column layout, with the account's signature and footer.
	const starter = (frm) => {
		const body = (frm.doc.use_html ? frm.doc.response_html : frm.doc.response) || "<p>Dear …,</p>";
		const text = /<html[\s>]/i.test(body) ? "<p>Dear …,</p>" : body;
		return `<mjml>
  <mj-head>
    <mj-title>${frappe.utils.escape_html(frm.doc.subject || "")}</mj-title>
    <mj-attributes>
      <mj-all font-family="Helvetica, Arial, sans-serif" />
      <mj-text font-size="15px" line-height="1.6" color="#222222" />
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#f4f4f5">
    <mj-section padding="24px 0 8px">
      <mj-column>
        <mj-text font-size="13px" color="#71717a" align="center">${frappe.utils.escape_html(
			frappe.boot.sysdefaults?.company || frappe.boot.website_settings?.app_name || ""
		)}</mj-text>
      </mj-column>
    </mj-section>
    <mj-section background-color="#ffffff" border-radius="8px" padding="24px 16px">
      <mj-column>
        <mj-text>
${text}
        </mj-text>
      </mj-column>
    </mj-section>
    <mj-section padding="8px 0 24px">
      <mj-column>
        <mj-text font-size="12px" color="#71717a" align="center">{{ email_signature or "" }}{{ email_footer or "" }}</mj-text>
      </mj-column>
    </mj-section>
  </mj-body>
</mjml>`;
	};

	const STYLE = `
		.cm-mjml { border: 1px solid var(--border-color); border-radius: var(--border-radius-md); overflow: hidden; }
		.cm-mjml-bar { display: flex; align-items: center; gap: var(--padding-sm); padding: var(--padding-xs) var(--padding-sm);
			border-bottom: 1px solid var(--border-color); background: var(--subtle-fg); flex-wrap: wrap; }
		.cm-mjml-bar .cm-mjml-status { font-size: var(--text-sm); color: var(--text-muted); margin-left: auto; }
		.cm-mjml-bar .cm-mjml-status.cm-error { color: var(--red-600); }
		.cm-mjml-stage { background: var(--subtle-accent); padding: var(--padding-md); display: flex; justify-content: center; }
		.cm-mjml-stage iframe { width: 100%; height: 640px; border: 0; background: #fff; border-radius: var(--border-radius);
			box-shadow: var(--shadow-sm); transition: width .2s ease; max-width: 100%; }
	`;

	const ensure_style = () => {
		if (document.getElementById("cm-mjml-style")) return;
		$(`<style id="cm-mjml-style">${STYLE}</style>`).appendTo(document.head);
	};

	const width_button = (key, label, icon) =>
		`<button type="button" class="btn btn-xs btn-default" data-width="${key}">
			${frappe.utils.icon(icon, "xs")} ${label}</button>`;

	const draw = (frm) => {
		const field = frm.fields_dict.mjml_preview;
		if (!field) return null;
		if (field.$wrapper.find(".cm-mjml").length) return field.$wrapper.find(".cm-mjml");
		ensure_style();
		const $box = $(`<div class="cm-mjml">
			<div class="cm-mjml-bar">
				<div class="btn-group">
					${width_button("desktop", __("Desktop"), "monitor")}
					${width_button("phone", __("Phone"), "smartphone")}
				</div>
				<span class="cm-mjml-status"></span>
			</div>
			<div class="cm-mjml-stage"><iframe sandbox="allow-same-origin" title="${__(
				"Email preview"
			)}"></iframe></div>
		</div>`).appendTo(field.$wrapper.empty());
		$box.on("click", "[data-width]", (e) => set_width($box, $(e.currentTarget).data("width")));
		set_width($box, "desktop");
		return $box;
	};

	const set_width = ($box, key) => {
		$box.find("[data-width]").removeClass("btn-primary").addClass("btn-default");
		$box.find(`[data-width="${key}"]`).removeClass("btn-default").addClass("btn-primary");
		$box.find("iframe").css("width", WIDTHS[key]);
	};

	// The latest request per form, so a slow answer can't overwrite a newer one.
	const asked = new WeakMap();

	const refresh_preview = (frm) => {
		if (!frm.doc.use_mjml) return;
		const $box = draw(frm);
		if (!$box) return;
		const $status = $box.find(".cm-mjml-status").removeClass("cm-error");
		const source = frm.doc.mjml_source || "";
		if (!source.trim()) {
			$status.text(__("Nothing to preview yet."));
			$box.find("iframe").attr("srcdoc", "");
			return;
		}
		$status.text(__("Compiling…"));
		const ticket = (asked.get(frm) || 0) + 1;
		asked.set(frm, ticket);
		frappe
			.xcall(PREVIEW, { source, email_doctype: frm.doc.email_doctype || null })
			.then((r) => {
				if (asked.get(frm) !== ticket) return;
				if (r.error) {
					$status.addClass("cm-error").text(__("Does not compile: {0}", [r.error]));
					return;
				}
				$box.find("iframe").attr("srcdoc", r.html);
				if (r.render_error) {
					$status.addClass("cm-error").text(__("Compiles, but Jinja failed: {0}", [r.render_error]));
				} else if (r.document) {
					$status.text(__("Filled in from {0} {1}", [__(frm.doc.email_doctype), r.document]));
				} else {
					$status.text(
						frm.doc.email_doctype
							? __("No {0} to fill it in from; Jinja shown as written.", [__(frm.doc.email_doctype)])
							: __("Set a Document Type on the Form Button tab to fill in the Jinja.")
					);
				}
			})
			.catch(() => asked.get(frm) === ticket && $status.addClass("cm-error").text(__("Preview failed.")));
	};

	const later = new WeakMap();
	const refresh_soon = (frm) => {
		clearTimeout(later.get(frm));
		later.set(frm, setTimeout(() => refresh_preview(frm), 500));
	};

	frappe.ui.form.on("Email Template", {
		refresh: refresh_preview,
		mjml_source: refresh_soon,
		email_doctype: refresh_soon,
		use_mjml(frm) {
			if (!frm.doc.use_mjml) return;
			frm.set_value("use_html", 1);
			if (!(frm.doc.mjml_source || "").trim()) frm.set_value("mjml_source", starter(frm));
			refresh_soon(frm);
		},
	});
})();
