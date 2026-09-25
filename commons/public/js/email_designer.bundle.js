// A drag-and-drop designer for an Email Template's MJML: GrapesJS with its MJML
// plugin, over the whole screen, opened from the template's form
// (`email_mjml.js`) and loaded the first time it is -- GrapesJS is some
// megabytes, and no other page needs it.
//
// What it edits is the template's MJML, and what it hands back is MJML: the
// same `mjml_source` the code editor beside the preview edits, compiled on save
// by the server as always (`commons.email_extensions.mjml`). The designer is a
// second way in, not a second kind of template.
//
// One engine
// ----------
// The plugin draws its canvas by compiling MJML, with mjml-browser unless given
// another compiler. It is given mrml -- the WebAssembly build of the same Rust
// engine the server compiles with (mrml core 6 in both) -- so the canvas, the
// form's preview and the email sent are one compiler's output. Two things the
// plugin assumes of mjml-browser's output are not true of mrml's, and
// `compile` below adapts each:
//
// * a section is drawn by compiling it inside `<mj-body><mj-body …>`, which
//   mjml-browser forgives and mrml renders as a literal unknown tag -- losing
//   the 600px column and the section's background with it. The doubled body is
//   merged into one before compiling.
// * the plugin cuts the body out with the greedy `/<body(.*)>/`, which stops at
//   the end of mjml-browser's first line; mrml writes one line, so it would run
//   to the document's last `>`. A line break after `<body …>` restores the
//   boundary.
//
// Attributes
// ----------
// The plugin's components hold MJML's built-in defaults among their attributes,
// and on export it leaves out any attribute equal to a built-in default --
// `font-size="13px"` on an `mj-text`, say. Both are only the same email while
// nothing changes the defaults, and `<mj-attributes>` exists to change them: a
// template setting text to 15px there, with one line held at 13px, came back
// with that line at 15px; exporting every attribute instead wrote the built-in
// paddings over the template's own. The only export that is the same email is
// the attributes the source was written with, and the ones the person has
// since changed (`track_attributes`). A block dragged in new has no source, and
// keeps the plugin's own export -- which lets it follow the template's defaults.
//
// Jinja
// -----
// GrapesJS keeps Jinja where it stands -- `{{ }}` in text and attributes, and a
// `{% for %}` between sections, shown on the canvas as a line of text -- but
// escapes `<` inside it (`{% if n &lt; 3 %}`), which Jinja can't read. The
// export is unescaped inside Jinja tags on the way out; the server's compile
// does the same, for MJML that comes from anywhere else.
import grapesjs from "grapesjs";
import mjml_plugin from "grapesjs-mjml";
import init_mrml, { Engine } from "mrml/web/mrml_wasm.js";

// Served from the app's node_modules, which bench links into every app's public
// folder. The bundler would otherwise have to inline 1 MB of WebAssembly.
const WASM = "/assets/commons/node_modules/mrml/web/mrml_wasm_bg.wasm";

let engine_loading = null;
const load_engine = () =>
	(engine_loading ||= init_mrml({ module_or_path: WASM }).then(() => new Engine()));

const compiler = (engine) => (input) => {
	const mjml = input
		.replace(/<mj-body>\s*<mj-body(\s[^>]*)?>/, "<mj-body$1>")
		.replace(/<\/mj-body>\s*<\/mj-body>/, "</mj-body>");
	const result = engine.toHtml(mjml);
	if (result.type !== "success") {
		return { html: "", errors: [{ message: result.message, formattedMessage: result.message }] };
	}
	return { html: result.content.replace(/(<body[^>]*>)/, "$1\n"), errors: [] };
};

const JINJA = /\{\{[\s\S]*?\}\}|\{%[\s\S]*?%\}|\{#[\s\S]*?#\}/g;
const unescape_jinja = (source) =>
	source.replace(JINJA, (tag) =>
		tag
			.replace(/&lt;/g, "<")
			.replace(/&gt;/g, ">")
			.replace(/&quot;/g, '"')
			.replace(/&#39;/g, "'")
			.replace(/&amp;/g, "&")
	);

// What the designer is given has to parse as XML: the plugin's HTML parser
// cannot read MJML's self-closing tags (`<mj-all … />` swallows the tags after
// it), so it runs with its XML parser -- which drops, without a word, any
// element whose content isn't well-formed XML. MJML written by hand, or
// compiled happily by mrml, often isn't: `{% if n < 3 %}`, `Fees & Charges`,
// `&nbsp;`, `<br>`. So those are rewritten into their XML spelling first, none
// of it changing what the email says: Jinja's `<`, `>` and `&` escaped (and
// unescaped again on the way out), a bare `&` escaped, an HTML-only entity as
// its number, and an HTML void tag closed.
const XML_ENTITIES = new Set(["lt", "gt", "amp", "quot", "apos"]);
const VOID_TAG = /<(area|base|br|col|embed|hr|img|input|link|meta|source|track|wbr)(\s[^<>]*?)?\s*>/gi;

const entity_number = (name) => {
	const probe = document.createElement("textarea");
	probe.innerHTML = `&${name};`;
	const text = probe.value;
	return text === `&${name};` ? `&amp;${name};` : `&#${text.codePointAt(0)};`;
};

export const as_xml = (source) =>
	source
		.replace(JINJA, (tag) => tag.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"))
		.replace(/&(?![A-Za-z][A-Za-z0-9]*;|#[0-9]+;|#[xX][0-9A-Fa-f]+;)/g, "&amp;")
		.replace(/&([A-Za-z][A-Za-z0-9]*);/g, (whole, name) => (XML_ENTITIES.has(name) ? whole : entity_number(name)))
		.replace(VOID_TAG, (whole, name, attributes = "") =>
			attributes.trimEnd().endsWith("/") ? whole : `<${name}${attributes}/>`
		);

// GrapesJS exports MJML on one line. Laid out again, one element to a line, so
// the source is still something a person can edit by hand after a designer has
// been at it. The content of an element that holds text or HTML (an "ending
// tag", in MJML's terms) is left exactly as it is.
const ENDING = new Set([
	"mj-text", "mj-button", "mj-raw", "mj-title", "mj-preview", "mj-style", "mj-table",
	"mj-navbar-link", "mj-social-element", "mj-accordion-title", "mj-accordion-text",
]);
const TAG = /<(\/?)(mjml|mj-[a-z-]+)((?:\s[^>]*?)?)(\/?)>/g;

export const format_mjml = (source) => {
	const lines = [];
	let depth = 0;
	let last = 0;
	let inside = null; // the ending tag whose content is being copied as it is
	let just_opened = null; // an element opened on the last line, still empty
	const push = (text) => lines.push("  ".repeat(depth) + text);
	TAG.lastIndex = 0;
	let m;
	while ((m = TAG.exec(source))) {
		const [whole, closing, name, , self_closing] = m;
		if (inside) {
			if (closing && name === inside) {
				lines[lines.length - 1] += source.slice(last, m.index) + whole;
				inside = null;
				last = TAG.lastIndex;
			}
			continue;
		}
		const between = source.slice(last, m.index).trim();
		if (between) {
			push(between);
			just_opened = null;
		}
		if (closing) {
			depth = Math.max(0, depth - 1);
			if (just_opened === name) lines[lines.length - 1] += whole;
			else push(whole);
			just_opened = null;
		} else if (self_closing) {
			push(whole);
			just_opened = null;
		} else if (ENDING.has(name)) {
			push(whole);
			inside = name;
			just_opened = null;
		} else {
			push(whole);
			depth++;
			just_opened = name;
		}
		last = TAG.lastIndex;
	}
	const rest = source.slice(last).trim();
	if (rest) push(rest);
	return lines.join("\n") + "\n";
};

// Images: the site's public ones to pick from, and uploads go to it as public
// files -- an email is read outside the desk, so a private file would not load.
// Their `/files/…` addresses are made absolute when the email is sent
// (`frappe.email.email_body.get_formatted_html` runs `scrub_urls`).
const IMAGE_TYPES = ["PNG", "JPG", "JPEG", "GIF", "SVG", "WEBP"];

const load_images = async (editor) => {
	const files = await frappe.db.get_list("File", {
		filters: { is_private: 0, is_folder: 0, file_type: ["in", IMAGE_TYPES] },
		fields: ["file_url", "file_name"],
		order_by: "creation desc",
		limit: 100,
	});
	editor.AssetManager.add(files.map((f) => ({ src: f.file_url, name: f.file_name })));
};

const upload_images = (editor) => async (event) => {
	const files = [...((event.dataTransfer || event.target).files || [])];
	for (const file of files) {
		const body = new FormData();
		body.append("file", file, file.name);
		body.append("is_private", "0");
		body.append("folder", "Home");
		const response = await fetch("/api/method/upload_file", {
			method: "POST",
			headers: { "X-Frappe-CSRF-Token": frappe.csrf_token, Accept: "application/json" },
			body,
		});
		const data = await response.json().catch(() => ({}));
		if (!response.ok || !data.message) {
			frappe.msgprint(__("{0} could not be uploaded.", [frappe.utils.escape_html(file.name)]));
			continue;
		}
		editor.AssetManager.add({ src: data.message.file_url, name: data.message.file_name });
	}
};

// "Insert field", in the text toolbar: a field of the template's doctype, as
// the `{{ fieldname }}` the email is filled in from.
const field_options = (doctype) => {
	const skip = new Set(frappe.model.layout_fields.concat(frappe.model.table_fields, ["Button", "HTML", "Image", "Attach Image"]));
	const fields = ((doctype && frappe.get_meta(doctype)) || {}).fields || [];
	return [{ value: "name", label: `${__("ID")} (name)` }].concat(
		fields
			.filter((df) => !skip.has(df.fieldtype))
			.map((df) => ({ value: df.fieldname, label: `${__(df.label || df.fieldname)} (${df.fieldname})` }))
	);
};

const add_field_action = (editor, doctype) => {
	editor.RichTextEditor.add("commons-field", {
		icon: `<span style="font-family: monospace; font-size: 11px;">{&thinsp;}</span>`,
		attributes: { title: __("Insert field") },
		result(rte) {
			if (!doctype) {
				frappe.msgprint(__("Set a Document Type on the template's Form Button tab to insert its fields."));
				return;
			}
			const doc = rte.el.ownerDocument;
			const selection = doc.getSelection();
			const range = selection.rangeCount ? selection.getRangeAt(0).cloneRange() : null;
			frappe.prompt(
				{
					label: __("Field of {0}", [__(doctype)]),
					fieldname: "field",
					fieldtype: "Autocomplete",
					options: field_options(doctype),
					reqd: 1,
				},
				({ field }) => {
					if (range) {
						selection.removeAllRanges();
						selection.addRange(range);
					}
					rte.insertHTML(`{{ ${field} }}`);
				},
				__("Insert field"),
				__("Insert")
			);
		},
	});
};

// Before import, each MJML tag is marked with the names of the attributes it
// was written with; after it, the list moves from the element to the component.
const WRITTEN = "data-cm-written";
const OPEN_TAG = /<(mjml|mj-[a-z-]+)(\s[^>]*?)?(\/?)>/g;
const ATTRIBUTE = /([^\s=\/"']+)\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/g;

const mark_written = (source) =>
	source.replace(OPEN_TAG, (whole, name, attributes = "", self_closing) => {
		const names = [...attributes.matchAll(ATTRIBUTE)].map((m) => m[1]);
		return `<${name}${attributes} ${WRITTEN}="${names.join(" ")}"${self_closing}>`;
	});

const track_attributes = (editor) => {
	const components = editor.DomComponents;
	components.getTypes().forEach((type) => {
		if (!/^mj(ml|-)/.test(type.id)) return;
		const plugins_own = type.model.prototype.getAttrToHTML;
		components.addType(type.id, {
			model: {
				getAttrToHTML() {
					if (!this.cm_written) return plugins_own.call(this);
					const attributes = { ...this.get("attributes") };
					delete attributes.style;
					delete attributes.id;
					delete attributes[WRITTEN];
					Object.keys(attributes).forEach((name) => {
						if (!this.cm_written.has(name)) delete attributes[name];
					});
					return attributes;
				},
			},
		});
	});
};

const collect_written = (component) => {
	const attributes = component.getAttributes();
	if (WRITTEN in attributes) {
		component.cm_written = new Set((attributes[WRITTEN] || "").split(" ").filter(Boolean));
		component.removeAttributes(WRITTEN);
	}
	component.components().forEach(collect_written);
};

// An attribute the person changes is theirs to keep, whatever its value.
const follow_changes = (editor) =>
	editor.on("component:update:attributes", (component) => {
		if (!component.cm_written) return;
		const before = component.previous("attributes") || {};
		const after = component.get("attributes") || {};
		new Set([...Object.keys(before), ...Object.keys(after)]).forEach((name) => {
			if (name !== "style" && name !== "id" && before[name] !== after[name]) component.cm_written.add(name);
		});
	});

class EmailDesigner {
	constructor({ title, source, doctype, on_save }) {
		this.on_save = on_save;
		this.dirty = false;
		this.$root = $(`<div class="cm-designer" role="dialog" aria-modal="true">
			<div class="cm-designer-bar">
				<span class="cm-designer-title"></span>
				<span class="cm-designer-note">${__("Drawn by the same MJML engine that sends it")}</span>
				<button type="button" class="btn btn-sm btn-default" data-action="cancel">${__("Cancel")}</button>
				<button type="button" class="btn btn-sm btn-primary" data-action="save">${__("Save")}</button>
			</div>
			<div class="cm-designer-editor"></div>
		</div>`).appendTo(document.body);
		this.$root.find(".cm-designer-title").text(title);
		this.$root.on("click", "[data-action=cancel]", () => this.cancel());
		this.$root.on("click", "[data-action=save]", () => this.save());
		$("body").addClass("modal-open");
		this.start(source, doctype);
	}

	async start(source, doctype) {
		const engine = await load_engine();
		const container = this.$root.find(".cm-designer-editor").get(0);
		const editor = (this.editor = grapesjs.init({
			container,
			height: "100%",
			fromElement: false,
			storageManager: false,
			colorPicker: { appendTo: "parent" },
			assetManager: { upload: false, assets: [], uploadFile: (event) => upload_images(this.editor)(event) },
			canvasCss: `[data-gjs-type="mj-head"] { display: none !important; }`,
			plugins: [mjml_plugin],
			pluginsOpts: {
				[mjml_plugin]: { mjmlParser: compiler(engine), useXmlParser: true },
			},
		}));
		track_attributes(editor);
		add_field_action(editor, doctype);
		editor.setComponents(mark_written(as_xml(source)));
		collect_written(editor.getWrapper());
		editor.on("load", () => {
			// Blocks first: the thing to do with an empty selection is add something.
			const blocks = editor.Panels.getButton("views", "open-blocks");
			if (blocks) blocks.set("active", true);
			editor.UndoManager.clear();
			// Anything after this point is a change of the person's.
			follow_changes(editor);
			editor.on("update", () => (this.dirty = true));
		});
		load_images(editor).catch(() => {});
		if (doctype) frappe.model.with_doctype(doctype);
	}

	mjml() {
		return format_mjml(unescape_jinja(this.editor.getHtml()));
	}

	async save() {
		if (!this.editor) return;
		const $button = this.$root.find("[data-action=save]").prop("disabled", true);
		try {
			await this.on_save(this.mjml());
			this.close();
		} catch (e) {
			// The form says what went wrong; the design stays open to be fixed.
			$button.prop("disabled", false);
		}
	}

	cancel() {
		if (!this.dirty) return this.close();
		frappe.confirm(__("Discard the changes to this design?"), () => this.close());
	}

	close() {
		if (this.editor) this.editor.destroy();
		this.$root.remove();
		$("body").removeClass("modal-open");
		if (commons.email_designer.current === this) commons.email_designer.current = null;
	}
}

frappe.provide("commons.email_designer");
commons.email_designer.open = (options) => (commons.email_designer.current = new EmailDesigner(options));
commons.email_designer.format_mjml = format_mjml;
commons.email_designer.unescape_jinja = unescape_jinja;
commons.email_designer.as_xml = as_xml;
