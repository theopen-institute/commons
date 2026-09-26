/**
 * Point the desk sidebar's "Website" button at Website Settings' Website Button
 * Target.
 *
 * Core builds that entry in `SidebarHeader`'s constructor with a hardcoded
 * `window.open(window.location.origin)`, which lands on `/` -- and `/` is
 * resolved by the same `get_home_page` cascade that `frappe.auth` sends a fresh
 * login through. One setting, two jobs. `frappe.boot.website_button_url` is the
 * second setting; see `commons/better_navigation/website_link.py`.
 *
 * Patched by wrapping `add_navbar_items`, which the constructor calls *before*
 * `setup_app_switcher` and `populate_dropdown_menu` render from the same array.
 * Rewriting the item there means both renderings, and the click handler
 * `setup_select_options` binds by `data-name`, all see the new target. There is
 * no lighter seam: the array is a constructor local until that point.
 */
frappe.provide("commons.website_button");

commons.website_button.target = function () {
	const configured = (frappe.boot && frappe.boot.website_button_url) || "";
	// Unset means "the site root", which is what core already did.
	return configured.trim() || window.location.origin;
};

(function patch_sidebar_header() {
	if (!frappe.ui || !frappe.ui.SidebarHeader) {
		// Core moved or renamed the sidebar; leave its button alone rather than
		// half-patch it.
		return;
	}

	const original = frappe.ui.SidebarHeader.prototype.add_navbar_items;

	frappe.ui.SidebarHeader.prototype.add_navbar_items = function () {
		original.apply(this, arguments);

		const website_item = (this.dropdown_items || []).find((item) => item.name === "website");
		if (!website_item) return;

		website_item.onClick = function () {
			window.open(commons.website_button.target());
		};
	};
})();
