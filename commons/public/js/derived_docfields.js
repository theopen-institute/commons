// Lets the desk treat a derived field (`commons.derived_docfields`) as the
// real field it reads as, and keeps one up to date on a form as its links change.
//
// A derived field is a Custom Field with `is_virtual` set -- that is what keeps
// core from giving it a column -- and the desk drops virtual fields in a dozen
// places: list columns, the fields a list asks the server for, List Settings,
// Report View's column picker, the filter field picker, the exporter. Each of
// those only ever meant "this has no value the server can query", which is
// exactly what stops being true for a derived field: the server joins it in.
//
// One seam, not a dozen: as a doctype's meta arrives (`frappe.meta.sync`), its
// derived fields have `is_virtual` cleared -- on this copy of the meta, in the
// browser, and nowhere else. It is safe to change because a derived field is
// always a Custom Field, never a row of the DocType's own field table, so no
// DocType form ever holds this copy and saves it back; the DocType form fetches
// its own document, and Customize Form its own rows. `read_only` is set, which
// is what core's controls, permissions and bulk edit check before offering to
// write a field. The fields are marked `_commons_derived` so they stay findable.
//
// The form half: a form loads with its derived values already in it, but a
// link changed on screen isn't saved yet, so this asks the server again
// (`commons.derived_docfields.api.resolve`) whenever a field a derived value
// depends on changes -- the link itself, the type of a Dynamic Link, and
// through a derived Link, whatever that one depends on. The answer is written
// into the form without marking it dirty: a derived value is not an edit.
//
// If core reshapes `frappe.meta.sync` the feature-detect below quietly disables
// all of it, and the worst case is today's behaviour: derived fields hidden from
// lists and pickers, as virtual fields are. Opt-in: nothing runs unless "Enable
// Derived Docfields" is ticked in Commons Settings; unticking it restores core's
// behaviour from the next reload.
(() => {
	const features = (frappe.boot && frappe.boot.commons_features) || {};
	if (!features.derived_docfields) return;
	if (!frappe.meta || typeof frappe.meta.sync !== "function") return;
	if (
		!frappe.ui ||
		!frappe.ui.form ||
		typeof frappe.ui.form.get_event_handler_list !== "function"
	)
		return;

	const is_derived = (df) =>
		Boolean(df && (df._commons_derived || (df.is_custom_field && df.derived_from)));

	const unveil_field = (df) => {
		if (!is_derived(df)) return;
		df._commons_derived = 1;
		df.is_virtual = 0;
		df.read_only = 1;
	};

	// Every place the desk keeps a doctype's fields: the meta in `locals`, and
	// `frappe.meta`'s map and list, which hold on to the first object they saw.
	const unveil = (doctype) => {
		const meta = locals.DocType && locals.DocType[doctype];
		(meta && meta.fields ? meta.fields : []).forEach(unveil_field);
		Object.values((frappe.meta.docfield_map || {})[doctype] || {}).forEach(unveil_field);
		((frappe.meta.docfield_list || {})[doctype] || []).forEach(unveil_field);
	};

	const sync = frappe.meta.sync;
	frappe.meta.sync = function (doc) {
		(doc && doc.fields ? doc.fields : []).forEach(unveil_field);
		const result = sync.apply(this, arguments);
		if (doc && doc.name) unveil(doc.name);
		return result;
	};

	// Metas that arrived before this script did.
	Object.keys(locals.DocType || {}).forEach(unveil);

	// The form half
	// -------------

	// What a doctype's derived fields depend on: fieldnames on the host whose
	// change can change one of them.
	const dependencies = (doctype) => {
		const fields = (frappe.get_meta(doctype) || {}).fields || [];
		const by_name = Object.fromEntries(fields.map((df) => [df.fieldname, df]));
		const found = new Set();

		const walk = (fieldname, seen) => {
			const df = by_name[fieldname];
			if (!df) return;
			if (!is_derived(df)) {
				found.add(fieldname);
				return;
			}
			if (seen.has(fieldname)) return;
			seen.add(fieldname);
			const link = df.derived_from.split(".")[0];
			walk(link, seen);
			const link_df = by_name[link];
			if (link_df && link_df.fieldtype === "Dynamic Link" && link_df.options) {
				walk(link_df.options, seen);
			}
		};

		const derived = fields.filter(is_derived);
		derived.forEach((df) => walk(df.fieldname, new Set()));
		return { derived: derived.map((df) => df.fieldname), sources: [...found] };
	};

	// The latest request per form, so a slow answer can't overwrite a newer one.
	const asked = new WeakMap();

	const refresh = (frm) => {
		const { derived, sources } = dependencies(frm.doctype);
		if (!derived.length) return;

		const doc = { doctype: frm.doctype, name: frm.doc.name, __islocal: frm.doc.__islocal };
		sources.forEach((fieldname) => (doc[fieldname] = frm.doc[fieldname]));

		const ticket = (asked.get(frm) || 0) + 1;
		asked.set(frm, ticket);
		frappe.xcall("commons.derived_docfields.api.resolve", { doc }).then((values) => {
			if (asked.get(frm) !== ticket || !values) return;
			Object.entries(values).forEach(([fieldname, value]) => {
				frm.doc[fieldname] = value;
				frm.refresh_field(fieldname);
			});
		});
	};

	// Handlers are registered once per doctype, on its first form. Onto core's
	// handler list directly rather than through `frappe.ui.form.on`, which would
	// also make this `frm.events[fieldname]` -- the name a doctype's own script
	// may call its own handler by.
	const wired = new Set();
	frappe.ui.form.on("*", "onload", (frm) => {
		if (wired.has(frm.doctype)) return;
		wired.add(frm.doctype);
		const { sources } = dependencies(frm.doctype);
		sources.forEach((fieldname) =>
			frappe.ui.form.get_event_handler_list(frm.doctype, fieldname).push(refresh)
		);
	});
})();
