// The navigation rail: apps down the left of the desk, where Frappe's Dock lists the open app's
// modules.
//
// Built on the Dock rather than beside it. Frappe 16.50 draws a column left of the sidebar (the
// Dock) holding the modules of whichever app owns the sidebar on screen, and a header menu over
// the sidebar. This keeps the column and everything Frappe does with it -- pinned or floating,
// hidden where a page hides it, the user menu at its foot -- and changes only what is in it:
//
//   - the column lists the apps `commons.better_navigation.navigation_apps` resolves (the
//     Navigation Apps, then every installed app for the modules those leave unclaimed), the one
//     you are in lit, and its mark at the top is the site's, leading to the Apps screen;
//   - picking an app shows its module list in the sidebar (below), which is also the way back
//     to it from inside one of its modules: pick the app again. Its tooltip is just its name;
//   - the header menu over the sidebar lists the open app's modules, under the Categories and
//     Spacers its Navigation App sets, in place of Frappe's switcher rows;
//   - the header names the module over the app it is in, since the rail's lit tile is an app
//     and Frappe's header names only the module;
//   - Search and Notifications sit at the foot of the rail, over the user's avatar, rather than
//     at the top of the sidebar. They are Frappe's own: the rail's buttons carry the classes
//     Frappe opens search from (`navbar-modal-search-mobile`, a delegated click) and puts the
//     unread count into (`notification-count`, every one on the page), and the bell toggles
//     Frappe's notifications panel. With Desk To Do on, its tile joins them, opening the To Do
//     panel the same way (`public/js/desk_todos/`). Both panels open beside the rail, over the
//     sidebar, rather than beside the sidebar;
//   - the user menu's Manage Dock, which arranges a Dock nothing draws while the rail is on, gives
//     way to Manage Rail, and a click on the module list's header opens Manage Modules for that
//     app (both `js/arrange.js`). They arrange what the rail does draw, and it is redrawn in
//     place when they save (`commons.navigation_rail.apply`).
//
// The module list. The sidebar's rows become the app's modules -- its frontend first, set apart,
// then the modules under their Categories and Spacers -- and its header is the app: its mark,
// its name, and how many modules it has. Nothing
// else moves: the page stays where it was until a module is picked, and navigating anywhere
// else puts back the sidebar for wherever you land. Frappe's own state is left alone, so
// leaving the list is only rebuilding the sidebar Frappe already thinks it is showing. An app
// with one module, or only a frontend, has no choice to show and opens it.
//
// The rows move to say which way you went: a module opened from the list comes in from the right
// (one level down), the list comes in from the left (one level up), and switching app or module
// sideways -- from the header menu, or an app of one module -- fades. Only what a person clicked
// here animates; the rebuilds Frappe makes on its own as you navigate just appear, or motion
// would stop meaning anything.
//
// Which app a module is in is written into the boot by `js/boot_arrangement.js`: each module's
// rail app into `module_sidebars[shell].app`, and an `app_data` entry for each rail app Frappe
// does not know, so Frappe's own header names the right app and logo -- again whenever Frappe
// replaces either.
//
// Off unless Commons Settings' "Enable Navigation Rail" is ticked, and off too if Frappe has moved
// what this hangs on: then the desk is simply Frappe's. Every change to Frappe's classes goes
// through `patch`, so if Frappe changes something this reads and a change throws, the rail
// switches itself off for the rest of the page and Frappe's own method runs instead (`give_up`).
// `test_frappe_seams.py` checks every name this hangs on is still in Frappe's source.
(function () {
	const features = (frappe.boot && frappe.boot.commons_features) || {};
	// Kept as one array for the life of the page: an editor's save refills it in place.
	const rail_apps = frappe.boot && frappe.boot.navigation_apps;
	if (!features.navigation_rail || !Array.isArray(rail_apps) || !rail_apps.length) return;

	const Sidebar = frappe.ui && frappe.ui.Sidebar;
	const Dock = frappe.ui && frappe.ui.Dock;
	const Header = frappe.ui && frappe.ui.SidebarHeader;
	if (
		!Sidebar ||
		!Dock ||
		!Header ||
		[
			"dock_enabled",
			"open_module",
			"setup",
			"set_workspace_sidebar",
			"add_item",
			"empty",
		].some((m) => typeof Sidebar.prototype[m] !== "function") ||
		["make", "render_entries", "render_logo", "name_tile", "close"].some(
			(m) => typeof Dock.prototype[m] !== "function"
		) ||
		typeof Header.prototype.menu_items !== "function" ||
		typeof Sidebar.prototype.refresh_header !== "function" ||
		!(window.commons && commons.user_menu && commons.user_menu.add) ||
		!(commons.boot_arrangement && commons.boot_arrangement.place)
	) {
		return;
	}

	$("body").addClass("commons-rail-on");
	commons.boot_arrangement.place(rail_apps);

	// Set once a change has thrown: from then on every patched method is Frappe's own.
	let broken = false;

	// Replace `proto[name]` with `impl`, which is handed a function calling Frappe's original with
	// the same arguments. If `impl` throws, the rail gives up and the original answers -- once:
	// not again if `impl` had already called it.
	function patch(proto, name, impl) {
		const original = proto[name];
		proto[name] = function (...args) {
			let called = false;
			let result;
			const call_original = () => {
				called = true;
				return (result = original.apply(this, args));
			};
			if (broken) return call_original();
			try {
				return impl.call(this, call_original, args);
			} catch (e) {
				give_up(e);
				return called ? result : original.apply(this, args);
			}
		};
	}

	// Off for the rest of the page: Frappe's placement back, the rail's tools gone, and the sidebar
	// and Dock drawn again, now by Frappe alone.
	function give_up(error) {
		if (broken) return;
		broken = true;
		console.error(
			"commons: the navigation rail met a change in Frappe and has switched itself off",
			error
		);
		$("body").removeClass("commons-rail-on");
		$(".commons-rail-tools").remove();
		commons.boot_arrangement.release();
		setTimeout(() => {
			try {
				const sidebar = frappe.app && frappe.app.sidebar;
				if (!sidebar) return;
				sidebar.commons_module_list = null;
				if (sidebar.sidebar_header) clear_list_header(sidebar.sidebar_header);
				if (sidebar.current_module) sidebar.setup(sidebar.current_module);
				if (sidebar.dock) {
					sidebar.dock.rendered = null;
					sidebar.refresh_dock();
				}
			} catch (e) {
				console.error("commons: could not redraw Frappe's sidebar", e);
			}
		});
	}

	// The rail app holding a shell, by the placement the server wrote into the boot.
	function rail_app_of(shell) {
		const sidebar = shell && frappe.boot.module_sidebars[shell];
		const app_name = sidebar && sidebar.app;
		return (app_name && rail_apps.find((app) => app.app_name === app_name)) || null;
	}

	// A rail app's modules this user can open, in its order.
	function modules_of(app) {
		return (app.modules || []).filter((entry) => frappe.boot.module_sidebars[entry.shell]);
	}

	// What an app's module list offers: its frontend, then its modules.
	function choice_count(app) {
		return modules_of(app).length + (app.frontend ? 1 : 0);
	}

	// Picking an app shows its module list, unless there is only one thing in it to pick.
	function open_app(sidebar, app) {
		if (choice_count(app) > 1) {
			show_module_list(sidebar, app);
			return;
		}
		const [only] = modules_of(app);
		if (only) {
			open_module(sidebar, only.shell, "fade");
		} else if (app.frontend) {
			window.location.href = app.frontend.url;
		}
	}

	// `open_module` builds the module's sidebar before it routes, so the rows are there to move.
	function open_module(sidebar, shell, motion) {
		leave_module_list(sidebar);
		sidebar.open_module(shell);
		animate_rows(sidebar, motion);
	}

	const MOTIONS = ["forward", "back", "fade"];

	function animate_rows(sidebar, motion) {
		if (!MOTIONS.includes(motion)) return;
		const $rows = sidebar.$items_container;
		if (!$rows || !$rows.length) return;
		$rows.removeClass(MOTIONS.map((m) => `commons-enter-${m}`).join(" "));
		// Read a layout property so the class removed above takes effect first, and the same
		// transition twice in a row still plays.
		void $rows.get(0).offsetWidth;
		$rows.addClass(`commons-enter-${motion}`);
		$rows.one("animationend", () => $rows.removeClass(`commons-enter-${motion}`));
	}

	// The list is drawn into the sidebar Frappe has built for the page, and remembers the route
	// it was opened on: once the route moves on, the list is put away.
	function show_module_list(sidebar, app) {
		// Beside a pinned rail a collapsed sidebar is hidden altogether, so it is opened, as
		// Frappe opens it for a Dock entry.
		if (!sidebar.sidebar_expanded && typeof sidebar.open === "function") sidebar.open();
		sidebar.commons_module_list = { app, route: frappe.get_route_str() };
		draw_module_rows(sidebar, app);
		draw_list_header(sidebar);
		refresh_rail(sidebar);
		animate_rows(sidebar, "back");
	}

	function leave_module_list(sidebar) {
		if (!sidebar.commons_module_list) return;
		sidebar.commons_module_list = null;
		if (sidebar.current_module) sidebar.setup(sidebar.current_module);
		refresh_rail(sidebar);
	}

	function refresh_rail(sidebar) {
		if (!sidebar.dock) return;
		sidebar.dock.rendered = null;
		sidebar.dock.render_entries();
	}

	function draw_module_rows(sidebar, app) {
		sidebar.empty();
		const $container = sidebar.$items_container;
		const add_row = (item) =>
			sidebar.add_item($container, {
				type: "Button",
				// A row with no link is only drawn when it is `standard`, as Frappe's own Search
				// and Notification rows are.
				standard: true,
				// `TypeButton` replaces the row's classes with these, so the class every
				// sidebar row is styled by is named again.
				class: "sidebar-item-container commons-module-row",
				...item,
			});

		if (app.frontend) {
			add_row({
				label: app.frontend.label,
				icon: "external-link",
				onClick: () => (window.location.href = app.frontend.url),
			});
			sidebar.add_item($container, { type: "Spacer", label: "" });
		}

		modules_of(app).forEach((entry, index) => {
			if (entry.category) {
				$(`<div class="sidebar-item-container commons-module-category">
					<div class="standard-sidebar-item">
						<div class="item-anchor section-break">
							<span class="sidebar-item-label"></span>
						</div>
					</div>
				</div>`)
					.find(".sidebar-item-label")
					.text(__(entry.category))
					.end()
					.appendTo($container);
			} else if (entry.space_before && index > 0) {
				sidebar.add_item($container, { type: "Spacer", label: "" });
			}
			add_row({
				label: __(entry.label),
				icon: entry.icon || frappe.get_module_icon(entry.shell) || "folder",
				onClick: () => open_module(sidebar, entry.shell, "forward"),
			});
			// The module the page is in, lit the way Frappe lights the current row.
			if (entry.shell === sidebar.current_module) {
				$container
					.find(".commons-module-row")
					.last()
					.find(".standard-sidebar-item")
					.addClass("active-sidebar");
			}
		});
	}

	// The header shows the app over its list: its mark, its name, and its module count under the
	// name in Frappe's own subtitle style. Its menu belongs to the module Frappe thinks it is
	// showing, which is not this list, so while the list is up a click on the header never reaches
	// it. For someone who may arrange the rail, the click opens Manage Modules for this app
	// instead -- the list's own editor, from the list itself. For everyone else the header is a
	// label. No chevron either way: it opens no menu.
	function draw_list_header(sidebar) {
		const header = sidebar.sidebar_header;
		const list = sidebar.commons_module_list;
		if (!header || !list) return;
		header.$header_title.text(list.app.title);
		header.$header_logo.html(app_mark(list.app));
		const count = modules_of(list.app).length;
		set_subtitle(header, count === 1 ? __("1 module") : __("{0} modules", [count]));
		const manageable = can_manage();
		header.wrapper
			.addClass("commons-module-list-header")
			.toggleClass("commons-module-list-header--manageable", manageable)
			.attr("title", manageable ? __("Manage {0} Modules", [__(list.app.title)]) : null);
		header.$drop_icon && header.$drop_icon.addClass("hidden");
		if (!header.commons_list_guard) {
			// Capture phase, so it runs before the menu's own listener on this element.
			header.wrapper.get(0).addEventListener(
				"click",
				(event) => {
					const shown = sidebar.commons_module_list;
					if (!shown || broken) return;
					event.stopImmediatePropagation();
					event.preventDefault();
					if (can_manage()) commons.navigation_rail.manage_modules(shown.app.key);
				},
				true
			);
			header.commons_list_guard = true;
		}
	}

	function app_mark(app) {
		if (app.logo) {
			return frappe.utils.app_logo({ app_title: app.title, app_logo_url: app.logo }).icon;
		}
		if (app.icon) return frappe.utils.icon(app.icon, "md");
		return frappe.utils.desktop_icon(app.title, "gray", "md");
	}

	// Search, Notifications and To Do, at the foot of the rail. Built once, with the Dock.
	patch(Dock.prototype, "make", function (make_dock) {
		const result = make_dock();
		const $tools = $('<div class="commons-rail-tools"></div>').insertBefore(
			this.$dock.find(".dock-user")
		);
		const tool = (name, label, icon, extra_class, suffix = "") => {
			const $button = $(`<button
				class="dock-item commons-rail-tool ${extra_class}"
				data-tool="${name}"
				aria-label="${frappe.utils.escape_html(label)}"
			>
				<span class="dock-item-icon">${frappe.utils.icon(icon, "md")}</span>
				${suffix}
			</button>`).appendTo($tools);
			this.name_tile($button, label);
			return $button;
		};

		if (frappe.boot.desk_settings && frappe.boot.desk_settings.search_bar) {
			tool("search", __("Search"), "search", "navbar-modal-search-mobile").on("click", () =>
				this.close()
			);
		}
		if (
			frappe.boot.desk_settings &&
			frappe.boot.desk_settings.notifications &&
			frappe.session.user !== "Guest"
		) {
			// `sidebar-notification` is the panel's trigger, so a click on it does not count as a
			// click outside that closes the panel it is opening.
			tool(
				"notifications",
				__("Notifications"),
				"bell",
				"sidebar-notification",
				'<span class="notification-count commons-rail-count hidden" aria-live="polite"></span>'
			).on("click", () => frappe.ui.sidebar_panels.toggle("notifications"));
		}
		const todos = window.commons && commons.desk_todos;
		if (features.desk_todos && todos && todos.may_use && todos.may_use()) {
			tool(
				"todos",
				__("To Do"),
				"list-todo",
				todos.TRIGGER,
				'<span class="commons-todo-badge commons-rail-count hidden" aria-live="polite"></span>'
			).on("click", () => frappe.ui.sidebar_panels.toggle(todos.PANEL));
			todos.show_count(todos.count);
		}
		return result;
	});

	// Whether this user may arrange the rail: the editors in `js/arrange.js` say.
	function can_manage() {
		const editors = window.commons && commons.navigation_rail;
		return !!(editors && editors.can_manage && editors.can_manage());
	}

	// The user menu: Manage Dock out, Manage Rail in, where it was (`public/js/user_menu_rows.js`).
	// Manage Modules opens from the module list's header (`draw_list_header`).
	const manage_rail = {
		name: "commons-manage-rail",
		label: __("Manage Rail"),
		icon: "monitor",
		condition: can_manage,
		onclick: () => commons.navigation_rail.manage_rail(),
	};
	commons.user_menu.add((groups) =>
		broken
			? groups
			: groups.map((group) =>
					group && Array.isArray(group.options)
						? {
								...group,
								options: group.options.map((row) =>
									row && row.name === "workspace-selector" ? manage_rail : row
								),
						  }
						: group
			  )
	);

	// After an editor saves: the rail, each module's rail app, and the app entries Frappe's header
	// reads, as the server now resolves them -- then everything drawn from them.
	frappe.provide("commons.navigation_rail");
	commons.navigation_rail.apply = function ({ navigation_apps, app_data }) {
		if (broken) return;
		rail_apps.splice(0, rail_apps.length, ...(navigation_apps || []));
		commons.boot_arrangement.adopt(app_data);
		commons.boot_arrangement.place(rail_apps);

		const sidebar = frappe.app && frappe.app.sidebar;
		if (!sidebar) return;
		const list = sidebar.commons_module_list;
		if (list) {
			const app = rail_apps.find((a) => a.key === list.app.key);
			app ? show_module_list(sidebar, app) : leave_module_list(sidebar);
		} else {
			sidebar.refresh_header();
		}
		refresh_rail(sidebar);
	};

	// Every page can switch apps, so the rail is drawn wherever the page lets Frappe draw a Dock,
	// whether or not the app on screen ships one.
	patch(Sidebar.prototype, "dock_enabled", () => true);

	// The site's mark at the top, leading where Frappe's app mark leads: the Apps screen.
	patch(Dock.prototype, "render_logo", function () {
		const logo = frappe.boot.app_logo_url;
		const title = __("Home");
		this.$header_logo.html(
			logo
				? frappe.utils.app_logo({ app_title: title, app_logo_url: logo }).icon
				: frappe.utils.icon("home", "md")
		);
		this.$header_title.text(title);
		this.$header.attr("aria-label", __("All apps"));
		if (!this.header_tooltip) {
			this.header_tooltip = new frappe.ui.Tooltip(this.$header[0], {
				text: __("All apps"),
				side: "right",
				delay: 0,
				offset: 10,
				class: "es-tooltip--plain",
			});
		}
	});

	// Apps instead of the open app's modules. Frappe calls this whenever what it would draw
	// changes, which includes moving to another module, so the lit app follows.
	patch(Dock.prototype, "render_entries", function () {
		this.tooltips.forEach((tip) => tip.destroy());
		this.tooltips = [];
		this.$items.empty();

		const sidebar = this.sidebar;
		const list = sidebar.commons_module_list;
		const current = list ? list.app : rail_app_of(sidebar.current_module);

		rail_apps.forEach((app) => {
			if (!choice_count(app)) return;
			const is_active = app === current;
			const label = app.title;
			const $item = $(`<button
				class="dock-item commons-rail-app ${is_active ? "active" : ""}"
				aria-label="${frappe.utils.escape_html(label)}"
				${is_active ? 'aria-current="page"' : ""}
			>
				<span class="dock-item-icon">${app_mark(app)}</span>
				<span class="dock-item-label">${frappe.utils.escape_html(label)}</span>
			</button>`);
			this.name_tile($item, label);
			$item.on("click", () => {
				this.close();
				open_app(sidebar, app);
			});
			this.$items.append($item);
		});
	});

	// Any rebuild of the sidebar is the real sidebar again.
	patch(Sidebar.prototype, "setup", function (setup) {
		this.commons_module_list = null;
		if (this.sidebar_header) clear_list_header(this.sidebar_header);
		return setup();
	});

	// Frappe re-resolves the sidebar on every route change but rebuilds it only when the answer
	// is a different module, which the list never changed. So once the route has moved on from
	// where the list was opened, the list is put away here.
	patch(Sidebar.prototype, "set_workspace_sidebar", function (set_workspace_sidebar) {
		const result = set_workspace_sidebar();
		const list = this.commons_module_list;
		if (list && frappe.get_route_str() !== list.route) leave_module_list(this);
		return result;
	});

	// Frappe makes the header, and redraws it, as pages settle and modules change, always through
	// here. Over the list it is the app; inside a module, the module over its app.
	patch(Sidebar.prototype, "refresh_header", function (refresh_header) {
		const result = refresh_header();
		if (this.commons_module_list) {
			draw_list_header(this);
		} else if (this.sidebar_header) {
			clear_list_header(this.sidebar_header);
			const app = rail_app_of(this.current_module);
			set_subtitle(this.sidebar_header, app ? app.title : "");
		}
		return result;
	});

	// Back to the header Frappe draws for a module.
	function clear_list_header(header) {
		header.wrapper
			.removeClass("commons-module-list-header commons-module-list-header--manageable")
			.removeAttr("title");
		header.$drop_icon && header.$drop_icon.removeClass("hidden");
	}

	// The line under the header's title, in Frappe's own `.header-subtitle` style. Frappe's header
	// has none of its own, so it is added the first time and dropped when there is nothing to say.
	function set_subtitle(header, text) {
		let $subtitle = header.wrapper.find(".title-container .header-subtitle");
		if (!text) {
			$subtitle.remove();
			return;
		}
		if (!$subtitle.length) {
			$subtitle = $('<div class="header-subtitle"></div>').appendTo(
				header.wrapper.find(".title-container")
			);
		}
		$subtitle.text(text);
	}

	// The header menu's switcher rows become the open app's module list: its frontend first, then
	// its modules under their Categories, a Spacer starting a new group.
	patch(Header.prototype, "menu_items", function (menu_items) {
		const items = menu_items();
		const app = rail_app_of(this.sidebar.current_module);
		if (!app) return items;
		return [
			...module_groups(this.sidebar, app),
			...app_switcher(this, this.sidebar),
			...items.filter((group) => !is_switcher(group)),
		];
	});

	// Frappe's switcher group, known by its rows rather than by where it sits: Modules, Apps, and
	// the way out to the Apps screen (`SidebarHeader.switcher_items`). A group that holds nothing
	// else is the switcher, whatever else Frappe puts in the menu or in what order.
	const SWITCHER_ROWS = new Set(["switch-module", "switch-app", "all-apps"]);
	function is_switcher(group) {
		const rows = (group && Array.isArray(group.options) && group.options) || [];
		return rows.length > 0 && rows.every((row) => row && SWITCHER_ROWS.has(row.name));
	}

	// Where the rail cannot be reached -- below 768px, where the sidebar is a drawer and the
	// rail is not drawn, or a touch screen with the rail floating out of reach -- the header
	// menu is the only way to another app, as Frappe's own switcher is there. So it carries the
	// rail's apps, then the way out to the Apps screen. Read on every open, as the menu's rows are.
	function app_switcher(header, sidebar) {
		const dock = sidebar.dock;
		const reachable =
			!frappe.is_mobile() &&
			!!dock &&
			dock.enabled &&
			(dock.is_pinned || Dock.pointer_can_reveal?.());
		if (reachable) return [];
		const apps = rail_apps
			.filter((app) => choice_count(app))
			.map((app) => ({
				name: `commons-rail-app-${app.key}`,
				label: __(app.title),
				onclick: () => open_app(sidebar, app),
			}));
		return [
			{
				group: "",
				options: [
					{
						name: "commons-switch-app",
						label: __("Apps"),
						icon: "layout-dashboard",
						submenu: [
							{ group: "", options: apps },
							{
								group: "",
								options:
									typeof header.all_apps_item === "function"
										? [header.all_apps_item()]
										: [],
							},
						],
					},
				],
			},
		];
	}

	function module_groups(sidebar, app) {
		const groups = [];
		let group = null;
		const start = (label) => {
			group = { group: label || "", options: [] };
			groups.push(group);
		};

		if (app.frontend) {
			start();
			group.options.push({
				name: "commons-rail-frontend",
				label: app.frontend.label,
				icon: "external-link",
				href: app.frontend.url,
			});
		}

		modules_of(app).forEach((entry, index) => {
			if (entry.category) {
				start(__(entry.category));
			} else if (!group || (entry.space_before && index > 0)) {
				start();
			}
			group.options.push({
				name: `commons-rail-module-${entry.shell}`,
				label: __(entry.label),
				icon: entry.icon || frappe.get_module_icon(entry.shell),
				onclick: () => open_module(sidebar, entry.shell, "fade"),
			});
		});
		return groups;
	}
})();
