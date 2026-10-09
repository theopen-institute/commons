/**
 * The Bikram Sambat date as a tooltip on Date and Datetime values shown in
 * tables: a child table's rows at rest, list views, Report View and query
 * reports.
 *
 * A tooltip rather than the inline readout the fields carry, because a table
 * cell is narrow and its width is set by the column, not by its content: a
 * second date beside the first would be clipped by the ellipsis in most of
 * them. The cell looks exactly as before; pointing at the date names the other
 * calendar.
 *
 * ## Why a flag and not a formatter patch
 *
 * All four tables draw a date through `frappe.format`, but so do filter pills,
 * Report View's filter descriptions ("Posting Date is 09-10-2026"), titles and
 * messages, which are plain text and would show the markup. So the Date and
 * Datetime formatters only add the tooltip while `cell_depth` says a table cell
 * is being drawn, and each table's cell-drawing method raises it for the length
 * of the call. Report scripts' own formatters (most of ERPNext's) still reach
 * the date through the default one, so they get the tooltip too.
 *
 * Like the readout, the date is read back from the formatter's own output --
 * the Gregorian text the cell shows, already in the user's time zone for a
 * Datetime -- so the two calendars cannot disagree about which day it is.
 */

import { format, from_gregorian } from "./bikram_sambat.js";
import { is_enabled } from "./date_control.js";

let cell_depth = 0;

/** Run `fn` with the tooltip on, and return what it returns. */
function in_cell(fn) {
	cell_depth++;
	try {
		return fn();
	} finally {
		cell_depth--;
	}
}

function with_tooltip(text) {
	if (!text || typeof text !== "string") return text;
	const date = frappe.datetime.user_to_obj(text);
	if (!(date instanceof Date) || Number.isNaN(date.getTime())) return text;
	const bs = from_gregorian(date);
	if (!bs) return text;
	const title = frappe.utils.escape_html(__("Bikram Sambat: {0}", [format(bs)]));
	return `<span class="commons-bs-tip" title="${title}">${text}</span>`;
}

/** Replace `name` on `prototype` with a version that runs inside `in_cell`. */
function wrap_in_cell(prototype, name) {
	const original = prototype?.[name];
	if (typeof original !== "function") return;
	prototype[name] = function (...args) {
		return in_cell(() => original.apply(this, args));
	};
}

/** The same, for a `format(value, row, column, data, filter)` on a column. */
function wrap_column_format(column) {
	const original = column?.format;
	if (typeof original !== "function") return column;
	column.format = function (...args) {
		// DataTable calls it again with `filter` set to get the text it searches;
		// the tooltip has no business there.
		if (args[4]) return original.apply(this, args);
		return in_cell(() => original.apply(this, args));
	};
	return column;
}

(function patch_table_cells() {
	if (frappe.boot?.commons_features && !is_enabled()) return;

	for (const fieldtype of ["Date", "Datetime"]) {
		const formatter = frappe.form?.formatters?.[fieldtype];
		if (typeof formatter !== "function") continue;
		frappe.form.formatters[fieldtype] = function (...args) {
			const text = formatter.apply(this, args);
			if (cell_depth === 0 || !is_enabled()) return text;
			try {
				return with_tooltip(text);
			} catch (error) {
				console.error("commons: Bikram Sambat tooltip failed", error);
				return text;
			}
		};
	}

	// List view: each column's cell.
	wrap_in_cell(frappe.views?.ListView?.prototype, "get_column_html");

	// Report View: the format function each column is built with.
	const report_view = frappe.views?.ReportView?.prototype;
	if (typeof report_view?.build_column === "function") {
		const build_column = report_view.build_column;
		report_view.build_column = function (...args) {
			return wrap_column_format(build_column.apply(this, args));
		};
	}

	// Query and script reports: the same, after the report's own formatter is
	// folded in.
	const query_report = frappe.views?.QueryReport?.prototype;
	if (typeof query_report?.prepare_columns === "function") {
		const prepare_columns = query_report.prepare_columns;
		query_report.prepare_columns = function (...args) {
			const columns = prepare_columns.apply(this, args);
			return Array.isArray(columns) ? columns.map(wrap_column_format) : columns;
		};
	}

	// A child table's rows at rest. `GridRow` is not exported anywhere, so its
	// prototype is reached through the first grid a Table control builds: the
	// header row exists once `make_head` has run, which is before any data row
	// is drawn.
	const table = frappe.ui?.form?.ControlTable?.prototype;
	if (typeof table?.make !== "function") return;
	const make = table.make;
	let grid_patched = false;
	table.make = function (...args) {
		const result = make.apply(this, args);
		const grid = grid_patched ? null : Object.getPrototypeOf(this.grid || {});
		if (grid && typeof grid.make_head === "function") {
			grid_patched = true;
			const make_head = grid.make_head;
			let row_patched = false;
			grid.make_head = function (...head_args) {
				const head = make_head.apply(this, head_args);
				if (!row_patched && this.header_row) {
					row_patched = true;
					wrap_in_cell(Object.getPrototypeOf(this.header_row), "_format_static_value");
				}
				return head;
			};
		}
		return result;
	};
})();
