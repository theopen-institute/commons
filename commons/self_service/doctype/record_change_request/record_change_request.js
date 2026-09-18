// The approver's half of a free-form value.
//
// `free_text` on `Self Service Field` lets an owner type a value whose document
// may not exist yet -- the bank they are paid into, most often. The request
// carries the text, and `check_links_exist` refuses an approval until something
// answers to it, because a Link has to resolve for the referenced record's save
// to take it.
//
// That refusal is the guard and stays the guard. What this adds is the notice
// before it: the form says which value names nothing while the approver is
// still reading the request, and offers the desk's own new-record popup against
// it -- the same `make_quick_entry` a Link field opens when you type a name it
// cannot find, prefilled the way that one is. Nothing here creates anything
// itself, and there is no endpoint behind it: the popup inserts through the
// ordinary document API, in the approver's session, under the target doctype's
// own permissions.
//
// What is missing is decided by the server and arrives with the document --
// `RecordChangeRequest.onload`, which reads the same `missing_links` the refusal
// does, so the notice and the refusal cannot come to disagree.

frappe.ui.form.on("Record Change Request", {
	refresh(frm) {
		// A settled request is history: the values are either applied or they
		// never will be, and neither is something to create master data for.
		if (frm.doc.docstatus !== 0) {
			return;
		}

		const missing = (frm.doc.__onload && frm.doc.__onload.missing_links) || [];
		if (!missing.length) {
			return;
		}

		// No clearing first: `refresh_header` resets the headline and the custom
		// buttons before any script refresh runs, so both are already empty.
		frm.dashboard.add_comment(missing.map(gap_line).join("<br>"), "yellow", true);

		for (const gap of missing) {
			if (gap.creatable) {
				frm.add_custom_button(__("Create {0}", [__(gap.target)]), () =>
					create_missing(frm, gap)
				);
			}
		}
	},
});

/**
 * One value that names nothing, as a line of the headline.
 *
 * Values are escaped because they are typed by whoever raised the request, and
 * this is going into the headline as HTML.
 */
function gap_line(gap) {
	const parts = [
		__("{0} names a {1} called <b>{2}</b>, and there is no such record yet.", [
			frappe.utils.escape_html(gap.label),
			__(gap.target),
			frappe.utils.escape_html(gap.value),
		]),
	];

	// Against duplicates. A typed value that matches nothing may still be
	// something the site holds under a slightly different name, and the approver
	// is the only person placed to notice before a second one exists.
	if (gap.suggestions.length) {
		parts.push(
			__("Already on file: {0} — worth checking it is not one of those.", [
				gap.suggestions.map(frappe.utils.escape_html).join(", "),
			])
		);
	}

	if (!gap.creatable) {
		parts.push(
			gap.name_field
				? __("Creating {0} records is not yours to do, so somebody who can has to add it first.", [
						__(gap.target),
				  ])
				: __("{0} records are named automatically, so one created here would not answer to that name.", [
						__(gap.target),
				  ])
		);
	}

	return parts.join(" ");
}

/**
 * The desk's own new-record popup, prefilled with the value.
 *
 * `name_field` is the route option Frappe reads to decide where a typed value
 * goes -- the autoname field, `__newname`, or the title -- so nothing here has
 * to know how the target is named. A doctype with no quick entry opens its full
 * form instead, prefilled the same way, which is the framework's answer rather
 * than one of ours.
 */
function create_missing(frm, gap) {
	frappe.route_options = { name_field: gap.value };
	frappe.ui.form.make_quick_entry(gap.target, () => frm.reload_doc());
}
