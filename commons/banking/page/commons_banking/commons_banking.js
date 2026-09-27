// Drawn by the `commons.banking` island. On Frappe v17 this Page becomes type
// "Frappe UI" with `commons.banking` in its island field, and this file is deleted.
// See `commons/pseudo_islands/README.md`.
frappe.pages["commons-banking"].on_page_load = (wrapper) =>
	commons.pseudo_islands.mount_page(wrapper, "commons.banking", {
		title: __("Bank Reconciliation"),
		fallback: "/commons/banking",
	});
