// Draws the gate in the Role Permission Manager, directly under "Only if Creator".
//
// The two belong together: both answer *which rows* a role reaches, unlike the
// grid of rights beside them, which answers what it may do with the rows it has.
//
// Core offers no hook for this placement. A `Permission Type` would put the
// checkbox in the rights grid instead, and can only be registered per doctype
// during an install or migrate. This file is appended after the page's own
// script, so the class is already defined by the time it runs, and the checkbox
// it adds saves itself: the page binds its change handler by delegation and
// reads `data-ptype` off the element, which `add_check` sets from the fieldname.
(() => {
	const engine = frappe.PermissionEngine;
	// Feature-detect rather than assume. If core reshapes this page, the gate
	// should quietly stop being drawn, not throw on every row.
	if (!engine || typeof engine.prototype.setup_if_owner !== "function") return;

	const setup_if_owner = engine.prototype.setup_if_owner;
	engine.prototype.setup_if_owner = function (d, role_cell) {
		setup_if_owner.call(this, d, role_cell);
		this.add_check(
			role_cell,
			d,
			"require_user_permission",
			__("Require User Permission"),
			__("This role sees nothing until a User Permission narrows it")
		)
			.removeClass("col-md-4")
			.css({ "margin-top": "10px" });
	};
})();
