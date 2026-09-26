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
 * Picking an app opens its first module. The sidebar's top menu then lists that
 * app's modules -- each a Workspace Sidebar -- in place of Desktop, Workspaces
 * and Website, which the rail now carries: Home is Desktop, the apps replace
 * Workspaces, and Website is at the foot. Its header reads module over app.
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

	// The server's rail, less what this user cannot open.
	const apps = frappe.boot.navigation_apps
		.map((app) => ({ ...app, sidebars: app.sidebars.filter((s) => openable(s.sidebar)) }))
		.filter((app) => app.sidebars.length);

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

	frappe.provide("commons.navigation_rail");

	commons.navigation_rail.open_sidebar = function (title) {
		const route = frappe.utils.get_route_for_icon({ link_type: "Workspace Sidebar", label: title });
		if (frappe.app.sidebar.sidebar_title !== title) frappe.app.sidebar.setup(title);
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
		return `<button type="button" class="commons-rail__item ${extra_class}" data-name="${frappe.utils.escape_html(name)}"
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
							button({ name: app.key, label: app.title, mark: app_mark(app), extra_class: "commons-rail__app" })
						)
						.join("")}
				</div>
			</div>
			<div class="commons-rail__bottom">
				${TOOLS.map((tool) =>
					button({ name: tool.name, label: tool.label, mark: frappe.utils.icon(tool.icon, "md"), extra_class: "hidden" })
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
				commons.navigation_rail.open_sidebar(app.sidebars[0].sidebar);
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
				const shown = $source.length && !$source.hasClass("hidden") && $source.text().trim();
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

	function mark_active_app(sidebar) {
		if (!sidebar.$commons_rail) return;
		const app = app_of(sidebar.sidebar_title);
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
		setup.apply(this, arguments);
		mark_active_app(this);
	};

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

		const current = this.sidebar && this.sidebar.sidebar_title;
		const modules = app
			? app.sidebars.map((entry, index) => ({
					name: `module-${index}`,
					label: entry.label,
					icon: entry.sidebar === current ? "check" : entry.icon || "",
					icon_html: entry.sidebar === current || entry.icon ? undefined : "&nbsp;",
					onClick: () => commons.navigation_rail.open_sidebar(entry.sidebar),
			  }))
			: [];

		this.dropdown_items = modules.length && rest.length ? [...modules, { is_divider: true }, ...rest] : [...modules, ...rest];
	};
})();
