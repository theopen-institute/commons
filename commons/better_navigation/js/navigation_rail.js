/**
 * The navigation rail: a narrow column down the left of the desk's sidebar.
 *
 *     Home                    /desk
 *     ---
 *     one icon per app        the Navigation Apps, then the installed apps
 *     ...
 *     (bottom)
 *     Search, Notifications, To Do, Website
 *
 * A module is a Workspace Sidebar, and an app's modules are always listed
 * alphabetically (the server sorts them). What picking an app does depends on
 * "Show Modules", a per-browser choice under Display, next to the theme:
 *
 *   off  the app opens the module you were last in, or its first module on a
 *        first visit.
 *   on   the sidebar turns into the app's module list -- the header reads the
 *        app's name over its module count, the rows are its modules -- and
 *        nothing else moves until a module is picked. Navigating anywhere
 *        else puts back the sidebar for wherever you land. An app with only
 *        one module skips the list and opens it. The way back to the list from
 *        inside a module is the app's own icon on the rail, whose tooltip says
 *        so; the header and the rows have no room for a back arrow.
 *
 * An app with a frontend of its own, outside the desk (Helpdesk's /helpdesk,
 * Commons' /commons), offers it as "Helpdesk app" at the top of its modules,
 * set apart by a rule and marked with an arrow out, and opens it in the same
 * tab, as the Desktop's tiles open it.
 * It counts toward whether there is a choice to show, but is never where the
 * rail sends you back to; an app with nothing but a frontend opens it.
 *
 * The rows move to say which way you went: a module opened from the list comes
 * in from the right (one level down), the list comes in from the left (one
 * level up), and switching app or module sideways fades. Only what a person
 * clicked here animates; the rebuilds core makes on its own as you navigate
 * just appear, or motion would stop meaning anything.
 *
 * Once inside, the sidebar's top menu lists the app's modules, in place of
 * Desktop, Workspaces and Website, which the rail now carries: Home is Desktop,
 * the apps replace Workspaces, and Website is at the foot. The header reads
 * module over app.
 *
 * Which apps, and which modules each holds, is the server's answer
 * (`commons.better_navigation.navigation_apps`), handed over on the boot. What
 * is left to the browser is the one thing the boot already knows better: which
 * sidebars this user can open. `frappe.boot.workspace_sidebar_item` holds only
 * sidebars with at least one row they may see, so a module missing from it is
 * dropped, and an app left with none is not drawn.
 *
 * Opening a module is two steps: `frappe.app.sidebar.setup(title)`, then its
 * first link. Core keeps the sidebar it is showing whenever that sidebar links
 * to the page being opened (rule 1 of `Sidebar.resolve_sidebar`), and a
 * sidebar's first link is by definition in it, so the route change does not
 * send us somewhere else.
 *
 * Search, Notifications and To Do are not rebuilt here: each rail button clicks
 * the sidebar row that already does the job, and those rows are hidden while
 * the rail is on. A row core or `desk_todos` never un-hid -- search switched
 * off in Desk Settings, notifications for a guest -- leaves its button hidden
 * too, so the rail offers exactly what the sidebar would have.
 *
 * Opt-in: "Enable Navigation Rail" in Commons Settings. Off, nothing here is
 * installed. Below the desk's mobile width the rail is not drawn; the sidebar
 * is a drawer there and keeps its own rows.
 */
(function patch_navigation_rail() {
	const features = (frappe.boot && frappe.boot.commons_features) || {};
	if (!features.navigation_rail || !Array.isArray(frappe.boot.navigation_apps)) return;

	const Sidebar = frappe.ui && frappe.ui.Sidebar;
	const Header = frappe.ui && frappe.ui.SidebarHeader;
	if (
		!Sidebar ||
		!Header ||
		["make_dom", "setup", "choose_app_name"].some(
			(m) => typeof Sidebar.prototype[m] !== "function"
		) ||
		typeof Header.prototype.add_navbar_items !== "function"
	) {
		return;
	}

	// The header's navigation entries, which the rail replaces.
	const REPLACED_IN_HEADER = ["desktop", "workspaces", "website"];

	const openable = (title) =>
		Boolean(frappe.boot.workspace_sidebar_item[(title || "").toLowerCase()]);

	// The server's rail, less what this user cannot open. An app with a frontend
	// of its own stays even when none of its sidebars are left: the frontend is
	// somewhere to go too.
	const apps = frappe.boot.navigation_apps
		.map((app) => ({ ...app, sidebars: app.sidebars.filter((s) => openable(s.sidebar)) }))
		.filter((app) => app.sidebars.length || app.frontend);

	// What an app offers: its own frontend if it has one, first and apart, then
	// its modules in the server's alphabetical order. The frontend leaves the
	// desk, so it stands outside the modules' flow rather than sorting in among
	// them, marked as a way out.
	function choices(app) {
		const modules = app.sidebars.map((entry) => ({ ...entry, kind: "sidebar" }));
		if (!app.frontend) return modules;
		return [
			{
				kind: "frontend",
				label: app.frontend.label,
				url: app.frontend.url,
				icon: "external-link",
			},
			...modules,
		];
	}

	// A frontend is somewhere else, not a panel of the desk: the same tab, the
	// way the Desktop's own tiles open one.
	function open_frontend(url) {
		window.location.href = url;
	}

	const open_choice = (choice, motion) =>
		choice.kind === "frontend"
			? open_frontend(choice.url)
			: commons.navigation_rail.open_sidebar(choice.sidebar, motion);

	// The app a sidebar is in. Core also draws sidebars it makes up on the spot,
	// one per module that has no Workspace Sidebar of its own (Commons Settings'
	// page is one); no app lists those, so they are placed under their module's
	// installed app instead -- the rail and the header can still say where you
	// are, though the top menu does not offer them.
	const app_of = (sidebar_title) => {
		const listed = apps.find((app) => app.sidebars.some((s) => s.sidebar === sidebar_title));
		if (listed) return listed;
		const config = frappe.boot.workspace_sidebar_item[(sidebar_title || "").toLowerCase()];
		const module = config && config.module;
		const app_name = module && frappe.boot.module_app[frappe.scrub(module)];
		return app_name ? apps.find((app) => app.key === `app:${app_name}`) : undefined;
	};

	// An app's choices as the sidebar's top menu lists them, the current one ticked.
	// A divider follows the frontend, when there are modules after it.
	function module_items(app, current) {
		const items = choices(app).map((entry, index) => {
			const ticked = entry.kind === "sidebar" && entry.sidebar === current;
			return {
				name: `module-${index}`,
				label: entry.label,
				icon: ticked ? "check" : entry.icon || "",
				icon_html: ticked || entry.icon ? undefined : "&nbsp;",
				onClick: () => open_choice(entry, "fade"),
			};
		});
		if (app.frontend && app.sidebars.length) items.splice(1, 0, { is_divider: true });
		return items;
	}

	// Plays one of the row transitions on the sidebar's rows (see the file
	// docstring for which is which). Entry only: core empties and redraws the
	// rows in one step, so there is nothing left of the old ones to move out.
	const MOTIONS = ["forward", "back", "fade"];
	function animate_rows(sidebar, motion) {
		if (!MOTIONS.includes(motion)) return;
		const $rows = sidebar.$items_container;
		$rows.removeClass(MOTIONS.map((m) => `commons-enter-${m}`).join(" "));
		// Read a layout property so the class removed above takes effect first,
		// and the same transition twice in a row still plays.
		void $rows.get(0).offsetWidth;
		$rows.addClass(`commons-enter-${motion}`);
		$rows.one("animationend", () => $rows.removeClass(`commons-enter-${motion}`));
	}

	// Per browser, like the theme: a convenience, so storage that throws or comes
	// back empty only costs the choice or the memory, never the page.
	const LAST_KEY = "commons_rail_last_module";
	const SHOW_MODULES_KEY = "commons_rail_show_modules";

	const storage = {
		get(key, fallback) {
			try {
				const value = localStorage.getItem(key);
				return value === null ? fallback : JSON.parse(value);
			} catch (e) {
				return fallback;
			}
		},
		set(key, value) {
			try {
				localStorage.setItem(key, JSON.stringify(value));
			} catch (e) {
				// Quota or private browsing.
			}
		},
	};

	const show_modules = () => storage.get(SHOW_MODULES_KEY, false) === true;

	// The module you were last in, per app. Only modules an app lists: the
	// made-up module sidebars are placed under an app for orientation, but are
	// not somewhere to send anyone back to.
	function remember_last(sidebar_title) {
		const app = apps.find((a) => a.sidebars.some((s) => s.sidebar === sidebar_title));
		if (!app) return;
		storage.set(LAST_KEY, { ...storage.get(LAST_KEY, {}), [app.key]: sidebar_title });
	}

	// Only ever a desk module: a frontend leaves the desk, so it is never the
	// place an app sends you back to.
	function landing(app) {
		if (!app.sidebars.length) return null;
		const last = storage.get(LAST_KEY, {})[app.key];
		return app.sidebars.some((s) => s.sidebar === last) ? last : app.sidebars[0].sidebar;
	}

	frappe.provide("commons.navigation_rail");

	// Where opening a module goes: its first link, as core's Desktop works it
	// out. Core gives up when that first link is a Workspace this user cannot
	// see (a private or since-deleted one: My Workspaces, or a site-made
	// sidebar's Home), and then the module would open without going anywhere --
	// so the rest of its links are tried, the way its own rows would open them.
	function route_for(title) {
		const route = frappe.utils.get_route_for_icon({
			link_type: "Workspace Sidebar",
			label: title,
		});
		if (route) return route;

		const config = frappe.boot.workspace_sidebar_item[(title || "").toLowerCase()];
		const Row = frappe.ui.sidebar_item && frappe.ui.sidebar_item.TypeLink;
		if (!config || !Row) return;
		for (const item of config.items) {
			if (item.type !== "Link") continue;
			// Core's row always has an answer for a Workspace, falling back to a
			// private address that leads nowhere; only a workspace this user has
			// counts.
			if (
				item.link_type === "Workspace" &&
				!item.route &&
				!frappe.workspaces[frappe.router.slug(item.link_to)]
			) {
				continue;
			}
			try {
				const path = Row.prototype.get_path.call({
					item,
					transform_filters: Row.prototype.transform_filters,
				});
				if (path) return path;
			} catch (e) {
				// One unreadable row is no reason not to try the next.
			}
		}
	}

	commons.navigation_rail.open_sidebar = function (title, motion) {
		const route = route_for(title);
		const sidebar = frappe.app.sidebar;
		// Rebuilt when it is a different module, and also when the module list is
		// up: the list never changes `sidebar_title`, so a module that matches it
		// would otherwise leave the list on screen with nothing having happened.
		if (sidebar.sidebar_title !== title || sidebar.commons_module_list) {
			sidebar.setup(title);
			animate_rows(sidebar, motion);
		}
		if (!route) return;
		if (/^https?:\/\//.test(route)) {
			window.open(route, "_blank");
		} else {
			frappe.set_route(route);
		}
	};

	// ---------------------------------------------------------------------------------
	// The rail
	// ---------------------------------------------------------------------------------

	function app_mark(app) {
		if (app.logo) return `<img src="${encodeURI(app.logo)}" alt="">`;
		if (app.icon) return frappe.utils.icon(app.icon, "md");
		// No mark of its own: the letter tile the desk draws for such an icon.
		return frappe.utils.desktop_icon(app.title, "gray", "sm");
	}

	function button({ name, label, mark, extra_class = "" }) {
		return `<button type="button" class="commons-rail__item ${extra_class}" data-name="${frappe.utils.escape_html(
			name
		)}"
			title="${frappe.utils.escape_html(label)}" aria-label="${frappe.utils.escape_html(label)}">
			<span class="commons-rail__mark">${mark}</span>
			<span class="commons-rail__badge hidden" aria-hidden="true"></span>
		</button>`;
	}

	// The sidebar row each foot button stands in for, and how to press it.
	const TOOLS = [
		{
			name: "search",
			label: __("Search"),
			icon: "search",
			row: "#navbar-modal-search",
		},
		{
			name: "notifications",
			label: __("Notifications"),
			icon: "bell",
			row: ".sidebar-notification",
			badge: ".sidebar-notification-count",
		},
		{
			name: "todo",
			label: __("To Do"),
			icon: "list-todo",
			row: ".commons-todo-sidebar-item",
			badge: ".commons-todo-badge",
		},
	];

	function make_rail(sidebar) {
		const $rail = $(`<nav class="commons-rail" aria-label="${__("Apps")}">
			<div class="commons-rail__top">
				<div class="commons-rail__home">
					${button({ name: "home", label: __("Home"), mark: frappe.utils.icon("home", "md") })}
				</div>
				<div class="commons-rail__apps">
					${apps
						.map((app) =>
							button({
								name: app.key,
								label: app.title,
								mark: app_mark(app),
								extra_class: "commons-rail__app",
							})
						)
						.join("")}
				</div>
			</div>
			<div class="commons-rail__bottom">
				${TOOLS.map((tool) =>
					button({
						name: tool.name,
						label: tool.label,
						mark: frappe.utils.icon(tool.icon, "md"),
						extra_class: "hidden",
					})
				).join("")}
				${button({ name: "website", label: __("Website"), mark: frappe.utils.icon("web", "md") })}
			</div>
		</nav>`).insertBefore(
			// Core's sidebar template renders to more than one top-level node, and
			// jQuery would put a copy of the rail before each of them.
			sidebar.wrapper.filter(".body-sidebar-container").first()
		);

		$rail.on("click", ".commons-rail__item", function (event) {
			const name = $(this).attr("data-name");
			const app = apps.find((a) => a.key === name);
			const tool = TOOLS.find((t) => t.name === name);

			if (app) {
				// A list of one is not a choice: an app with a single module opens
				// it either way. An app with only a frontend opens that.
				if (show_modules() && choices(app).length > 1) {
					show_module_list(sidebar, app, "back");
				} else if (app.sidebars.length) {
					commons.navigation_rail.open_sidebar(landing(app), "fade");
				} else {
					open_frontend(app.frontend.url);
				}
			} else if (tool) {
				// Notifications closes itself on any click outside its own row, and
				// this button is outside it: keep the click from getting that far.
				event.stopPropagation();
				sidebar.wrapper.find(tool.row).first().trigger("click");
			} else if (name === "home") {
				frappe.set_route("desk");
			} else if (name === "website") {
				const target =
					(commons.website_button && commons.website_button.target()) ||
					window.location.origin;
				window.open(target);
			}
		});

		sidebar.$commons_rail = $rail;
		$("body").addClass("commons-rail-on");
		mirror_tools(sidebar);
		title_apps(sidebar);
	}

	// An app's tooltip says what clicking it does when that is not simply "go
	// there": with "Show Modules" on it shows the app's modules, which is also
	// the way back to them from inside one.
	function title_apps(sidebar) {
		if (!sidebar.$commons_rail) return;
		for (const app of apps) {
			const label =
				show_modules() && choices(app).length > 1
					? __("{0} — show modules", [app.title])
					: app.title;
			sidebar.$commons_rail
				.find(`.commons-rail__app[data-name="${app.key}"]`)
				.attr({ title: label, "aria-label": label });
		}
	}

	// Each foot button follows its row: drawn only once the row is (core and
	// `desk_todos` un-hide their rows when the feature is available), and
	// carrying the row's count. The rows are built after the rail, and redrawn,
	// so they are watched rather than read once.
	function mirror_tools(sidebar) {
		const sync = () => {
			for (const tool of TOOLS) {
				const $row = sidebar.wrapper.find(tool.row).first();
				const $item = sidebar.$commons_rail.find(`[data-name="${tool.name}"]`);
				$item.toggleClass("hidden", !$row.length || $row.closest(".hidden").length > 0);

				if (!tool.badge) continue;
				const $source = $row.find(tool.badge);
				const $badge = $item.find(".commons-rail__badge");
				const shown =
					$source.length && !$source.hasClass("hidden") && $source.text().trim();
				$badge.text(shown ? $source.text().trim() : "").toggleClass("hidden", !shown);
			}
		};
		sync();
		new MutationObserver(frappe.utils.debounce(sync, 50)).observe(sidebar.wrapper.get(0), {
			subtree: true,
			childList: true,
			attributes: true,
			attributeFilter: ["class"],
			characterData: true,
		});
	}

	// ---------------------------------------------------------------------------------
	// The module list ("Show Modules" on)
	// ---------------------------------------------------------------------------------

	// Draws an app's modules into the sidebar in place of its rows, and the app
	// into its header. Core's own sidebar state is left alone -- `sidebar_title`
	// is still the module the page belongs to -- so leaving the list is just
	// rebuilding what core already thinks it is showing.
	function show_module_list(sidebar, app, motion) {
		sidebar.commons_module_list = { app, route: frappe.get_route_str() };

		const $header = sidebar.wrapper.find(".sidebar-header");
		$header.find(".header-title").text(app.title);
		$header.find(".header-subtitle").text(__("{0} modules", [choices(app).length]));
		$header.find(".header-logo").html(app_mark(app));

		// The header's menu belongs to the sidebar core thinks it is showing, which
		// is not this list, and the list already is the choice that menu offers.
		// So while the list is up the header is a label: no chevron, and its click
		// stopped before core's menu sees it. Capture phase, because core's handler
		// is on this same element. Rebuilding the real sidebar replaces the header,
		// and with it all of this.
		$header.addClass("commons-module-list-header").find(".drop-icon").addClass("hidden");
		$header.get(0).addEventListener(
			"click",
			(event) => {
				if (!sidebar.commons_module_list) return;
				event.stopImmediatePropagation();
				event.preventDefault();
			},
			true
		);

		sidebar.$items_container.empty();
		const list = choices(app);
		for (const [index, entry] of list.entries()) {
			// The frontend, first and apart: a rule under it, before the modules.
			if (index === 1 && list[0].kind === "frontend") {
				sidebar.$items_container.append(
					'<div class="commons-module-divider" role="separator"></div>'
				);
			}
			sidebar.add_item(sidebar.$items_container, {
				type: "Button",
				// A row with no link is only drawn when it is `standard`, as core's
				// own Search and Notification rows are.
				standard: true,
				label: entry.label,
				icon: entry.icon || "",
				// `TypeButton` replaces the row's classes with these, so the class
				// every sidebar row is styled by has to be named again.
				class: "sidebar-item-container commons-module-row",
				onClick: () => open_choice(entry, "forward"),
			});
		}
		// The module the page is in, marked the way core marks the current row.
		sidebar.$items_container
			.find(".commons-module-row")
			.filter((_, row) => $(row).attr("data-id") === label_of(app, sidebar.sidebar_title))
			.find(".standard-sidebar-item")
			.addClass("active-sidebar");

		mark_active_app(sidebar, app);
		animate_rows(sidebar, motion);
	}

	const label_of = (app, sidebar_title) => {
		const entry = app.sidebars.find((s) => s.sidebar === sidebar_title);
		return entry && entry.label;
	};

	function leave_module_list(sidebar) {
		if (!sidebar.commons_module_list) return;
		sidebar.commons_module_list = null;
		if (sidebar.sidebar_title) sidebar.setup(sidebar.sidebar_title);
	}

	function mark_active_app(sidebar, shown) {
		if (!sidebar.$commons_rail) return;
		const app = shown || app_of(sidebar.sidebar_title);
		sidebar.$commons_rail.find(".commons-rail__app").each(function () {
			$(this).toggleClass("active", Boolean(app) && $(this).attr("data-name") === app.key);
		});
	}

	// ---------------------------------------------------------------------------------
	// The sidebar: its header, and where the rail goes
	// ---------------------------------------------------------------------------------

	const make_dom = Sidebar.prototype.make_dom;
	Sidebar.prototype.make_dom = function () {
		make_dom.apply(this, arguments);
		try {
			make_rail(this);
		} catch (e) {
			// Never take the sidebar down with the rail.
			console.error("commons: could not draw the navigation rail", e);
		}
	};

	const setup = Sidebar.prototype.setup;
	Sidebar.prototype.setup = function () {
		// Any rebuild is the real sidebar again.
		this.commons_module_list = null;
		setup.apply(this, arguments);
		mark_active_app(this);
		remember_last(this.sidebar_title);
	};

	// Core re-resolves the sidebar on every route change, but rebuilds only when
	// the answer differs from `sidebar_title` -- which the module list never
	// touched. So once the route has moved on from where the list was opened,
	// the list is put away here and the sidebar for the new page drawn.
	if (typeof Sidebar.prototype.set_workspace_sidebar === "function") {
		const set_workspace_sidebar = Sidebar.prototype.set_workspace_sidebar;
		Sidebar.prototype.set_workspace_sidebar = function () {
			set_workspace_sidebar.apply(this, arguments);
			const list = this.commons_module_list;
			if (list && frappe.get_route_str() !== list.route) leave_module_list(this);
		};
	}

	// "Show Modules" beside the theme under Display, ticked while on. The same
	// item object is re-rendered each time the submenu opens, so updating its
	// icon is enough to show the new state.
	if (typeof Header.prototype.get_display_siblings === "function") {
		const get_display_siblings = Header.prototype.get_display_siblings;
		Header.prototype.get_display_siblings = function () {
			const items = get_display_siblings.apply(this, arguments);
			const item = {
				name: "show-modules",
				label: __("Show Modules"),
				onClick: () => {
					const on = !show_modules();
					storage.set(SHOW_MODULES_KEY, on);
					tick(on);
					const sidebar = frappe.app.sidebar;
					title_apps(sidebar);
					if (sidebar.commons_module_list) leave_module_list(sidebar);
					frappe.show_alert({
						message: on
							? __("Picking an app now shows its modules")
							: __("Picking an app now opens your last module"),
						indicator: "blue",
					});
				},
			};
			const tick = (on) => {
				item.icon = on ? "check" : "";
				item.icon_html = on ? undefined : "&nbsp;";
			};
			tick(show_modules());
			return [...items, item];
		};
	}

	// Module over app: the header's subtitle is the app the module belongs to.
	const choose_app_name = Sidebar.prototype.choose_app_name;
	Sidebar.prototype.choose_app_name = function () {
		choose_app_name.apply(this, arguments);
		const app = app_of(this.sidebar_title);
		if (app) this.header_subtitle = app.title;
	};

	// The top menu lists the current app's modules, where Desktop, Workspaces
	// and Website were. Outermost of the three `add_navbar_items` wrappers (it is
	// imported last), so the user menu has already taken what it takes.
	const add_navbar_items = Header.prototype.add_navbar_items;
	Header.prototype.add_navbar_items = function () {
		add_navbar_items.apply(this, arguments);

		const app = app_of(this.sidebar && this.sidebar.sidebar_title);
		const rest = this.dropdown_items.filter((item) => !REPLACED_IN_HEADER.includes(item.name));
		// A divider the removed entries used to sit above has nothing over it now.
		while (rest.length && rest[0].is_divider) rest.shift();

		const modules = app ? module_items(app, this.sidebar && this.sidebar.sidebar_title) : [];

		this.dropdown_items =
			modules.length && rest.length
				? [...modules, { is_divider: true }, ...rest]
				: [...modules, ...rest];
	};
})();
