// The rail's two editors, in Frappe's own arrangement editor.
//
// `frappe.ui.ArrangementEditor` is the one editor Frappe 16.50 has for "an ordered list of entries
// more than one party can arrange" -- Manage Dock and Edit Sidebar are both built on it. It holds
// the list, the drag, the eye, the preview, the layer switch and the save; a surface supplies what
// its entries are and where they are read from and written to. These are two more surfaces:
//
//   Manage Rail     the apps on the rail, in order; the eye takes one off it (Hide from Rail).
//                   Add makes a new app, which Manage Modules then opens on to fill.
//   Manage Modules  one app's module list: order, Category and Spacer rows, labels, and the
//                   eye, which takes a module off this app's list (an installed app's own module
//                   then goes to Other). Add puts a module, a heading or a gap on it.
//
// Both write Navigation App records, through `commons.better_navigation.arrange`, which says how.
// There is one layer, the site's ("For everyone"): Navigation Apps are site records.
//
// The editor is not in the desk bundle (Frappe loads it on demand, as Manage Dock does), so the
// two classes are defined once it has loaded. Off unless "Enable Navigation Rail" is ticked.
(function () {
	const features = (frappe.boot && frappe.boot.commons_features) || {};
	if (!features.navigation_rail) return;

	frappe.provide("commons.navigation_rail");

	const METHOD = "commons.better_navigation.arrange";
	let editors = null;

	function load() {
		if (editors) return Promise.resolve(editors);
		return frappe.require("arrangement_editor.bundle.js").then(() => {
			if (!frappe.ui.ArrangementEditor) throw new Error("ArrangementEditor is missing");
			editors = define();
			return editors;
		});
	}

	function failed(e) {
		console.error("commons: could not open the editor", e);
		frappe.ui.toast({
			message: __("Could not open the editor. Please refresh the page."),
			type: "error",
		});
	}

	commons.navigation_rail.manage_rail = () =>
		load()
			.then(({ RailEditor }) => new RailEditor())
			.catch(failed);

	commons.navigation_rail.manage_modules = (app_key) =>
		load()
			.then(({ ModulesEditor }) => {
				// The base class builds the dialog in its constructor, so the app it is about is
				// handed over before that runs.
				ModulesEditor.next_key = app_key;
				return new ModulesEditor();
			})
			.catch(failed);

	// Whether this user may write the records both editors save to.
	commons.navigation_rail.can_manage = () =>
		!!frappe.model.can_write && frappe.model.can_write("Navigation App");

	function define() {
		const Base = frappe.ui.ArrangementEditor;

		// An app's mark, as the rail draws it: its logo, else its icon, else a letter tile.
		function app_mark(entry) {
			if (entry.logo) {
				return `<img src="${frappe.utils.escape_html(
					entry.logo
				)}" alt="" class="commons-arrange-logo">`;
			}
			return entry.icon
				? frappe.utils.icon(entry.icon, "md")
				: frappe.utils.desktop_icon(entry.label, "gray", "sm", "Solid");
		}

		class RailEditor extends Base {
			get layers() {
				return {
					site: {
						read: `${METHOD}.get_rail`,
						save: `${METHOD}.save_rail`,
						label: () => __("For everyone"),
						saved: () => __("Rail updated for everyone"),
					},
				};
			}

			// The one layer there is is the site's, so the editor opens on it.
			prepare() {
				this.can_curate_site = true;
				this.next_new = 0;
			}

			title() {
				return __("Manage Rail");
			}

			can_add() {
				return true;
			}

			// A new app is only an entry until Save, which makes it; a cross takes it out before.
			is_own_add(key) {
				return !!this.entries.get(key).new;
			}

			add() {
				if (!this.loaded) return;
				const dialog = new frappe.ui.Dialog({
					title: __("Add Navigation App"),
					fields: [
						{
							fieldname: "title",
							fieldtype: "Data",
							label: __("Title"),
							description: __(
								"What the rail's tooltip and the sidebar header call it."
							),
						},
						{
							fieldname: "icon",
							fieldtype: "Icon",
							label: __("Icon"),
							description: __("A logo can be set on the Navigation App afterwards."),
						},
					],
					primary_action_label: __("Add"),
					primary_action: ({ title, icon }) => {
						title = (title || "").trim();
						if (!title) {
							frappe.msgprint(__("A new app needs a title."));
							return;
						}
						const taken = [...this.entries.values()].some(
							(entry) => entry.label.toLowerCase() === title.toLowerCase()
						);
						if (taken) {
							frappe.msgprint(__("There is already an app called {0}.", [title]));
							return;
						}
						const key = `new:${this.next_new++}`;
						this.entries.set(key, {
							label: title,
							icon: icon || null,
							roles: [],
							new: true,
						});
						this.order.push(key);
						this.render_panes();
						dialog.hide();
					},
				});
				dialog.show();
			}

			copy() {
				return {
					list_head: __("Apps"),
					add_label: __("Add Navigation App"),
					list_sub: __(
						"Drag to reorder. The eye takes an app off the rail. A new app shows on the rail once it has modules."
					),
					reset_title: __("Put every app back on the rail."),
					list_empty: __("There are no apps"),
					preview_head: __("Preview"),
					preview_sub: __("The rail as this arrangement leaves it."),
					preview_empty: __("Nothing on the rail"),
					load_error: __("Could not load the rail. Please try again."),
				};
			}

			async read() {
				const apps = await frappe.xcall(this.layer_config.read);
				this.entries = new Map();
				apps.forEach((app) =>
					this.entries.set(app.key, {
						label: app.title,
						icon: app.icon,
						logo: app.logo,
						roles: app.roles || [],
					})
				);
				this.arrange(
					apps.map((app) => app.key),
					apps.filter((app) => app.hidden).map((app) => app.key)
				);
			}

			entry_icon(entry) {
				return app_mark(entry);
			}

			item_extras(key) {
				const roles = this.entries.get(key).roles;
				return roles.length
					? `<span class="ws-item-chip text-muted" title="${frappe.utils.escape_html(
							roles.join(", ")
					  )}">${__("Some roles")}</span>`
					: "";
			}

			hide_tooltip(key, hidden) {
				return hidden ? __("Put back on the rail") : __("Take off the rail");
			}

			reset() {
				this.hidden = new Set();
				this.render_panes();
			}

			save_args() {
				return {
					items: JSON.stringify(
						this.arranged_rows((key, hidden) => {
							const entry = this.entries.get(key);
							return entry.new
								? { key, hidden, new: true, title: entry.label, icon: entry.icon }
								: { key, hidden };
						})
					),
				};
			}

			// A new app has no modules yet, so nothing on the rail to pick it by: its Manage Modules
			// opens next, once this dialog has closed.
			apply(payload) {
				commons.navigation_rail.apply(payload);
				const [created] = payload.created || [];
				if (created) {
					setTimeout(() => commons.navigation_rail.manage_modules(created), 400);
				}
			}
		}

		class ModulesEditor extends Base {
			get layers() {
				return {
					site: {
						read: `${METHOD}.get_app_modules`,
						save: `${METHOD}.save_app_modules`,
						label: () => __("For everyone"),
						saved: () => __("Modules updated for everyone"),
					},
				};
			}

			prepare() {
				this.app_key = ModulesEditor.next_key;
				// A new app with no modules is not on the rail yet; its title is read with its rows.
				this.app = (frappe.boot.navigation_apps || []).find((a) => a.key === this.app_key);
				this.can_curate_site = true;
				this.next_marker = 0;
			}

			title() {
				// Dialog titles are written as HTML, so a record's title is escaped.
				return this.app
					? __("Manage {0} Modules", [frappe.utils.escape_html(__(this.app.title))])
					: __("Manage Modules");
			}

			copy() {
				return {
					list_head: __("Modules"),
					add_label: __("Add"),
					list_sub: this.is_other
						? __(
								"Drag to reorder. Other holds every module no app claims, so nothing is taken off it here: add a module to another app instead."
						  )
						: this.installed
						? __(
								"Drag to reorder. The eye takes a module off this app's list, and it goes to Other."
						  )
						: __(
								"Drag to reorder. The eye takes a module off this app, back to the app it came from."
						  ),
					reset_title: __("Put every module back on this app's list."),
					list_empty: __("This app has no modules"),
					preview_head: __("Preview"),
					preview_sub: __("The module list as this arrangement leaves it."),
					preview_empty: __("No modules"),
					load_error: __("Could not load the modules. Please try again."),
				};
			}

			async read() {
				const data = await frappe.xcall(this.layer_config.read, { key: this.app_key });
				this.data_title = data.title;
				if (!this.app) {
					this.dialog.set_title(
						__("Manage {0} Modules", [frappe.utils.escape_html(__(data.title))])
					);
				}
				// An installed app's: taking a module off sends it to Other. Other's: it cannot.
				this.installed = !!data.installed_app;
				this.is_other = data.installed_app === "Other";
				this.entries = new Map();
				const order = [];
				const hidden = [];
				data.rows.forEach((row) => {
					const key = this.key_for(row);
					this.entries.set(key, this.entry_for(row));
					order.push(key);
					if (row.hidden) hidden.push(key);
				});
				this.arrange(order, hidden);
			}

			key_for(row) {
				if (row.kind === "module") return `module:${row.module}`;
				return `${row.kind}:${this.next_marker++}`;
			}

			entry_for(row) {
				if (row.kind === "spacer") return { kind: "spacer", label: __("Spacer") };
				if (row.kind === "category") return { kind: "category", label: row.label };
				return {
					kind: "module",
					module: row.module,
					label: row.label,
					own_label: row.own_label || null,
					icon: row.icon,
					several_sidebars: !!row.several_sidebars,
				};
			}

			entry_icon(entry) {
				if (entry.kind !== "module") return "";
				return entry.icon
					? frappe.utils.icon(entry.icon, "md")
					: frappe.utils.desktop_icon(entry.label, "gray", "sm", "Solid");
			}

			item_classes(key) {
				const kind = this.entries.get(key).kind;
				return kind === "module" ? "" : `commons-arrange-${kind}`;
			}

			// Headings and gaps are this list's own: a cross removes one, where a module has the eye.
			is_own_add(key) {
				return this.entries.get(key).kind !== "module";
			}

			// Other has nowhere further to send a module, so its list is ordered and labelled only.
			visibility_button(key) {
				if (this.is_other) return $();
				return super.visibility_button(key);
			}

			hide_tooltip(key, hidden) {
				if (hidden) return __("Put back on this app's list");
				return this.installed
					? __("Take off this app's list (it goes to Other)")
					: __("Take off this app");
			}

			// A pencil on modules and headings, for what the list calls them.
			decorate_item($el, key) {
				const entry = this.entries.get(key);
				if (entry.kind === "spacer") return;
				$(
					`<button class="ws-item-eye commons-arrange-rename" title="${__(
						"Rename"
					)}">${frappe.utils.icon("edit", "sm")}</button>`
				)
					.on("click", () => this.rename(key))
					.appendTo($el);
			}

			rename(key) {
				const entry = this.entries.get(key);
				frappe.prompt(
					{
						fieldname: "label",
						fieldtype: "Data",
						label: entry.kind === "category" ? __("Heading") : __("Label"),
						default: entry.kind === "category" ? entry.label : entry.own_label || "",
						// A module of several sidebars keeps each one's own name on the rail.
						description:
							entry.kind !== "module"
								? ""
								: entry.several_sidebars
								? __(
										"This module has more than one sidebar, so each keeps its own name: a label here is not used."
								  )
								: __("Left blank, the module's own name."),
						reqd: entry.kind === "category",
					},
					({ label }) => {
						label = (label || "").trim();
						if (entry.kind === "category") {
							entry.label = label;
						} else {
							entry.own_label = label || null;
							if (!entry.several_sidebars) entry.label = label || entry.module;
						}
						this.render_panes();
					},
					__("Rename")
				);
			}

			preview_item(key) {
				const entry = this.entries.get(key);
				if (entry.kind === "spacer") return $('<div class="commons-arrange-gap"></div>');
				if (entry.kind === "category") {
					return $('<div class="ws-preview-item commons-arrange-heading"></div>').text(
						entry.label
					);
				}
				return super.preview_item(key);
			}

			can_add() {
				return true;
			}

			add() {
				if (!this.loaded) return;
				const dialog = new frappe.ui.Dialog({
					title: __("Add to {0}", [
						frappe.utils.escape_html(
							__(this.app ? this.app.title : this.data_title || "")
						),
					]),
					fields: [
						{
							fieldname: "kind",
							fieldtype: "Select",
							label: __("Type"),
							options: [
								{ value: "module", label: __("Module") },
								{ value: "category", label: __("Category heading") },
								{ value: "spacer", label: __("Spacer") },
							],
							default: "module",
						},
						{
							fieldname: "module",
							fieldtype: "Link",
							options: "Module Def",
							label: __("Module"),
							depends_on: "eval:doc.kind == 'module'",
						},
						{
							fieldname: "label",
							fieldtype: "Data",
							label: __("Label"),
							depends_on: "eval:doc.kind != 'spacer'",
							description: __("For a module, left blank: its own name."),
						},
					],
					primary_action_label: __("Add"),
					primary_action: (values) => {
						if (this.place(values)) dialog.hide();
					},
				});
				dialog.show();
			}

			// New rows go at the end of the list; a module already on it is put back if it was
			// taken off, and otherwise left where it is. What each type needs is checked here
			// rather than with `mandatory_depends_on`, which can read the type from before it was
			// changed.
			place({ kind, module, label }) {
				label = (label || "").trim();
				if (kind === "module" && !module) {
					frappe.msgprint(__("Pick a module."));
					return false;
				}
				if (kind === "category" && !label) {
					frappe.msgprint(__("A category needs a heading."));
					return false;
				}
				if (kind === "module") {
					const key = `module:${module}`;
					if (this.entries.has(key)) {
						if (this.hidden.has(key)) {
							this.hidden.delete(key);
							this.render_panes();
							return true;
						}
						frappe.show_alert({
							message: __("{0} is already on this list", [module]),
							indicator: "orange",
						});
						return false;
					}
					const sidebar = frappe.utils.sidebar_for_module(module);
					this.entries.set(key, {
						kind,
						module,
						label: label || (sidebar && sidebar.label) || module,
						own_label: label || null,
						icon: sidebar && sidebar.header_icon,
					});
					this.order.push(key);
				} else {
					const key = this.key_for({ kind });
					this.entries.set(key, this.entry_for({ kind, label }));
					this.order.push(key);
				}
				this.render_panes();
				return true;
			}

			reset() {
				this.hidden = new Set();
				this.render_panes();
			}

			save_args() {
				const rows = this.arranged_rows((key, hidden) => {
					const entry = this.entries.get(key);
					return {
						kind: entry.kind,
						module: entry.module || null,
						label: entry.kind === "category" ? entry.label : null,
						own_label: entry.own_label || null,
						hidden,
					};
				});
				return { key: this.app_key, items: JSON.stringify(rows) };
			}

			apply(payload) {
				commons.navigation_rail.apply(payload);
			}
		}

		return { RailEditor, ModulesEditor };
	}
})();
