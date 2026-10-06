// Drawn by the `commons.attendance` island. On Frappe v17 this Page becomes type
// "Frappe UI" with `commons.attendance` in its island field, and this file is deleted.
// See `commons/pseudo_islands/README.md`.
frappe.pages["commons-attendance"].on_page_load = (wrapper) =>
	commons.pseudo_islands.mount_page(wrapper, "commons.attendance", {
		title: __("Attendance"),
		fallback: "/commons/attendance",
	});
