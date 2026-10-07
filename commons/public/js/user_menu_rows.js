// Rows of this app's own in the desk's user menu (your avatar).
//
// Frappe 16.50 builds the user menu in `Sidebar.create_user_menu`, for both the sidebar's user
// button and the Dock's avatar, as a `frappe.ui.Dropdown` it makes there and does not hand back,
// from a list of rows it writes inline. There is no hook to add a row. So for as long as that one
// call runs, the Dropdown it makes is a subclass that passes its rows through every change
// registered here, in the order they were registered, and the call puts Frappe's Dropdown back
// whatever happens.
//
// A feature registers a change with `commons.user_menu.add(change)`, which says whether the change
// will reach the menu -- so a feature that also takes a row away elsewhere can leave it there when
// it would not. A change takes the menu's groups (`[{group, options}]`) and the sidebar, and
// returns the groups to show; it is called once per menu made, and a row's `condition` is how a
// row follows state. A change that throws is skipped, so one broken feature cannot take the menu
// away.
//
// Nothing is installed until something registers, and nothing at all if Frappe has moved what this
// hangs on: then the menu is simply Frappe's.
frappe.provide("commons.user_menu");

(function () {
	const changes = [];
	let installed = false;

	commons.user_menu.add = function (change) {
		if (typeof change !== "function") return false;
		install();
		if (installed) changes.push(change);
		return installed;
	};

	function install() {
		if (installed) return;
		const Sidebar = frappe.ui && frappe.ui.Sidebar;
		if (
			!Sidebar ||
			!frappe.ui.Dropdown ||
			typeof Sidebar.prototype.create_user_menu !== "function"
		) {
			return;
		}
		installed = true;

		const create_user_menu = Sidebar.prototype.create_user_menu;
		Sidebar.prototype.create_user_menu = function () {
			const sidebar = this;
			const Dropdown = frappe.ui.Dropdown;
			frappe.ui.Dropdown = class extends Dropdown {
				constructor(opts = {}) {
					super(
						Array.isArray(opts.options)
							? { ...opts, options: apply_changes(opts.options, sidebar) }
							: opts
					);
				}
			};
			try {
				return create_user_menu.apply(this, arguments);
			} finally {
				frappe.ui.Dropdown = Dropdown;
			}
		};
	}

	function apply_changes(groups, sidebar) {
		return changes.reduce((current, change) => {
			try {
				const changed = change(current, sidebar);
				return Array.isArray(changed) ? changed : current;
			} catch (e) {
				console.error("commons: a user menu change failed", e);
				return current;
			}
		}, groups);
	}
})();
