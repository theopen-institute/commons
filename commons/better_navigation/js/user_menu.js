/**
 * Turn the desk sidebar's user badge into a menu, and move the header menu's
 * account and maintenance entries into it.
 *
 * Core's badge does one thing when clicked: `frappe.ui.toolbar.route_to_user()`,
 * straight to your own User record. Its header menu (`SidebarHeader`) holds
 * everything else -- navigation, then Display, Session Defaults, Reload, Help,
 * Logout, Navbar Settings' "settings_dropdown" rows, and Edit Sidebar in
 * developer mode. After this, the header keeps the navigation (Desktop,
 * Workspaces, Website) and the badge opens a menu of the rest:
 *
 *     My Settings, Display, Session Defaults    you: your record, how the desk
 *                                               looks to you, this session's defaults
 *     ---
 *     Edit Sidebar, Navbar Settings' rows       the site: tools that act on the
 *     (System Console...), Reload               system rather than on you
 *     ---
 *     Help                                      reading rather than doing
 *     ---
 *     Logout
 *
 * My Settings is the badge's old click. Navbar Settings rows always land in the
 * second section, so adding one never scatters the order.
 *
 * Moved by wrapping `add_navbar_items`, the same seam `website_button.js` uses:
 * the constructor calls it after building `dropdown_items` and before
 * `setup_app_switcher` renders them, so the header menu is built from the
 * trimmed list. That runs every time the sidebar switches workspace (Help's
 * route-specific links are computed then), so the badge's menu is refilled in
 * place rather than rebuilt -- `frappe.ui.menu` re-renders from its array on
 * every show.
 *
 * The commons SPA's sidebar is built to the same split; see
 * `frontend/src/components/AppSidebar.vue`.
 */
(function patch_user_menu() {
	// Opt-in: "Enable User Menu" in Commons Settings. Unticked, nothing here is
	// installed and both menus are core's, from the next reload.
	const features = (frappe.boot && frappe.boot.commons_features) || {};
	if (!features.user_menu) return;

	const Sidebar = frappe.ui && frappe.ui.Sidebar;
	const Header = frappe.ui && frappe.ui.SidebarHeader;
	if (
		!Sidebar ||
		!Header ||
		typeof Sidebar.prototype.make_dom !== "function" ||
		typeof Header.prototype.add_navbar_items !== "function" ||
		typeof frappe.ui.create_menu !== "function"
	) {
		// Core reshaped the sidebar. Leave both menus as core draws them rather
		// than move entries into a menu that may never open.
		return;
	}

	const STAYS_IN_HEADER = ["desktop", "workspaces", "website"];
	const EDGE_GAP = 8;

	const divider = () => ({ is_divider: true });

	function arrange(moved) {
		// Navbar Settings rows are pushed by core as the boot objects themselves,
		// which is what tells them apart from core's own entries.
		const navbar_rows = frappe.boot.navbar_settings.settings_dropdown || [];
		const from_navbar = moved.filter((item) => navbar_rows.includes(item));
		const own = moved.filter((item) => !navbar_rows.includes(item));

		// Session Defaults and Reload have no `name` in core, only a label.
		const take = (match) => {
			const index = own.findIndex(match);
			return index === -1 ? [] : own.splice(index, 1);
		};
		const display = take((item) => item.name === "display");
		const session_defaults = take((item) => item.label === "Session Defaults");
		const edit_sidebar = take((item) => item.name === "edit-sidebar");
		const reload = take((item) => item.label === "Reload");
		const help = take((item) => item.name === "help");
		const logout = take((item) => item.name === "logout");

		const settings = from_navbar
			// Core pushes hidden rows too; Navbar Settings' Hidden should hide them.
			.filter((item) => !item.hidden)
			.map((item) => ({
				...item,
				// A Route row has `route` but the menu only follows `url`, so in the
				// header these rows did nothing when clicked.
				url: item.url || (item.item_type === "Route" ? item.route : undefined),
				// Navbar rows carry no icon, and the menu drops an empty icon slot
				// altogether, which leaves their labels out of line with the rest.
				icon_html: item.icon || item.icon_url ? item.icon_html : item.icon_html || "&nbsp;",
			}));

		const sections = [
			[
				{
					name: "my-settings",
					label: __("My Settings"),
					icon: "user",
					onClick: () => frappe.ui.toolbar.route_to_user(),
				},
				...display,
				...session_defaults,
			],
			// Whatever is left in `own` is something core added after this was
			// written. It goes with the tools, above Reload, until it is placed.
			[...edit_sidebar, ...settings, ...own, ...reload],
			help,
			logout,
		].filter((section) => section.length);

		return sections.flatMap((section, index) => (index ? [divider(), ...section] : section));
	}

	const add_navbar_items = Header.prototype.add_navbar_items;
	Header.prototype.add_navbar_items = function () {
		add_navbar_items.apply(this, arguments);

		const user_menu_items = this.sidebar && this.sidebar.user_menu_items;
		// No badge menu to receive them: leave the header whole.
		if (!Array.isArray(user_menu_items)) return;

		const moved = this.dropdown_items.filter(
			(item) => !item.is_divider && !STAYS_IN_HEADER.includes(item.name)
		);
		this.dropdown_items = this.dropdown_items.filter((item) =>
			STAYS_IN_HEADER.includes(item.name)
		);
		user_menu_items.splice(0, user_menu_items.length, ...arrange(moved));
	};

	// A menu opened from the foot of the screen runs off it: core places a
	// submenu level with the row it hangs from, whatever is below. Lift it.
	function keep_on_screen(menu) {
		const show = menu.show;
		menu.show = function () {
			show.apply(this, arguments);
			const rect = this.template.get(0).getBoundingClientRect();
			const overflow = rect.bottom - (window.innerHeight - EDGE_GAP);
			if (overflow > 0) {
				this.template.css("top", Math.max(EDGE_GAP, rect.top - overflow) + "px");
			}
		};
		nest(menu);
	}

	function nest(menu) {
		// Core closes an open submenu only when the pointer reaches another row
		// that has one of its own, so moving from Help onto Reload left Help's
		// submenu standing. Any other row closes it here. Delegated from the
		// template, which outlives the rows `make` redraws on every show.
		menu.template.on("mouseenter", ".dropdown-menu-item", function () {
			if (menu.nested_menus.some((nested) => nested.parent.get(0) === this)) return;
			menu.nested_menus.forEach((nested) => nested.hide());
			menu.current_menu = null;
		});

		menu.handle_nested_menu = function () {
			const nested = frappe.ui.menu.prototype.handle_nested_menu.apply(this, arguments);
			keep_on_screen(nested);
			return nested;
		};
	}

	function make_user_menu(sidebar) {
		const $button = sidebar.wrapper.find(".sidebar-user-button");
		if (!$button.length) return;

		// The attribute, not a handler: core's template inlines the route there.
		$button.removeAttr("onclick");

		const menu = frappe.ui.create_menu({
			parent: $button,
			menu_items: sidebar.user_menu_items,
			onShow: () => $button.addClass("active"),
			onHide: () => $button.removeClass("active"),
			onItemClick: () => $button.removeClass("active"),
		});

		// The badge is at the foot of the sidebar and core opens a menu below its
		// trigger, so this one opens above it instead -- as wide as the badge
		// while there is a badge's width to match.
		const show = menu.show;
		menu.show = function () {
			// Before any workspace has built the header there is nothing to list;
			// do what the badge used to do rather than open an empty menu.
			if (!this.menu_items.length) {
				frappe.ui.toolbar.route_to_user();
				return;
			}
			show.apply(this, arguments);
			const anchor = this.parent.get(0).getBoundingClientRect();
			if (sidebar.sidebar_expanded) {
				this.template.css("min-width", anchor.width + "px");
			}
			const top = anchor.top - this.template.outerHeight() - this.gap;
			this.template.css("top", Math.max(EDGE_GAP, top) + "px");
		};
		nest(menu);
	}

	const make_dom = Sidebar.prototype.make_dom;
	Sidebar.prototype.make_dom = function () {
		// Before core's make_dom, so the array exists by the time anything asks.
		this.user_menu_items = [];
		make_dom.apply(this, arguments);
		make_user_menu(this);
	};
})();
