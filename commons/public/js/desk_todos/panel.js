// The panel both hosts open: header, scrolling list, footer. It owns its own
// markup, because the desk's sidebar template is frappe's and this app does not
// edit it.
//
// Every class here is prefixed `commons-todo-`. Nothing is borrowed from core's
// notification widget, which is the nearest thing on screen: sharing its classes
// would make this break the day core restyles its own panel.

import { closeTodo, deskUrl, fetchTodos, listUrl, SORTS, SORT_STORAGE_KEY } from "./data";

const PRIORITY_TONE = { High: "red", Medium: "amber", Low: "blue" };

// "Sep 17, 2026". Parsed field by field because `new Date("2026-09-17")` is UTC
// midnight, which renders as the day before for anyone west of it.
const DUE_FORMAT = new Intl.DateTimeFormat(undefined, {
	day: "numeric",
	month: "short",
	year: "numeric",
});

function format_due(value) {
	const [y, m, d] = String(value).slice(0, 10).split("-").map(Number);
	if (!y || !m || !d) return value;
	return DUE_FORMAT.format(new Date(y, m - 1, d));
}

// ToDo.color is user-entered; only a literal hex goes near a style declaration.
const HEX_COLOR = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;

export class ToDoPanel {
	/**
	 * @param {object} opts
	 * @param {JQuery}  opts.container  where the panel element is appended
	 * @param {string}  opts.placement  "sidebar" (full height, beside the rail)
	 *                                  or "navbar" (hanging under an icon)
	 * @param {function(number)} opts.onCount  called with every fresh count
	 * @param {function():JQuery} opts.trigger the element that toggles us, so a
	 *                                  click on it is not read as a click away
	 */
	constructor(opts) {
		this.opts = opts;
		this.count = 0;
		this.todos = [];
		this.truncated = false;
		this.sort_by = this.stored_sort();
		this.build();
		this.refresh();
	}

	stored_sort() {
		try {
			const saved = localStorage.getItem(SORT_STORAGE_KEY);
			return SORTS.some((s) => s.value === saved) ? saved : "due_date";
		} catch (e) {
			// private window, or site data blocked; the default is no worse
			return "due_date";
		}
	}

	remember_sort() {
		try {
			localStorage.setItem(SORT_STORAGE_KEY, this.sort_by);
		} catch (e) {
			/* a remembered sort is a convenience, not the feature */
		}
	}

	build() {
		this.$panel = $(`
			<div class="commons-todo-panel commons-todo-panel--${this.opts.placement} hidden" role="dialog"
				aria-label="${__("To Do")}">
				<div class="commons-todo-header">
					<h2 class="commons-todo-title">
						<span>${__("To Do")}</span>
						<span class="commons-todo-title-count hidden" aria-live="polite"></span>
					</h2>
					<div class="commons-todo-actions">
						<span class="commons-todo-sort">
							<select aria-label="${__("Sort by")}" title="${__("Sort by")}">
								${SORTS.map(
									(s) =>
										`<option value="${s.value}">${frappe.utils.escape_html(
											s.label()
										)}</option>`
								).join("")}
							</select>
							${frappe.utils.icon("chevron-down", "xs")}
						</span>
						<button class="commons-todo-close btn-reset" aria-label="${__("Close")}"
							title="${__("Close")}">${frappe.utils.icon("x", "sm")}</button>
					</div>
				</div>
				<div class="commons-todo-body"></div>
				<a class="commons-todo-footer" href="${listUrl()}"></a>
			</div>
		`).appendTo(this.opts.container);

		this.$body = this.$panel.find(".commons-todo-body");
		this.$footer = this.$panel.find(".commons-todo-footer");
		this.$sort = this.$panel.find(".commons-todo-sort select").val(this.sort_by);

		this.$sort.on("change", (e) => {
			this.sort_by = e.currentTarget.value;
			this.remember_sort();
			this.refresh();
		});
		this.$panel.find(".commons-todo-close").on("click", () => this.hide());

		// Ours to open, so ours to close when the click lands elsewhere. The
		// trigger is excluded or its own press would shut what it just opened.
		$(document).on("click.commons-todo", (e) => {
			if (this.is_hidden()) return;
			const $t = $(e.target);
			if ($t.closest(this.$panel).length) return;
			const $trigger = this.opts.trigger && this.opts.trigger();
			if ($trigger && $trigger.length && $t.closest($trigger).length) return;
			this.hide();
		});
		$(document).on("page-change.commons-todo", () => this.hide());

		// An assignment reaches the user as a notification. Reusing that signal
		// avoids a global `list_update` listener, which list views call `.off()`
		// on, taking every other listener with it.
		frappe.realtime && frappe.realtime.on("notification", () => this.refresh());
	}

	is_hidden() {
		return this.$panel.hasClass("hidden");
	}

	hide() {
		this.$panel.addClass("hidden");
	}

	toggle() {
		this.$panel.toggleClass("hidden");
		if (!this.is_hidden()) this.refresh();
	}

	refresh() {
		return fetchTodos(this.sort_by).then((r) => {
			if (!r) return;
			this.todos = r.todos || [];
			this.truncated = !!r.truncated;
			this.set_count(r.count || 0);
			this.render();
		});
	}

	set_count(count) {
		this.count = count;
		const $c = this.$panel.find(".commons-todo-title-count");
		count ? $c.text(count).removeClass("hidden") : $c.addClass("hidden");
		this.opts.onCount && this.opts.onCount(count);
	}

	// Only the two sorts that group get headings; due date and recency are
	// continuous, and a heading per day would be noise.
	group_of(todo) {
		if (this.sort_by === "doctype") {
			return todo.reference_type ? __(todo.reference_type) : __("Not linked");
		}
		if (this.sort_by === "urgency") return __(todo.priority || "Medium");
		return null;
	}

	render() {
		this.$body.empty();

		if (!this.todos.length) {
			this.$body.append(`
				<div class="commons-todo-empty">
					<div class="commons-todo-empty-title">${__("Nothing to do")}</div>
					<div class="commons-todo-empty-text">${__("You have no open to-dos.")}</div>
				</div>`);
		} else {
			let last = null;
			this.todos.forEach((todo) => {
				const group = this.group_of(todo);
				if (group && group !== last) {
					this.$body.append(
						`<div class="commons-todo-group">${frappe.utils.escape_html(group)}</div>`
					);
					last = group;
				}
				this.$body.append(this.row(todo));
			});
		}

		this.$footer.text(
			this.truncated ? __("See all {0} to-dos", [this.count]) : __("See all to-dos")
		);
	}

	meta(todo) {
		const bits = [];

		if (todo.reference_type && todo.reference_name) {
			bits.push(
				`<span class="commons-todo-ref">${frappe.utils.escape_html(
					`${__(todo.reference_type)}: ${todo.reference_name}`
				)}</span>`
			);
		}
		if (todo.date) {
			const due = format_due(todo.date);
			bits.push(
				`<span class="commons-todo-due ${todo.overdue ? "is-overdue" : ""}">${
					todo.overdue ? __("Overdue {0}", [due]) : __("Due {0}", [due])
				}</span>`
			);
		}
		// redundant once the list is grouped by it
		if (todo.priority && this.sort_by !== "urgency") {
			const tone = PRIORITY_TONE[todo.priority] || "gray";
			bits.push(
				`<span class="commons-todo-priority ${tone}">${__(todo.priority)}</span>`
			);
		}

		return bits.length ? `<div class="commons-todo-meta">${bits.join("")}</div>` : "";
	}

	row(todo) {
		// `title` is plain text from the server, but it is still user content,
		// so it is escaped again on the way into the DOM.
		const $row = $(`
			<div class="commons-todo-row" data-name="${frappe.utils.escape_html(todo.name)}">
				<button class="commons-todo-tick btn-reset" aria-label="${__("Mark as closed")}"
					title="${__("Mark as closed")}">${frappe.utils.icon("check", "sm")}</button>
				<a class="commons-todo-link" href="${deskUrl(todo)}">
					<div class="commons-todo-text">${
						frappe.utils.escape_html(todo.title) ||
						`<span class="text-muted">${__("No description")}</span>`
					}</div>
					${this.meta(todo)}
				</a>
			</div>`);

		if (HEX_COLOR.test(todo.color || "")) {
			$row.css("border-left-color", todo.color);
		}

		$row.find(".commons-todo-tick").on("click", (e) => {
			e.preventDefault();
			e.stopPropagation();
			this.close_one(todo, $row);
		});
		$row.find(".commons-todo-link").on("click", () => this.hide());

		return $row;
	}

	close_one(todo, $row) {
		$row.addClass("is-closing");
		closeTodo(todo.name)
			.then(() => {
				frappe.show_alert({
					message: __("Closed: {0}", [frappe.ellipsis(todo.title || todo.name, 60)]),
					indicator: "green",
				});
				// The server's count is the one that counts: it sees ToDos closed
				// elsewhere in the same breath. Re-reading is how this learns.
				return this.refresh();
			})
			.catch(() => $row.removeClass("is-closing"));
	}
}
