// Hide cancelled documents (docstatus 2) from every list-type view, as a
// setting of this browser rather than of the user -- kept in localStorage
// beside core's `container_fullwidth`, and toggled from the same Display menu.
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
	const Header = frappe.ui && frappe.ui.SidebarHeader;
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

	// Display menu: beside Toggle Theme and Toggle Full Width. The menu redraws
	// from its items on every show, so the label is kept current by changing it.
	if (Header && typeof Header.prototype.get_display_siblings === "function") {
		const label = () =>
			is_on() ? __("Show Cancelled Documents") : __("Hide Cancelled Documents");

		const get_display_siblings = Header.prototype.get_display_siblings;
		Header.prototype.get_display_siblings = function () {
			const items = get_display_siblings.apply(this, arguments);
			const item = {
				name: "toggle-cancelled",
				label: label(),
				icon: "eye-off",
				onClick: () => {
					set_on(!is_on());
					item.label = label();
					if (cur_list instanceof ListView) cur_list.refresh();
				},
			};
			return [...items, item];
		};
	}
})();
