// A To Do widget for the desk, beside the notification bell, in both the places
// the desk puts that bell: the workspace sidebar and the desktop navbar.
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

function may_use_todos() {
	return (
		frappe.session.user !== "Guest" &&
		frappe.model &&
		typeof frappe.model.can_read === "function" &&
		frappe.model.can_read("ToDo")
	);
}

/* --------------------------------------------------------------------------
 * Host 1: the workspace sidebar
 * ----------------------------------------------------------------------- */

function mount_in_sidebar(sidebar) {
	const $section = sidebar.$standard_items_sections;
	if (!$section || !$section.length) return;
	if ($section.find(".commons-todo-panel").length) return;

	let panel;
	const $trigger = () => sidebar.wrapper.find(".commons-todo-sidebar-item");

	sidebar.add_item($section, {
		label: __("To Do"),
		icon: "list-todo",
		standard: true,
		type: "Button",
		// TypeButton assigns this to the wrapper's class attribute wholesale,
		// so it is the only hook available on the row.
		class: "commons-todo-sidebar-item",
		suffix: "<span class='commons-todo-badge hidden' aria-live='polite'></span>",
		onClick: () => {
			panel.toggle();
			// The drawer is over the page below 768px, and the row just pressed
			// is inside it. Core closes its own drawer on the same press.
			if (frappe.is_mobile()) sidebar.wrapper.removeClass("expanded");
		},
	});

	panel = new ToDoPanel({
		container: $section,
		placement: "sidebar",
		trigger: $trigger,
		onCount: (count) => {
			const $badge = $trigger().find(".commons-todo-badge");
			if (!$badge.length) return;
			count
				? $badge
						.text(count > 99 ? "99+" : count)
						.attr("aria-label", __("{0} open to-dos", [count]))
						.removeClass("hidden")
				: $badge.removeAttr("aria-label").addClass("hidden");
		},
	});

	sidebar.commons_todos = panel;
}

function patch_sidebar() {
	const Sidebar = frappe.ui && frappe.ui.Sidebar;
	const required = ["add_standard_items", "add_item", "make_sidebar_item"];
	if (!Sidebar || required.some((m) => typeof Sidebar.prototype[m] !== "function")) return;
	if (!frappe.ui.sidebar_item || !frappe.ui.sidebar_item.TypeButton) return;

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

function mount_in_navbar() {
	const $bell = $(".desktop-notifications");
	if (!$bell.length || $(".commons-todo-navbar").length) return;

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

	panel = new ToDoPanel({
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

patch_sidebar();
patch_desktop();
