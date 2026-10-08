// A To Do widget for the desk, beside the notification bell, in the places the
// desk puts that bell: the sidebar's band of standard rows (Search, Notification),
// the navigation rail's foot when Better Navigation's or Open Desk's rail is on,
// and the desktop navbar.
//
// Beside the sidebar it is Frappe's own kind of panel, as Notifications is: a
// `frappe.ui.SidebarPanel` named `commons-todos`, opened through
// `frappe.ui.sidebar_panels` by any element carrying `commons-todo-trigger` --
// the sidebar row here, the rail's tile in `better_navigation/js/navigation_rail.js`.
// Every `.commons-todo-badge` on the page shows the open count.
//
// Written entirely from this app. An earlier version of this widget edited
// `frappe/`'s own sidebar template, stylesheet and bundle, and a bump from
// 16.33.1 to 16.34.0 removed every line of it. Nothing here touches another
// app's files: the button is appended by wrapping one method, the panel builds
// its own markup, and the styling is this app's bundle.
//
// Both hosts are feature-detected. If core moves a seam, the widget quietly
// does not appear, rather than half-appearing or throwing inside core's own
// setup -- `Sidebar.prepare` wraps `add_standard_items` in a try/catch that
// swallows the error and leaves the sidebar half-built.

import { ToDoPanel } from "./panel";

frappe.provide("commons.desk_todos");

const PANEL = "commons-todos";
commons.desk_todos.PANEL = PANEL;
commons.desk_todos.TRIGGER = "commons-todo-trigger";
// The last count, for a badge drawn after it arrived (the rail is built later).
commons.desk_todos.count = 0;

function show_count(count) {
	commons.desk_todos.count = count;
	const $badges = $(".commons-todo-badge");
	count
		? $badges
				.text(count > 99 ? "99+" : count)
				.attr("aria-label", __("{0} open to-dos", [count]))
				.removeClass("hidden")
		: $badges.removeAttr("aria-label").addClass("hidden");
}
commons.desk_todos.show_count = show_count;

function may_use_todos() {
	return (
		frappe.session.user !== "Guest" &&
		frappe.model &&
		typeof frappe.model.can_read === "function" &&
		frappe.model.can_read("ToDo")
	);
}

commons.desk_todos.may_use = may_use_todos;

/* --------------------------------------------------------------------------
 * Host 1: the sidebar's band of standard rows, and the drawer beside it
 * ----------------------------------------------------------------------- */

function mount_in_sidebar(sidebar) {
	const $band = sidebar.$standard_items_band;
	if (!$band || !$band.length) return;
	if (frappe.ui.sidebar_panels.get(PANEL)) return;

	sidebar.add_item($band, {
		label: __("To Do"),
		icon: "list-todo",
		standard: true,
		type: "Button",
		// TypeButton assigns this to the wrapper's class attribute wholesale,
		// so it is the only hook available on the row.
		class: `commons-todo-sidebar-item ${commons.desk_todos.TRIGGER}`,
		suffix: "<span class='commons-todo-badge hidden' aria-live='polite'></span>",
		onClick: () => frappe.ui.sidebar_panels.toggle(PANEL),
	});

	let panel;
	const host = new frappe.ui.SidebarPanel({
		name: PANEL,
		title: __("To Do"),
		trigger_selector: `.${commons.desk_todos.TRIGGER}`,
		on_open: () => panel && panel.refresh(),
	});
	panel = new ToDoPanel({ host, onCount: show_count });
	sidebar.commons_todos = panel;
}

function patch_sidebar() {
	const Sidebar = frappe.ui && frappe.ui.Sidebar;
	const required = ["add_standard_items", "add_item", "make_sidebar_item"];
	if (!Sidebar || required.some((m) => typeof Sidebar.prototype[m] !== "function")) return;
	if (!frappe.ui.sidebar_item || !frappe.ui.sidebar_item.TypeButton) return;
	if (!frappe.ui.SidebarPanel || !frappe.ui.sidebar_panels) return;

	const add_standard_items = Sidebar.prototype.add_standard_items;
	Sidebar.prototype.add_standard_items = function (items) {
		// Core returns immediately when its own items are already up; the guard
		// is read before the call because the call is what sets it.
		const was_setup = this.standard_items_setup;
		add_standard_items.call(this, items);
		if (was_setup || !this.standard_items_setup) return;
		if (!may_use_todos()) return;

		try {
			mount_in_sidebar(this);
		} catch (e) {
			// Never let this take core's sidebar down with it: `prepare` calls
			// `add_standard_items` first and abandons the rest of the sidebar on
			// a throw.
			console.error("commons: could not mount the To Do widget", e);
		}
	};
}

/* --------------------------------------------------------------------------
 * Host 2: the desktop navbar, immediately left of the bell
 * ----------------------------------------------------------------------- */

// The navbar's panel, so a desktop redrawn from scratch -- which removes the old
// icon without telling it -- gets one panel rather than one more.
let navbar_panel = null;

function mount_in_navbar() {
	const $bell = $(".desktop-notifications");
	if (!$bell.length || $(".commons-todo-navbar").length) return;
	if (navbar_panel) navbar_panel.destroy();

	let panel;
	const $host = $(`
		<div class="commons-todo-navbar">
			<button class="btn-reset nav-link text-muted commons-todo-navbar-icon"
				aria-label="${__("To Do")}" title="${__("To Do")}">
				${frappe.utils.icon("list-todo", "md")}
				<span class="commons-todo-badge hidden" aria-live="polite"></span>
			</button>
		</div>
	`).insertBefore($bell);

	panel = navbar_panel = new ToDoPanel({
		container: $host,
		placement: "navbar",
		trigger: () => $host.find(".commons-todo-navbar-icon"),
		onCount: (count) => {
			const $badge = $host.find(".commons-todo-badge");
			count
				? $badge
						.text(count > 99 ? "99+" : count)
						.attr("aria-label", __("{0} open to-dos", [count]))
						.removeClass("hidden")
				: $badge.removeAttr("aria-label").addClass("hidden");
		},
	});

	$host.find(".commons-todo-navbar-icon").on("click", (e) => {
		e.stopPropagation();
		panel.toggle();
	});
}

function patch_desktop() {
	// Core triggers this in `DesktopPage.setup`, which is the only seam the page
	// offers and the reason the navbar half needs no template edit.
	$(document).on("desktop_screen", () => {
		if (!may_use_todos()) return;
		try {
			mount_in_navbar();
		} catch (e) {
			console.error("commons: could not mount the To Do navbar icon", e);
		}
	});
}

/* --------------------------------------------------------------------------
 * Host 3: Open Desk's rail, when that app is installed and its rail is on
 * ----------------------------------------------------------------------- */

// A tile at the rail's foot, beside its bell, opening the same drawer as the
// sidebar's row. Open Desk reads `opendesk.rail.tools` when it draws the rail,
// so this works whichever bundle loads first, and costs nothing where Open
// Desk is not installed. See `opendesk/open_desk/js/rail.js`.
function add_to_open_desk_rail() {
	const rail = frappe.provide("opendesk.rail");
	(rail.tools = rail.tools || []).push({
		name: "commons-todos",
		label: __("To Do"),
		icon: "list-todo",
		class: commons.desk_todos.TRIGGER,
		badge_class: "commons-todo-badge",
		condition: may_use_todos,
		on_click: () => frappe.ui.sidebar_panels.toggle(PANEL),
		on_draw: () => show_count(commons.desk_todos.count),
	});
}

// Opt-in: "Enable Desk To Do" in Commons Settings. Off, neither seam is
// wrapped, and neither rail's To Do tile, which opens the sidebar's drawer,
// is drawn either.
const features = (frappe.boot && frappe.boot.commons_features) || {};
if (features.desk_todos) {
	patch_sidebar();
	patch_desktop();
	add_to_open_desk_rail();
}
