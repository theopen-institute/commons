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
// They go in as one more group, just above Logout, through `commons.user_menu`
// (`public/js/user_menu_rows.js`), which says how a row gets into Frappe's user menu.
//
// Off unless Commons Settings' "Enable User Menu" is ticked, and off too if Frappe has moved what
// this hangs on: then both stay where Frappe puts them. They leave the header menu only once a
// user menu has really been built with them in it, so a change in how Frappe builds that menu
// leaves them where Frappe puts them rather than nowhere.
(function () {
	const features = (frappe.boot && frappe.boot.commons_features) || {};
	if (!features.user_menu) return;
	// Open Desk's copy of this does the same, behind its own switch; one of them is enough. The
	// switch here still opens the Commons frontend's user menu.
	const open_desk = (frappe.boot && frappe.boot.opendesk_features) || {};
	if (open_desk.user_menu) return;

	const Header = frappe.ui && frappe.ui.SidebarHeader;
	if (
		!Header ||
		!(window.commons && commons.user_menu && commons.user_menu.add) ||
		typeof Header.prototype.system_items !== "function" ||
		typeof Header.prototype.navbar_items !== "function" ||
		typeof Header.prototype.get_help_siblings !== "function"
	) {
		return;
	}

	// Into the user menu, over Logout -- and then, only once they are there, off the header menu,
	// where that whole block is the Navbar Settings rows and Help.
	let delivered = false;
	const added = commons.user_menu.add((groups, sidebar) => {
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

		const changed = [...groups];
		changed.splice(Math.max(changed.length - 1, 0), 0, help);
		delivered = true;
		return changed;
	});
	if (added) {
		const system_items = Header.prototype.system_items;
		Header.prototype.system_items = function () {
			return delivered ? [] : system_items.apply(this, arguments);
		};
	}
})();
