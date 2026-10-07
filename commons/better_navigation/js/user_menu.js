// The site's tools and Help, in the user menu rather than the sidebar's header menu.
//
// Frappe 16.50 ends the menu at the top of the sidebar, which is otherwise about the module on
// screen, with the site's Navbar Settings rows (System Console, and whatever else a site or an
// app's `standard_navbar_items` adds) and Help (the page's own help links, then the site's
// Navbar Settings help rows). Neither is about the module. Both are about you and the site, as is
// everything in the user menu at the foot of the rail (Settings, Reload, Logout), so they move
// there, as one group above Logout: the same rows Frappe builds, from the header's own
// `navbar_items`, and the same Help submenu, read afresh on every open from its
// `get_help_siblings`, so the page's help links still follow the page.
//
// The user menu is built by `Sidebar.create_user_menu` for both the sidebar's user button and the
// Dock's avatar, as a `frappe.ui.Dropdown` it does not hand back. So the Dropdown it makes is
// given one more group, just above Logout, for as long as that call runs.
//
// Off unless Commons Settings' "Enable User Menu" is ticked, and off too if Frappe has moved what
// this hangs on: then both stay where Frappe puts them.
(function () {
	const features = (frappe.boot && frappe.boot.commons_features) || {};
	if (!features.user_menu) return;

	const Sidebar = frappe.ui && frappe.ui.Sidebar;
	const Header = frappe.ui && frappe.ui.SidebarHeader;
	const Dropdown = frappe.ui && frappe.ui.Dropdown;
	if (
		!Sidebar ||
		!Header ||
		!Dropdown ||
		typeof Sidebar.prototype.create_user_menu !== "function" ||
		typeof Header.prototype.system_items !== "function" ||
		typeof Header.prototype.navbar_items !== "function" ||
		typeof Header.prototype.get_help_siblings !== "function"
	) {
		return;
	}

	// Off the header menu: that whole block is the Navbar Settings rows and Help.
	Header.prototype.system_items = function () {
		return [];
	};

	// Into the user menu, over Logout.
	const create_user_menu = Sidebar.prototype.create_user_menu;
	Sidebar.prototype.create_user_menu = function () {
		const sidebar = this;
		// Navbar Settings rows read only the boot, so the prototype builds them as well as a
		// header would; the sidebar's header may not exist yet when the menu is made.
		const site_rows = Header.prototype.navbar_items.call(
			sidebar.sidebar_header || Header.prototype
		);
		const help = {
			group: "",
			options: [
				...site_rows,
				{
					name: "help",
					label: __("Help"),
					icon: "info",
					// A function, so the menu reads it on every open: the page's help links
					// change with every navigation.
					submenu: () =>
						sidebar.sidebar_header ? sidebar.sidebar_header.get_help_siblings() : [],
					condition: () =>
						!!sidebar.sidebar_header &&
						sidebar.sidebar_header
							.get_help_siblings()
							.some((section) => section.options.length),
				},
			],
		};

		// Whatever Dropdown is current is extended, so another change made the same way (the
		// rail's editors, in `js/navigation_rail.js`) still applies.
		const Current = frappe.ui.Dropdown;
		frappe.ui.Dropdown = class extends Current {
			constructor(opts = {}) {
				const options = Array.isArray(opts.options) ? [...opts.options] : opts.options;
				if (Array.isArray(options))
					options.splice(Math.max(options.length - 1, 0), 0, help);
				super({ ...opts, options });
			}
		};
		try {
			return create_user_menu.apply(this, arguments);
		} finally {
			frappe.ui.Dropdown = Current;
		}
	};
})();
