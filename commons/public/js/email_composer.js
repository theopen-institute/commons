// A Visual view for HTML emails in core's composer (`frappe.views.CommunicationComposer`).
//
// Core offers two editors: a rich-text one (Quill), which rewrites whatever it
// is given into its own small vocabulary of markup -- a table-based responsive
// layout does not survive being loaded into it -- and, for an HTML template,
// a code editor, which keeps the layout but asks whoever is writing to edit
// markup. This adds a third: the email itself, drawn as it will arrive, with
// the browser's own editing switched on inside it (`designMode`). Text is
// edited where it stands, and the layout around it is left exactly as it was,
// because nothing re-parses it: what is sent is the edited document, read back.
//
// The code editor stays the one source of truth. Visual edits are written back
// into it as they happen, so sending, drafts and everything else core does with
// the HTML field are core's own and unchanged. Switching to HTML shows it.
//
// Wired in at two seams: `get_fields` (one more field, beside core's HTML one)
// and `prepare` (drawing it once the dialog exists). If core renames either,
// or the HTML field, the feature-detect quietly leaves the composer as it is.
// Opt-in: "Enable Visual HTML Email Editor" in Commons Settings.
(() => {
	const features = (frappe.boot && frappe.boot.commons_features) || {};
	if (!features.visual_email_editor) return;
	const Composer = frappe.views && frappe.views.CommunicationComposer;
	if (!Composer || typeof Composer.prototype.get_fields !== "function") return;
	if (typeof Composer.prototype.prepare !== "function") return;

	const FIELD = "commons_visual_editor";
	const WIDTHS = { desktop: "100%", phone: "375px" };
	const is_document = (html) => /^\s*(<!doctype|<html[\s>])/i.test(html || "");

	const STYLE = `
		.cm-visual { border: 1px solid var(--border-color); border-radius: var(--border-radius-md); overflow: hidden; }
		.cm-visual-bar { display: flex; align-items: center; gap: var(--padding-sm); flex-wrap: wrap;
			padding: var(--padding-xs) var(--padding-sm); background: var(--subtle-fg); border-bottom: 1px solid var(--border-color); }
		.cm-visual-bar .cm-spacer { flex: 1; }
		.cm-visual-bar .btn .icon { margin: 0; }
		.cm-visual-stage { background: var(--subtle-accent); padding: var(--padding-sm); display: flex; justify-content: center; }
		.cm-visual-stage iframe { width: 100%; height: 520px; border: 0; background: #fff; border-radius: var(--border-radius);
			box-shadow: var(--shadow-sm); transition: width .2s ease; max-width: 100%; }
		.cm-visual.cm-html-mode .cm-visual-stage, .cm-visual.cm-html-mode .cm-visual-tools,
		.cm-visual.cm-html-mode .cm-visual-widths { display: none; }
		.cm-visual-hidden { display: none !important; }
	`;

	const ensure_style = () => {
		if (document.getElementById("cm-visual-style")) return;
		$(`<style id="cm-visual-style">${STYLE}</style>`).appendTo(document.head);
	};

	const get_fields = Composer.prototype.get_fields;
	Composer.prototype.get_fields = function () {
		const fields = get_fields.apply(this, arguments);
		const at = fields.findIndex((df) => df.fieldname === "html_content");
		if (at < 0) return fields;
		fields.splice(at, 0, {
			fieldtype: "HTML",
			fieldname: FIELD,
			label: __("Message"),
			depends_on: "eval:doc.use_html",
		});
		return fields;
	};

	const prepare = Composer.prototype.prepare;
	Composer.prototype.prepare = function () {
		const result = prepare.apply(this, arguments);
		try {
			setup(this);
		} catch (e) {
			console.warn("Visual HTML email editor could not start", e);
		}
		return result;
	};

	const button = (attrs, content, title) =>
		`<button type="button" class="btn btn-xs btn-default" ${attrs} title="${title || ""}">${content}</button>`;

	const setup = (composer) => {
		const dialog = composer.dialog;
		const code = dialog.fields_dict.html_content;
		const holder = dialog.fields_dict[FIELD];
		if (!code || !holder) return;
		ensure_style();

		const $box = $(`<div class="cm-visual">
			<div class="cm-visual-bar">
				<div class="btn-group">
					${button('data-mode="visual"', __("Visual"))}
					${button('data-mode="html"', __("HTML"))}
				</div>
				<div class="btn-group cm-visual-tools">
					${button('data-cmd="bold"', "<b>B</b>", __("Bold"))}
					${button('data-cmd="italic"', "<i>I</i>", __("Italic"))}
					${button('data-cmd="underline"', "<u>U</u>", __("Underline"))}
					${button('data-cmd="createLink"', frappe.utils.icon("link", "xs"), __("Link"))}
					${button('data-cmd="unlink"', frappe.utils.icon("unlink", "xs"), __("Remove link"))}
					${button('data-cmd="removeFormat"', frappe.utils.icon("remove-formatting", "xs"), __("Clear formatting"))}
					${button('data-cmd="undo"', frappe.utils.icon("undo-2", "xs"), __("Undo"))}
				</div>
				<span class="cm-spacer"></span>
				<div class="btn-group cm-visual-widths">
					${button('data-width="desktop"', frappe.utils.icon("monitor", "xs"), __("Desktop"))}
					${button('data-width="phone"', frappe.utils.icon("smartphone", "xs"), __("Phone"))}
				</div>
			</div>
			<div class="cm-visual-stage"><iframe sandbox="allow-same-origin" title="${__("Email")}"></iframe></div>
		</div>`).appendTo(holder.$wrapper.empty());
		const iframe = $box.find("iframe").get(0);

		let mode = "visual";
		let whole = false; // whether the email is a complete document, or a fragment drawn in one
		let writing = false; // a write-back of our own, not a change to load

		const read_back = () => {
			const doc = iframe.contentDocument;
			if (!doc || !doc.documentElement) return "";
			if (!whole) return doc.body.innerHTML;
			return (doc.doctype ? "<!DOCTYPE html>\n" : "") + doc.documentElement.outerHTML;
		};

		const write_back = frappe.utils.debounce(() => {
			writing = true;
			Promise.resolve(set_code(read_back())).finally(() => (writing = false));
		}, 250);

		const load = (html) => {
			whole = is_document(html);
			iframe.srcdoc = whole
				? html
				: `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
					body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
						font-size: 14px; line-height: 1.5; color: #171717; margin: 16px; }
				</style></head><body>${html || ""}</body></html>`;
			// Frappe's email CSS would be inlined over a complete document's own.
			if (whole && dialog.fields_dict.add_css) dialog.set_value("add_css", 0);
		};

		iframe.addEventListener("load", () => {
			const doc = iframe.contentDocument;
			if (!doc) return;
			doc.designMode = "on";
			doc.addEventListener("input", write_back);
		});

		// Everything that writes the HTML field -- a template, core's Use HTML
		// toggle, a restored draft -- goes through this, so the view follows it.
		const set_code = code.set_value.bind(code);
		code.set_value = function (value) {
			const result = set_code.apply(this, arguments);
			if (!writing && mode === "visual") load(value);
			return result;
		};

		const set_mode = (next) => {
			if (next === "visual" && mode !== "visual") load(code.get_value());
			mode = next;
			$box.toggleClass("cm-html-mode", mode === "html");
			code.$wrapper.toggleClass("cm-visual-hidden", mode === "visual");
			$box.find("[data-mode]").removeClass("btn-primary").addClass("btn-default");
			$box.find(`[data-mode="${mode}"]`).removeClass("btn-default").addClass("btn-primary");
		};

		const set_width = (key) => {
			$box.find("[data-width]").removeClass("btn-primary").addClass("btn-default");
			$box.find(`[data-width="${key}"]`).removeClass("btn-default").addClass("btn-primary");
			iframe.style.width = WIDTHS[key];
		};

		const run = (cmd) => {
			const doc = iframe.contentDocument;
			if (!doc) return;
			if (cmd !== "createLink") {
				doc.execCommand(cmd, false, null);
				write_back();
				return;
			}
			const selection = doc.getSelection();
			const range = selection.rangeCount ? selection.getRangeAt(0).cloneRange() : null;
			frappe.prompt(
				{ label: __("Link address"), fieldname: "url", fieldtype: "Data", reqd: 1, default: "https://" },
				({ url }) => {
					if (range) {
						selection.removeAllRanges();
						selection.addRange(range);
					}
					doc.execCommand("createLink", false, url);
					write_back();
				},
				__("Add link")
			);
		};

		// Keep the selection inside the email while a toolbar button is pressed.
		$box.on("mousedown", "[data-cmd]", (e) => e.preventDefault());
		$box.on("click", "[data-cmd]", (e) => run($(e.currentTarget).data("cmd")));
		$box.on("click", "[data-mode]", (e) => set_mode($(e.currentTarget).data("mode")));
		$box.on("click", "[data-width]", (e) => set_width($(e.currentTarget).data("width")));

		set_width("desktop");
		set_mode("visual");
		load(code.get_value());
	};
})();
