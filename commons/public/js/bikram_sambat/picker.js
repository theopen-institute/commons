/**
 * The Bikram Sambat month calendar that drops out of a date field.
 *
 * One instance for the whole desk, not one per field. A form with a dozen date
 * fields built a dozen jQuery datepicker instances under the old NepalERP
 * implementation, each with its own detached DOM and its own document-level
 * handlers, all to render a popup only one of which can ever be visible. This is
 * a single node, moved and re-rendered as it is opened against each anchor.
 *
 * It knows nothing about Frappe controls. It is handed a selected date and an
 * anchor element, and it calls back with the Gregorian `Date` the user picked;
 * deciding what that means for a document is [date_control.js]'s job.
 *
 * Deliberately not built on air-datepicker, which core uses for the Gregorian
 * picker. Its month grid derives cell counts, weekday offsets and navigation
 * from `Date` arithmetic, so a Bikram Sambat month -- 29 to 32 days, in a year
 * with no Gregorian counterpart -- cannot be expressed as a configuration of it,
 * only as a fight with it. The styling is matched to core's instead, so the two
 * pickers still read as the same control.
 */

import {
	MAX_BS_YEAR,
	MIN_BS_YEAR,
	add_months,
	days_in_month,
	from_gregorian,
	month_name,
	to_devanagari_digits,
	to_gregorian,
	today,
	weekday,
	weekday_name,
} from "./bikram_sambat.js";

/** Nepal's weekend, and the reason the last column is tinted. */
const SATURDAY = 6;

class BikramSambatPicker {
	constructor() {
		this.root = null;
		this.anchor = null;
		this.on_select = null;
		this.focus_on_close = null;
		this.cursor = null; // the month on screen
		this.selected = null; // the field's own value, if any
		this.focused = null; // the day the keyboard is on
	}

	/**
	 * Show the picker under `anchor`, opened on `selected` (or today).
	 *
	 * `on_select` receives a `Date` at local midnight. The picker closes itself
	 * first, so a caller is free to move focus.
	 *
	 * `focus_on_close` is where focus goes afterwards, and is separate from
	 * `anchor` for one specific reason: the anchor is the date input, and core
	 * configures air-datepicker with `showEvent: "focus"`, so returning focus
	 * there would pop the Gregorian picker open the instant this one closed.
	 */
	open({ anchor, focus_on_close, selected, on_select }) {
		this.close();
		this.anchor = anchor;
		this.focus_on_close = focus_on_close || anchor;
		this.on_select = on_select;
		this.selected = selected || null;
		this.cursor = selected || today() || { year: MIN_BS_YEAR, month: 1, day: 1 };
		this.focused = this.selected || { ...this.cursor };

		this.build();
		this.render();
		this.position();
		this.bind_dismissal();
		// Focus the grid, not the document: arrow keys should drive the calendar
		// the moment it appears, and Escape should come back here.
		this.grid.querySelector('[tabindex="0"]')?.focus({ preventScroll: true });
	}

	close() {
		if (!this.root) return;
		this.unbind_dismissal();
		const returning_to = this.focus_on_close;
		this.root.remove();
		this.root = null;
		this.anchor = null;
		this.focus_on_close = null;
		this.on_select = null;
		// Hand focus back to whatever opened us, so keyboard users are not
		// dumped at the top of the document.
		if (returning_to && document.contains(returning_to))
			returning_to.focus({ preventScroll: true });
	}

	get is_open() {
		return Boolean(this.root);
	}

	build() {
		this.root = document.createElement("div");
		this.root.className = "commons-bs-picker";
		this.root.setAttribute("role", "dialog");
		this.root.setAttribute("aria-modal", "false");
		this.root.setAttribute("aria-label", __("Bikram Sambat date picker"));

		this.root.innerHTML = `
			<div class="commons-bs-nav">
				<button type="button" class="commons-bs-step" data-step="-1" tabindex="-1"
					aria-label="${frappe.utils.escape_html(__("Previous month"))}">&lsaquo;</button>
				<select class="commons-bs-select commons-bs-month" aria-label="${frappe.utils.escape_html(__("Month"))}"></select>
				<select class="commons-bs-select commons-bs-year" aria-label="${frappe.utils.escape_html(__("Year"))}"></select>
				<button type="button" class="commons-bs-step" data-step="1" tabindex="-1"
					aria-label="${frappe.utils.escape_html(__("Next month"))}">&rsaquo;</button>
			</div>
			<div class="commons-bs-weekdays" aria-hidden="true"></div>
			<div class="commons-bs-grid" role="group" aria-label="${frappe.utils.escape_html(
				__("Days"),
			)}"></div>
			<div class="commons-bs-foot">
				<button type="button" class="commons-bs-today" tabindex="-1"></button>
				<span class="commons-bs-gregorian"></span>
			</div>`;

		this.month_select = this.root.querySelector(".commons-bs-month");
		this.year_select = this.root.querySelector(".commons-bs-year");
		this.grid = this.root.querySelector(".commons-bs-grid");
		this.gregorian_label = this.root.querySelector(".commons-bs-gregorian");

		const today_button = this.root.querySelector(".commons-bs-today");
		today_button.textContent = "आज";
		today_button.setAttribute("aria-label", __("Today"));

		this.root.querySelector(".commons-bs-weekdays").innerHTML = Array.from(
			{ length: 7 },
			(_, index) =>
				`<span class="${index === SATURDAY ? "is-weekend" : ""}">${frappe.utils.escape_html(
					weekday_name(index),
				)}</span>`,
		).join("");

		for (let month = 1; month <= 12; month++) {
			this.month_select.add(new Option(month_name(month), String(month)));
		}
		for (let year = MIN_BS_YEAR; year <= MAX_BS_YEAR; year++) {
			this.year_select.add(new Option(to_devanagari_digits(year), String(year)));
		}

		this.root.addEventListener("mousedown", (event) => {
			// Keep the field's own focus while clicking around inside the popup;
			// without this the input blurs and the form thinks it was left.
			if (event.target.tagName !== "SELECT") event.preventDefault();
		});
		this.root
			.querySelectorAll(".commons-bs-step")
			.forEach((button) =>
				button.addEventListener("click", () => this.step(Number(button.dataset.step))),
			);
		this.month_select.addEventListener("change", () =>
			this.go_to({ ...this.cursor, month: Number(this.month_select.value) }),
		);
		this.year_select.addEventListener("change", () =>
			this.go_to({ ...this.cursor, year: Number(this.year_select.value) }),
		);
		today_button.addEventListener("click", () => {
			const now = today();
			if (now) this.choose(now);
		});
		this.grid.addEventListener("click", (event) => {
			const cell = event.target.closest("[data-day]");
			if (cell) this.choose({ ...this.cursor, day: Number(cell.dataset.day) });
		});
		this.grid.addEventListener("keydown", (event) => this.on_keydown(event));

		document.body.appendChild(this.root);
	}

	/** Move the visible month, clamping the day to one the new month has. */
	go_to(bs) {
		const day = Math.min(bs.day, days_in_month(bs.year, bs.month) || bs.day);
		const next = { year: bs.year, month: bs.month, day };
		if (!to_gregorian(next)) return;
		this.cursor = next;
		this.focused = next;
		this.render();
		this.grid.querySelector('[tabindex="0"]')?.focus({ preventScroll: true });
	}

	step(delta) {
		const next = add_months(this.cursor, delta);
		if (next) this.go_to(next);
	}

	choose(bs) {
		const date = to_gregorian(bs);
		if (!date) return;
		const callback = this.on_select;
		this.close();
		callback?.(date);
	}

	render() {
		this.month_select.value = String(this.cursor.month);
		this.year_select.value = String(this.cursor.year);

		const length = days_in_month(this.cursor.year, this.cursor.month);
		const leading = weekday({ ...this.cursor, day: 1 });
		const now = today();
		const cells = [];

		for (let blank = 0; blank < leading; blank++) {
			cells.push('<span class="commons-bs-cell is-blank" aria-hidden="true"></span>');
		}
		for (let day = 1; day <= length; day++) {
			const bs = { year: this.cursor.year, month: this.cursor.month, day };
			const classes = ["commons-bs-cell"];
			if (weekday(bs) === SATURDAY) classes.push("is-weekend");
			if (same_day(bs, this.selected)) classes.push("is-selected");
			if (same_day(bs, now)) classes.push("is-today");
			// Roving tabindex: exactly one cell is reachable by Tab, and the arrow
			// keys move which one it is.
			const focusable = same_day(bs, this.focused) ? 0 : -1;
			const gregorian = to_gregorian(bs);
			cells.push(
				`<span class="${classes.join(" ").trim()}" role="button" data-day="${day}" tabindex="${focusable}"` +
					(same_day(bs, now) ? ' aria-current="date"' : "") +
					(same_day(bs, this.selected) ? ' aria-pressed="true"' : "") +
					` aria-label="${frappe.utils.escape_html(
						`${to_devanagari_digits(day)} ${month_name(bs.month)} ${to_devanagari_digits(
							bs.year,
						)} — ${frappe.datetime.obj_to_user(gregorian)}`,
					)}">${to_devanagari_digits(day)}</span>`,
			);
		}
		this.grid.innerHTML = cells.join("");

		// If the day the keyboard is on is not in this month, put it on day one so
		// there is always exactly one tab stop.
		if (!this.grid.querySelector('[tabindex="0"]')) {
			this.focused = { ...this.cursor, day: 1 };
			this.grid.querySelector('[data-day="1"]')?.setAttribute("tabindex", "0");
		}
		this.show_gregorian(this.focused);
	}

	show_gregorian(bs) {
		const date = to_gregorian(bs);
		this.gregorian_label.textContent = date ? frappe.datetime.obj_to_user(date) : "";
	}

	on_keydown(event) {
		const moves = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
		if (event.key in moves) {
			event.preventDefault();
			return this.move(moves[event.key]);
		}
		if (event.key === "PageUp" || event.key === "PageDown") {
			event.preventDefault();
			return this.step(event.key === "PageUp" ? -1 : 1);
		}
		if (event.key === "Home" || event.key === "End") {
			event.preventDefault();
			const day =
				event.key === "Home" ? 1 : days_in_month(this.cursor.year, this.cursor.month);
			this.focused = { ...this.cursor, day };
			return this.refocus();
		}
		if (event.key === "Enter" || event.key === " ") {
			event.preventDefault();
			return this.choose(this.focused);
		}
		if (event.key === "Escape") {
			event.preventDefault();
			return this.close();
		}
	}

	/** Step the keyboard cursor by whole days, crossing month boundaries. */
	move(delta) {
		const from = to_gregorian(this.focused);
		if (!from) return;
		const moved = from_gregorian(
			new Date(from.getFullYear(), from.getMonth(), from.getDate() + delta),
		);
		if (!moved) return; // walked off the end of the supported span
		const changed_month = moved.year !== this.cursor.year || moved.month !== this.cursor.month;
		this.focused = moved;
		if (changed_month) {
			this.cursor = moved;
			this.render();
		}
		this.refocus();
	}

	refocus() {
		this.grid
			.querySelectorAll("[data-day]")
			.forEach((cell) =>
				cell.setAttribute(
					"tabindex",
					Number(cell.dataset.day) === this.focused.day ? "0" : "-1",
				),
			);
		this.grid.querySelector('[tabindex="0"]')?.focus({ preventScroll: true });
		this.show_gregorian(this.focused);
	}

	/**
	 * Place the popup under the anchor, flipping above it when the window has no
	 * room below and clamping so it never hangs off the right edge.
	 */
	position() {
		const anchor = this.anchor.getBoundingClientRect();
		const popup = this.root.getBoundingClientRect();
		const margin = 4;

		let top = anchor.bottom + margin;
		if (top + popup.height > window.innerHeight && anchor.top - popup.height - margin > 0) {
			top = anchor.top - popup.height - margin;
		}
		const left = Math.max(
			margin,
			Math.min(anchor.left, window.innerWidth - popup.width - margin),
		);

		// Fixed rather than absolute, so a popup opened inside a scrolling modal
		// body does not have to guess which ancestor establishes its containing
		// block; `reposition` keeps it glued to the anchor.
		this.root.style.top = `${top}px`;
		this.root.style.left = `${left}px`;
	}

	reposition() {
		if (!this.root || !this.anchor) return;
		if (!document.contains(this.anchor)) return this.close();
		this.position();
	}

	bind_dismissal() {
		this.dismiss = (event) => {
			if (!this.root) return;
			if (this.root.contains(event.target)) return;
			if (this.focus_on_close?.contains(event.target)) return;
			this.close();
		};
		this.escape = (event) => {
			if (event.key === "Escape") this.close();
		};
		this.reflow = () => this.reposition();

		document.addEventListener("mousedown", this.dismiss, true);
		document.addEventListener("keydown", this.escape, true);
		// Capture, so scrolling any ancestor -- a modal body, a form section --
		// moves the popup rather than leaving it stranded.
		window.addEventListener("scroll", this.reflow, true);
		window.addEventListener("resize", this.reflow);
	}

	unbind_dismissal() {
		document.removeEventListener("mousedown", this.dismiss, true);
		document.removeEventListener("keydown", this.escape, true);
		window.removeEventListener("scroll", this.reflow, true);
		window.removeEventListener("resize", this.reflow);
	}
}

function same_day(a, b) {
	return Boolean(a && b && a.year === b.year && a.month === b.month && a.day === b.day);
}

/** The desk's one picker. */
export const picker = new BikramSambatPicker();
