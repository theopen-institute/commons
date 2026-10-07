/**
 * `commons.pseudo_islands.mount_page`: a desk Page drawn by an island, on v16.
 *
 * frappe develop draws a Page of type "Frappe UI" itself, in
 * `frappe/public/js/frappe/views/pageview.js` (`setup_island_page`,
 * `show_island`, `set_island_chrome`, `show_island_error`). v16's Page has no
 * type, so a page script calls this instead:
 *
 *     frappe.pages["commons-banking"].on_page_load = (wrapper) =>
 *         commons.pseudo_islands.mount_page(wrapper, "commons.banking");
 *
 * The methods below are develop's at beeaa33c6b, as functions over a state
 * object rather than methods on the page view, with two additions, each
 * marked:
 *
 * - the page draws a pointer to the same screen in the app's frontend when
 *   Commons Settings has desk islands off, or when the Frappe underneath has
 *   no loader at all;
 * - `onReplaceQuery`, so an island that keeps its view in the query string can
 *   write it back. develop's page host has no such event, and on v17 the
 *   island's filters simply stop reaching the URL.
 *
 * Both states the page draws in place of the island are Frappe 16.50's
 * `frappe.ui.empty_state`, as develop's are.
 *
 * On v17 the page's type becomes "Frappe UI" with this island in its `island`
 * field, its script goes, and so does this file. See
 * `commons/pseudo_islands/README.md`.
 */

// Set on <body> while a Frappe UI page is on screen. `island_page.scss` keys the
// bounded box off this class. The island scrolls its own body, which needs a
// definite height to scroll in.
const ISLAND_PAGE_CLASS = "island-page";

/**
 * @param {HTMLElement} wrapper  the page wrapper `on_page_load` receives
 * @param {string} island        the island's name
 * @param {{ title?: string, fallback?: string }} [options]
 *        `title` is the page's until the island reports its own, and
 *        `fallback` the frontend path the off state points to.
 */
function mount_page(wrapper, island, options = {}) {
	const state = {
		wrapper,
		island,
		title: options.title || wrapper.page_name,
		fallback: options.fallback,
		handle: null,
		// What the island last reported. Desk re-applies both on every visit,
		// because another page owns the head in between.
		island_title: null,
		island_actions: [],
	};

	frappe.ui.make_app_page({ parent: wrapper, title: state.title, single_column: true });
	state.container = $('<div class="island-page-body">').appendTo(
		$(wrapper).find(".page-content")
	);

	// Added: the off state.
	if (!frappe.boot?.commons_features?.pseudo_islands || !frappe.ui.mount_island) {
		show_switched_off(state);
		return;
	}

	$(wrapper).on("show", () => {
		document.body.classList.add(ISLAND_PAGE_CLASS);
		show_island(state);
		set_island_chrome(state);
	});

	$(wrapper).on("hide", () => {
		document.body.classList.remove(ISLAND_PAGE_CLASS);
	});
}

/**
 * Mounts the island on the first visit and updates its props on the rest.
 *
 * The props are the part of the URL below the page. An island reads its own
 * address from them rather than from desk's router, so the same component
 * runs under a host that has no desk.
 */
function show_island(state) {
	const props = {
		route: frappe.get_route().slice(1),
		query: Object.fromEntries(new URLSearchParams(window.location.search)),
	};

	if (state.handle) {
		state.handle.update(props);
		return;
	}

	state.handle = frappe.ui.mount_island(state.island, state.container[0], {
		...props,
		onTitle: (title) => {
			state.island_title = title;
			set_island_chrome(state);
		},
		onActions: (actions) => {
			state.island_actions = actions || [];
			set_island_chrome(state);
		},
		// Added: see the header.
		onReplaceQuery: (query) => replace_query(query),
	});

	state.handle.ready.catch((error) => show_island_error(state, error));
}

/**
 * The page head, from what the island reported.
 *
 * The title is the page's one breadcrumb, as desk's own pages set it
 * (`frappe.views.Page`), and the browser tab's. It goes through the page's
 * own `set_breadcrumbs`, so it lands in this page's head whichever page is on
 * screen. A desk without it -- before Frappe 16.50 -- gets the old
 * `frappe.breadcrumbs.add`, which writes to the current page.
 *
 * An action is `{ label, icon? }` plus either an `onClick` or an `href`. An
 * `href` leads out of desk, so desk opens it in a new tab. A desk menu row is
 * a click handler rather than a link, because `add_dropdown_item` writes its
 * own `href="#"`. Desk's menu rows carry no icon, so the icon goes unread.
 */
function set_island_chrome(state) {
	const label = state.island_title || __(state.title);
	const page = state.wrapper.page;
	if (typeof page.set_breadcrumbs === "function") {
		page.set_breadcrumbs([{ label }]);
	} else {
		frappe.breadcrumbs.add({
			type: "Custom",
			label: label,
			route: frappe.get_route_str(),
		});
	}
	frappe.utils.set_title(label);

	page.clear_menu();
	state.island_actions.forEach((action) => {
		const click = action.href ? () => window.open(action.href, "_blank") : action.onClick;
		page.add_menu_item(action.label, click);
	});
}

/**
 * The island did not load. It is the whole page here, so desk says so where
 * the page would have been. Nearly every cause is a bundle that was never
 * built, and the loader's own message names the asset and the fix, so
 * developer mode shows it as it is.
 */
function show_island_error(state, error) {
	console.error(`could not mount the "${state.island}" island`, error);

	state.container.empty().append(
		frappe.ui.empty_state({
			title: __("This page has not been built"),
			description: frappe.boot.developer_mode
				? error.message
				: __("Its assets are missing. Build the app that ships this page."),
		})
	);
}

// Added: the rest of this file.

/**
 * Desk islands are off on this site: the screen is still in the frontend.
 *
 * The way there is a button rather than `empty_state`'s link, which would open
 * it in a new tab: the frontend is this screen's other home, not a reference.
 */
function show_switched_off(state) {
	const fallback = state.fallback;
	state.container.append(
		frappe.ui.empty_state({
			title: __("This page is switched off"),
			description: __("Desk islands are off in Commons Settings."),
			actions: fallback
				? [
						{
							label: __("Open it in {0}", [fallback]),
							onclick: () => window.location.assign(fallback),
						},
				  ]
				: [],
		})
	);
}

/**
 * Writes the island's view back into the query string, in place: a filter is
 * not somewhere the reader went, so it adds no history entry. A key whose value
 * is `undefined` or `null` is dropped.
 */
function replace_query(query) {
	const params = new URLSearchParams(window.location.search);
	for (const [key, value] of Object.entries(query || {})) {
		if (value === undefined || value === null || value === "") params.delete(key);
		else params.set(key, String(value));
	}
	const search = params.toString();
	const url = window.location.pathname + (search ? `?${search}` : "") + window.location.hash;
	window.history.replaceState(window.history.state, "", url);
}

frappe.provide("commons.pseudo_islands");
commons.pseudo_islands.mount_page = mount_page;
