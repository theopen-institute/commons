// Drawn by the `commons.capture` island. On Frappe v17 this Page becomes type
// "Frappe UI" with `commons.capture` in its island field, and this file is deleted.
// See `commons/pseudo_islands/README.md`.
frappe.pages["commons-capture"].on_page_load = (wrapper) =>
	commons.pseudo_islands.mount_page(wrapper, "commons.capture", {
		title: __("Document Capture"),
		fallback: "/commons/capture",
	});
