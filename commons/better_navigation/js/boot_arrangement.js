// Commons' arrangement of the desk's boot, kept when Frappe replaces it.
//
// The rail and the Apps screen both work by arranging two things in `frappe.boot` that Frappe's
// own desk reads:
//
//   - `module_sidebars[shell].app`, which app a module is in. Frappe's header takes its title and
//     logo from there, and it decides which app is open. The rail writes each module's rail app
//     into it, here, from the rail itself (`commons.boot_arrangement.place`).
//   - `app_data`, the apps Frappe knows. The rail adds an entry for each rail app Frappe has no
//     record of (a Navigation App of its own, Other) and retitles a bound one; the Apps screen
//     setting has already arranged its tiles on the server (`apps_screen.py`).
//
// Frappe replaces both wholesale when a workspace or a sidebar is saved (`workspace.js`,
// `sidebar_manager.js`), with its own answer. So both are watched: whatever Frappe puts there is
// arranged again as it arrives, from wherever in Frappe it comes. A replaced `app_data` takes back
// the Apps screen's tiles, titles and order from the copy the boot arrived with; everything else
// in it is Frappe's new answer.
//
// The rail only places modules once it has checked that it can draw (`place`), and stops if it
// gives up (`release`), putting back what Frappe said.
frappe.provide("commons.boot_arrangement");

(function () {
	const boot = frappe.boot;
	if (!boot) return;
	const features = boot.commons_features || {};

	// What the Apps screen setting decides about an app, and so takes back from a replacement.
	const ARRANGED = ["app_title", "app_logo_url", "on_apps_screen", "sequence_id"];
	const snapshot = (app_data) => app_data.map((entry) => ({ ...entry }));

	// The Apps screen as the server arranged it, while that setting is on.
	let arranged =
		features.apps_screen && Array.isArray(boot.app_data) ? snapshot(boot.app_data) : null;
	// The rail's apps, once the rail asks for its modules to be placed.
	let rail = null;
	// Frappe's own answer for each module entry, so placing again, or giving up, starts from it.
	const origins = new WeakMap();

	function place_modules(module_sidebars) {
		if (!module_sidebars) return;
		const placement = {};
		(rail || []).forEach((app) =>
			(app.sidebars || []).forEach((module) => (placement[module.sidebar] = app.app_name))
		);
		Object.entries(module_sidebars).forEach(([shell, sidebar]) => {
			if (!sidebar || typeof sidebar !== "object") return;
			if (!origins.has(sidebar)) origins.set(sidebar, sidebar.app);
			sidebar.app = placement[shell] || origins.get(sidebar);
		});
	}

	// A rail app Frappe does not know gets an entry of its own, kept off the Apps screen; a bound
	// one gives Frappe's entry its title and logo.
	function add_rail_entries(app_data) {
		if (!rail || !Array.isArray(app_data)) return;
		const known = new Map(app_data.map((entry) => [entry.app_name, entry]));
		rail.forEach((app) => {
			const entry = known.get(app.app_name);
			if (entry) {
				if (app.configured) {
					entry.app_title = app.title;
					if (app.logo) entry.app_logo_url = app.logo;
				}
				return;
			}
			const added = {
				app_name: app.app_name,
				app_title: app.title,
				app_logo_url: app.logo || null,
				app_route: "",
				desk_route: "",
				on_apps_screen: false,
				sequence_id: 100,
				dock: [],
			};
			app_data.push(added);
			known.set(app.app_name, added);
		});
	}

	// Frappe's fresh `app_data`, with the Apps screen's arrangement put back over it: the arranged
	// entries in their order, then whatever Frappe has that the arrangement did not.
	function rearrange(fresh) {
		if (!arranged) return fresh;
		const by_name = new Map(fresh.map((entry) => [entry.app_name, entry]));
		const result = arranged.map((saved) => {
			const entry = by_name.get(saved.app_name);
			if (!entry) return { ...saved };
			by_name.delete(saved.app_name);
			const merged = { ...entry };
			ARRANGED.forEach((field) => (merged[field] = saved[field]));
			if (!(merged.dock || []).length) merged.dock = saved.dock;
			return merged;
		});
		return [...result, ...by_name.values()];
	}

	// Run `settle` on every value assigned to `frappe.boot[key]`, and keep what it returns. Left
	// alone if something else already owns the property.
	function watch(key, settle) {
		const descriptor = Object.getOwnPropertyDescriptor(boot, key);
		if (descriptor && (!descriptor.configurable || descriptor.get || descriptor.set)) return;
		let value = boot[key];
		Object.defineProperty(boot, key, {
			configurable: true,
			enumerable: true,
			get: () => value,
			set: (next) => {
				value = next;
				try {
					value = settle(next);
				} catch (e) {
					console.error(`commons: could not arrange frappe.boot.${key}`, e);
				}
			},
		});
	}

	watch("module_sidebars", (value) => {
		if (rail) place_modules(value);
		return value;
	});
	watch("app_data", (value) => {
		if (!Array.isArray(value)) return value;
		const result = rearrange(value);
		add_rail_entries(result);
		return result;
	});

	Object.assign(commons.boot_arrangement, {
		// Place each module in its rail app, now and whenever Frappe replaces the boot's copy.
		// Called again with the same array after the rail is refilled.
		place(rail_apps) {
			rail = rail_apps;
			place_modules(boot.module_sidebars);
			add_rail_entries(boot.app_data);
		},
		// Back to Frappe's placement, and stop placing.
		release() {
			rail = null;
			Object.values(boot.module_sidebars || {}).forEach((sidebar) => {
				if (sidebar && origins.has(sidebar)) sidebar.app = origins.get(sidebar);
			});
		},
		// An editor's save: the server's freshly arranged `app_data` is the arrangement from now on.
		adopt(app_data) {
			if (!Array.isArray(app_data)) return;
			arranged = features.apps_screen ? snapshot(app_data) : null;
			boot.app_data = app_data;
		},
	});
})();
