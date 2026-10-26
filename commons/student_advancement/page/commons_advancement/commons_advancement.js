// Drawn by the `commons.advancement` island. On Frappe v17 this Page becomes type
// "Frappe UI" with `commons.advancement` in its island field, and this file is deleted.
// See `commons/pseudo_islands/README.md`.
frappe.pages["commons-advancement"].on_page_load = (wrapper) =>
	commons.pseudo_islands.mount_page(wrapper, "commons.advancement", {
		title: __("Student Advancement"),
		fallback: "/commons/advancement",
	});
