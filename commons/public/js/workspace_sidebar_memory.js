// Makes the workspace sidebar remember which sidebar you reached a page from,
// so a refresh keeps your context instead of reverting to the doctype's module.
//
// Core already intends this. `resolve_sidebar` consults a remembered choice in
// localStorage["sidebar_item_map"] as its second rule, above the fallback that
// resolves by module. The reader is fine; the writer never produces anything it
// can find:
//
//   - it keys the map on the sidebar *item's label* (`data-id`, set from
//     item.label), while the reader looks up the *route entity*, i.e. the
//     doctype. Unless a label happens to equal a doctype name, no lookup hits.
//   - `setup_reload` resets the in-memory map to {} on every page load, and the
//     next write setItems that near-empty map over the stored one, so anything
//     remembered earlier is lost.
//   - it pushes onto an array the reader indexes at [0], so a hit would return
//     the oldest choice rather than the newest.
//
// So we replace the writer only, and store in the shape the stock reader
// already expects: map[entity] = [sidebar_title]. `resolve_sidebar` is left
// untouched, which keeps the priority order upstream's to change. If core
// reshapes this area the feature-detect below quietly disables us, and a stale
// map is inert — worst case the sidebar falls back to today's behaviour.
(() => {
	const Sidebar = frappe.ui && frappe.ui.Sidebar;
	// Every method we lean on, including the two we only call.
	const required = [
		"set_workspace_sidebar",
		"store_last_show_sidebar_for_item",
		"entity_from_route",
		"get_workspace_sidebars",
	];
	if (!Sidebar || required.some((m) => typeof Sidebar.prototype[m] !== "function")) return;

	const STORE = "sidebar_item_map";

	const read = () => {
		try {
			return JSON.parse(localStorage.getItem(STORE) || "{}");
		} catch (e) {
			return {};
		}
	};

	function remember(sidebar) {
		const title = sidebar.sidebar_title;
		if (!title) return;

		const entity = sidebar.entity_from_route(frappe.get_route() || []);
		if (!entity) return;

		// Record only a sidebar that actually links to this entity. Without this
		// guard, reaching a list by URL or awesomebar would overwrite a genuine
		// choice with whichever sidebar happened to be open at the time.
		if (!sidebar.get_workspace_sidebars(entity).includes(title)) return;

		const map = read();
		if (map[entity] && map[entity][0] === title) return;

		// One element, not a history: the stock reader takes [0] and an
		// unbounded array would grow on every navigation.
		map[entity] = [title];
		try {
			localStorage.setItem(STORE, JSON.stringify(map));
		} catch (e) {
			// Quota or private browsing. The memory is a convenience; losing it
			// costs the user the old behaviour, not the page.
		}
	}

	// Called by core at the end of `setup` and on beforeunload. Both now route
	// through the corrected writer; `item_sidebar_map` is read nowhere else, so
	// dropping it is safe.
	Sidebar.prototype.store_last_show_sidebar_for_item = function () {
		remember(this);
	};

	// beforeunload alone is too weak to rely on (bfcache, mobile, crashes), and
	// `setup` only fires when the sidebar actually *changes* — never when you
	// click a link within the sidebar you are already in, which is exactly the
	// case worth remembering. Wrapping here records after every route change,
	// once resolution has settled `sidebar_title`.
	const set_workspace_sidebar = Sidebar.prototype.set_workspace_sidebar;
	Sidebar.prototype.set_workspace_sidebar = function (router) {
		set_workspace_sidebar.call(this, router);
		remember(this);
	};
})();
