/**
 * Puts a Bikram Sambat readout, and a Bikram Sambat calendar, on every Date and
 * Datetime field in the desk.
 *
 * Nothing Nepali is ever stored. The document keeps its Gregorian value exactly
 * as before; this is a second way to read and to enter the same date, and if the
 * whole file failed to load, every field would still work.
 *
 * Switched on by "Enable Bikram Sambat Calendar" in Commons Settings, which the
 * desk reads from `frappe.boot.commons_features`. A site that has not ticked it
 * gets nothing -- not even the patches below -- which is what a shared-tools app
 * owes the sites that installed it for something else.
 *
 * ## Why this is a prototype patch and not a subclass
 *
 * The obvious move, and the one NepalERP made, is
 * `frappe.ui.form.ControlDate = class extends frappe.ui.form.ControlDate {...}`.
 * It has two problems, and the second is silent.
 *
 * The loud one: two apps cannot both do it and survive; whichever bundle loads
 * last is the only one whose `make_input` ever runs.
 *
 * The quiet one: `datetime.js` says `ControlDatetime extends
 * frappe.ui.form.ControlDate` at class-definition time, and that expression is
 * evaluated when core's bundle loads -- long before any app bundle. Rebinding
 * the name afterwards leaves `ControlDatetime` pointing at the *original* class,
 * so a subclass silently never reaches Datetime fields at all. NepalERP's
 * calendar has never appeared on one, and nothing anywhere reports that.
 *
 * Patching the prototype has neither problem: `ControlDatetime` inherits from
 * the same object it always did, and wrapping rather than replacing means
 * another app's patch composes with this one instead of erasing it.
 *
 * ## Where the readout gets its value
 *
 * From the input's own displayed text, on every `set_input` -- which is core's
 * single funnel for "this control now shows a different value", covering script
 * assignment, `fetch_from`, defaults, a doc reload, an undo and a route change
 * alike. The old implementation refreshed on `blur` behind a 100ms timer, so a
 * value that arrived any other way left a stale Nepali date sitting beside a
 * changed Gregorian one, which is worse than showing nothing.
 *
 * Reading the *displayed* text rather than the model value also settles the time
 * zone question without a single line about time zones: what the input shows is
 * already in the user's zone for a Datetime, and has none for a Date.
 */

import { format, from_gregorian } from "./bikram_sambat.js";
import { picker } from "./picker.js";

frappe.provide("commons.bikram_sambat");

/**
 * The fieldtypes that get a readout.
 *
 * Checked on every patched method rather than assumed from the class, because
 * `ControlTime` also extends `ControlDate` and so inherits all three patches.
 * A Time field has no date to convert, and `Date Range` -- which extends
 * `ControlData`, not this class -- is not reached at all.
 */
const READOUT_FIELDTYPES = ["Date", "Datetime"];

/**
 * Sites that ticked the box in Commons Settings, and no one else.
 *
 * Read once: the setting reaches the desk through boot, so it cannot change
 * without a reload, and this is consulted on every control that is built.
 */
let enabled = null;
function is_enabled() {
	// Only cache once boot has actually arrived: a patch that ran a moment too
	// early would otherwise pin the answer to "no" for the rest of the session.
	if (enabled === null && frappe.boot?.commons_features) {
		enabled = frappe.boot.commons_features.bikram_sambat === true;
	}
	return enabled === true;
}

/**
 * The token shown when the field is empty.
 *
 * Without it there is nothing to click: a blank field would have no readout, so
 * the Bikram Sambat calendar would be reachable only on dates that already had
 * a value -- which is exactly backwards, since an empty field is the one you
 * most want to fill from it.
 *
 * A flag rather than a word because it has to survive being 12px wide in the
 * corner of a grid cell, and because it says "other calendar here" without
 * needing to be read. Windows has no colour flag glyphs and renders this as
 * "NP", which is still a legible token; swapping this constant for "वि.सं." is
 * the one-line change if that matters on a given deployment.
 */
const EMPTY_TOKEN = "🇳🇵";

/**
 * The Gregorian date the control is currently showing, as displayed text.
 *
 * Which element that text lives in depends on whether the field is editable, and
 * core's own signal for that is the `hide` class it puts on the input area. When
 * the field is writable the input is the live source -- it updates on every
 * keystroke, which `control.value` does not. When it is read-only core stops
 * writing to the input altogether and refreshes only `control.value`, so the
 * input still holds whatever it last had, which may be stale.
 *
 * `format_for_input` is the control's own method, so the read-only string is
 * produced exactly the way the editable one is, Datetime's shift into the user's
 * time zone included.
 */
function displayed_value(control) {
	const input_hidden = control.input_area && $(control.input_area).hasClass("hide");
	return (
		(input_hidden ? control.format_for_input?.(control.value) : control.$input?.val()) || ""
	);
}

/** The Bikram Sambat date the control is currently showing, or null. */
function current_bs(control) {
	const shown = displayed_value(control);
	if (!shown) return null;
	const date = frappe.datetime.user_to_obj(shown);
	if (!(date instanceof Date) || Number.isNaN(date.getTime())) return null;
	return from_gregorian(date);
}

function applies_to(control) {
	return is_enabled() && READOUT_FIELDTYPES.includes(control.df?.fieldtype);
}

/**
 * Hang the readout at the right-hand edge of the input.
 *
 * A `<button>` rather than the second `<input>` the old implementation used: an
 * input is a tab stop, is submitted with forms, is picked up by anything walking
 * `.frappe-control input`, and announces itself to a screen reader as an empty
 * unlabelled text field. This is `tabindex="-1"` so it never lengthens the tab
 * path through a form -- a form with twenty date fields would otherwise take
 * forty tabs to cross -- and is reachable from the keyboard with `b` on the
 * input instead, mirroring the `t` core already binds there for "today".
 */
function attach(control) {
	if (!applies_to(control) || control.$bs_readout || !control.$input) return;

	// Hang the readout on `.control-input-wrapper`, the parent of *both* the
	// editable `.control-input` and the read-only `.control-value` -- not on
	// either of them.
	//
	// Core swaps those two by putting `hide` on one and taking it off the other,
	// so a readout living inside `.control-input` vanishes the moment a field
	// goes read-only and has to be redrawn somewhere else, which is what made it
	// jump from the right edge of the field to just after the value. Toggling
	// `set_posting_time` on a Purchase Invoice does exactly that swap, live.
	// Anchored to the wrapper, the same element stays in the same place and only
	// its text changes.
	//
	// `only_input` -- grid cells, filter rows -- has no wrapper at all; there
	// `input_area` is the `.frappe-control` itself and there is no read-only
	// rendering to swap to.
	const host = control.$input_wrapper?.length ? control.$input_wrapper : $(control.input_area);
	if (!host?.length) return;
	host.addClass("bs-readout-host");

	control.$bs_readout = $(
		'<button type="button" class="commons-bs-readout" tabindex="-1"></button>',
	)
		.attr("title", __("Bikram Sambat — click, or press B in the field, to pick a date"))
		.appendTo(host);

	// `only_input` is core's flag for the compact renderings -- grid cells,
	// filter rows -- where an inline readout has no room to sit beside the text.
	// There it hides while the field has focus and the cell is being typed in.
	const wrapper = host.closest(".frappe-control").addClass("has-bs-readout");
	if (control.only_input) wrapper.addClass("bs-compact");

	control.$bs_readout.on("click", (event) => {
		event.preventDefault();
		toggle_picker(control);
	});

	control.$input.on("keydown", (event) => {
		if (event.ctrlKey || event.metaKey || event.altKey) return;
		if (String(event.key).toLowerCase() !== "b") return;
		event.preventDefault();
		toggle_picker(control);
	});

	// `set_input` covers every programmatic change, but not the keystrokes
	// between them: without this the readout would lag a date being typed by
	// hand until the field was left.
	control.$input.on("input", () => refresh(control));

	refresh(control);
}

function refresh(control) {
	if (!control.$bs_readout) return;
	const bs = current_bs(control);
	const text = bs ? format(bs) : "";
	const pickable = can_pick(control);

	// Three states, not two. A date converts and is shown. An empty field shows
	// the token, so the calendar is still one click away. A field holding a date
	// outside the calendar's span -- or half-typed -- shows nothing at all,
	// because the honest answer there is silence rather than a guess.
	const placeholder = !text && !displayed_value(control) && pickable;

	control.$bs_readout
		.text(text || (placeholder ? EMPTY_TOKEN : ""))
		.toggleClass("is-placeholder", placeholder)
		// A read-only field still shows its Bikram Sambat date; it just is not a
		// button any more.
		.toggleClass("is-static", !pickable)
		.toggleClass("hide", !text && !placeholder)
		.attr(
			"aria-label",
			text
				? __("Bikram Sambat: {0}. Open the Bikram Sambat calendar.", [text])
				: __("Open the Bikram Sambat calendar"),
		);
}

/** A second click on the readout puts the calendar away again. */
function toggle_picker(control) {
	if (picker.is_open && picker.anchor === control.$input.get(0)) return picker.close();
	open_picker(control);
}

/** Whether a date can still be chosen for this field. */
function can_pick(control) {
	if (!control.$input || control.$input.prop("disabled")) return false;
	return control.disp_status !== "Read" && !control.df.read_only;
}

function open_picker(control) {
	if (!control.$bs_readout || !can_pick(control)) return;

	// The two pickers are alternatives, not layers.
	control.datepicker?.hide();

	picker.open({
		anchor: control.$input.get(0),
		focus_on_close: control.$bs_readout.get(0),
		selected: current_bs(control),
		on_select: (date) => apply(control, date),
	});
}

/**
 * Write the picked date back through core's own datepicker.
 *
 * `selectDate` formats the value into the input to the site's date format and
 * fires the `onSelect` that core wired to `$input.trigger("change")` -- so the
 * value lands by exactly the path a click on the Gregorian calendar uses:
 * `parse`, `validate`, then the model. That is what makes this work in a child
 * table row, a dialog, Quick Entry and a list filter without knowing about any
 * of them.
 *
 * The old implementation instead assigned `cur_frm.doc[fieldname]` and called
 * `refresh_field`. On a plain form field the two look the same. In a grid row it
 * writes the child field onto the *parent* document; in a dialog or a filter
 * there is no `cur_frm` at all; and everywhere it skips validation and the
 * change event, so dependent fields never recalculate.
 */
function apply(control, date) {
	if (!control.datepicker) return;

	// Carry the clock across. `selectDate` takes the time from the Date it is
	// given, so a bare midnight would silently wipe the time someone had already
	// entered -- and a widget whose whole premise is that it only changes how a
	// date is *displayed* has no business changing the instant it refers to.
	if (control.df.fieldtype === "Datetime") {
		const shown = control.$input.val();
		const existing = shown ? frappe.datetime.user_to_obj(shown) : null;
		const timepicker = control.datepicker.timepicker;
		if (existing instanceof Date && !Number.isNaN(existing.getTime())) {
			date.setHours(existing.getHours(), existing.getMinutes(), existing.getSeconds());
		} else if (timepicker) {
			date.setHours(timepicker.hours || 0, timepicker.minutes || 0, timepicker.seconds || 0);
		}
	}

	control.datepicker.selectDate(date);
}

/** Replace `name` on `prototype` with a version that runs `after` afterwards. */
function wrap(prototype, name, after) {
	const original = prototype[name];
	if (typeof original !== "function") return false;
	prototype[name] = function (...args) {
		const result = original.apply(this, args);
		try {
			after(this);
		} catch (error) {
			// A decoration is never worth taking a field down for.
			console.error("commons: Bikram Sambat readout failed", error);
		}
		return result;
	};
	return true;
}

(function patch_date_controls() {
	const date_control = frappe.ui?.form?.ControlDate;
	const datetime_control = frappe.ui?.form?.ControlDatetime;

	// Feature-detect rather than assume. If core reshapes these controls, the
	// readout should quietly stop appearing, not throw on every form.
	if (!date_control?.prototype) return;

	// Boot has arrived and the site has not asked for this: leave the controls
	// exactly as core built them. Before boot there is no answer yet, so the
	// patches go on and `is_enabled` decides on each call instead.
	if (frappe.boot?.commons_features && !is_enabled()) return;

	wrap(date_control.prototype, "make_input", attach);

	// `set_input` and `set_disp_area` are inherited from ControlData; assigning
	// here puts an own property on ControlDate.prototype, which shadows it for
	// Date and Datetime and leaves every other fieldtype untouched.
	// Both, because they are the two ends of the swap: `set_input` is the only one
	// core calls while a field is editable, and `set_disp_area` the only one it
	// calls once the field has gone read-only.
	wrap(date_control.prototype, "set_input", refresh);
	wrap(date_control.prototype, "set_disp_area", refresh);

	// ControlDatetime overrides none of the three, so it inherits all of them --
	// which is the whole reason for patching here rather than subclassing. The
	// check below is cheap and would say so if a future core version changed that.
	if (datetime_control?.prototype) {
		for (const method of ["make_input", "set_input", "set_disp_area"]) {
			if (Object.prototype.hasOwnProperty.call(datetime_control.prototype, method)) {
				console.warn(
					`commons: ControlDatetime now defines its own ${method}(); ` +
						"the Bikram Sambat readout needs patching there too.",
				);
			}
		}
	}
})();

// Exposed so a site script can format a date the same way the fields do, and so
// the conversion is testable from the console. `format` takes `{script: "latin"}`
// for the cases that want `2081-05-18` rather than `२०८१-०५-१८`.
Object.assign(commons.bikram_sambat, { format, from_gregorian, picker });
