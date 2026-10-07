// Hide cancelled documents (docstatus 2) from every list-type view, as a
// setting of this browser rather than of the user -- kept in localStorage, and
// toggled from the user menu (your avatar), after Settings. Frappe 16.50 took
// away the Display menu it used to sit in; display settings are in Settings'
// Appearance tab now, which has no room for an app's own row.
//
// Every list-type view (list, report, kanban, image, the record count, the
// sidebar's group-by counts and the form's prev/next buttons) asks
// `ListView.get_filters_for_args()` for its filters, so the filter is added
// there and nowhere else. It is never put into the filter area, so it is not
// saved with the view's filters, "Clear filters" leaves it, and a filter on
// docstatus -- or on status "Cancelled" -- that you set yourself turns it off.
//
// The one caller that must not see it is `get_search_params`, which writes the
// filters into the page URL: from there a reload would read it back as a real
// filter chip.
//
// A list shows a small eye button beside Filter while the setting is on. It
// shows cancelled rows in that list until the page is reloaded; the list views
// are cached per route, so the choice survives moving away and back.
(() => {
	const KEY = "hide_cancelled_documents";
	const ListView = frappe.views && frappe.views.ListView;
	if (!ListView || typeof ListView.prototype.get_filters_for_args !== "function") return;

	const is_on = () => {
		try {
			return JSON.parse(localStorage.getItem(KEY) || "false") === true;
		} catch (e) {
			return false;
		}
	};

	const set_on = (on) => {
		try {
			localStorage.setItem(KEY, JSON.stringify(on));
		} catch (e) {
			// Storage blocked: the setting simply does not stick.
		}
	};

	const applies = (list) =>
		is_on() &&
		!list.__show_cancelled &&
		// Meta is loaded by the time anything asks for filters.
		frappe.model.is_submittable(list.doctype);

	// You asked about cancelled rows yourself, so you get what you asked for.
	const asks_for_cancelled = (filters, doctype) =>
		filters.some(
			(f) =>
				f[0] === doctype &&
				(f[1] === "docstatus" ||
					(f[1] === "status" && JSON.stringify(f[3] ?? "").includes("Cancelled")))
		);

	const get_filters_for_args = ListView.prototype.get_filters_for_args;
	ListView.prototype.get_filters_for_args = function () {
		const filters = get_filters_for_args.apply(this, arguments);
		if (this.__for_url || !applies(this) || asks_for_cancelled(filters, this.doctype)) {
			return filters;
		}
		return [...filters, [this.doctype, "docstatus", "!=", 2]];
	};

	const get_search_params = ListView.prototype.get_search_params;
	if (typeof get_search_params === "function") {
		ListView.prototype.get_search_params = function () {
			this.__for_url = true;
			try {
				return get_search_params.apply(this, arguments);
			} finally {
				this.__for_url = false;
			}
		};
	}

	// The per-list button, redrawn after every fetch so it follows the setting.
	const after_render = ListView.prototype.after_render;
	ListView.prototype.after_render = function () {
		const result = after_render.apply(this, arguments);
		draw_button(this);
		return result;
	};

	function draw_button(list) {
		const $section = list.$filter_section;
		if (!$section) return;

		const wanted = is_on() && frappe.model.is_submittable(list.doctype);
		if (!wanted) {
			list.$cancelled_button?.remove();
			list.$cancelled_button = null;
			return;
		}

		// Built like the Filter button beside it, in a wrapper of its own so the
		// filter section's flex row does not stretch it to the standard filters'
		// height. While it is hiding rows its icon takes the primary colour, as
		// the Filter button's does while filters are applied.
		if (!list.$cancelled_button) {
			list.$cancelled_button = $(
				`<div class="cancelled-toggle" style="align-self: flex-start; margin: var(--margin-xs)">
					<button class="btn btn-default btn-sm">
						<span class="filter-icon button-icon"></span>
					</button>
				</div>`
			).prependTo($section);
			list.$cancelled_button.find("button").on("click", () => {
				list.__show_cancelled = !list.__show_cancelled;
				list.refresh();
			});
		}

		const hidden = !list.__show_cancelled;
		list.$cancelled_button
			.find(".filter-icon")
			.toggleClass("active", hidden)
			.html(frappe.utils.icon(hidden ? "eye-off" : "eye"));
		list.$cancelled_button
			.find("button")
			.attr(
				"title",
				hidden
					? __(
							"Cancelled documents are hidden (browser setting). Click to show them in this list."
					  )
					: __("Showing cancelled documents in this list. Click to hide them again.")
			);
	}

	// The user menu, after Settings (`commons.user_menu`, in `user_menu_rows.js`).
	// The menu re-reads each row's condition on every open but not its label, so
	// the two states are two rows, of which one shows.
	if (window.commons && commons.user_menu && commons.user_menu.add) {
		const toggle = () => {
			set_on(!is_on());
			if (window.cur_list instanceof ListView) cur_list.refresh();
		};
		const rows = [
			{
				name: "hide-cancelled",
				label: __("Hide Cancelled Documents"),
				icon: "eye-off",
				condition: () => !is_on(),
				onclick: toggle,
			},
			{
				name: "show-cancelled",
				label: __("Show Cancelled Documents"),
				icon: "eye",
				condition: () => is_on(),
				onclick: toggle,
			},
		];
		const add_rows = (options) => {
			let placed = false;
			const result = options.map((entry) => {
				if (placed || !entry || !Array.isArray(entry.options)) return entry;
				const at = entry.options.findIndex((row) => row && row.name === "settings");
				if (at < 0) return entry;
				placed = true;
				const own = [...entry.options];
				own.splice(at + 1, 0, ...rows);
				return { ...entry, options: own };
			});
			// No Settings row to follow: a group of their own, ahead of the rest.
			return placed ? result : [{ group: "", options: rows }, ...result];
		};

		commons.user_menu.add(add_rows);
	}
})();
