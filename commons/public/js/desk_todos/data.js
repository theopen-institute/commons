// What the panel asks the server, and the two URLs it links out to.
//
// The endpoints are this app's (`commons/commons_core/todos.py`), shared with
// the staff portal's copy of the widget so the two never show different counts.

frappe.provide("commons.desk_todos");

export const SORT_STORAGE_KEY = "commons:desk-todos:sort";

// Labels are read through `__` at call time, not at module load, so a site
// whose translations arrive after this file does still gets them.
export const SORTS = [
	{ value: "due_date", label: () => __("Due date") },
	{ value: "urgency", label: () => __("Urgency") },
	{ value: "doctype", label: () => __("Document type") },
	{ value: "recent", label: () => __("Recently created") },
];

export function fetchTodos(sort_by) {
	return frappe.xcall("commons.commons_core.todos.get_open_todos", { sort_by });
}

export function closeTodo(name) {
	return frappe.xcall("commons.commons_core.todos.close_todo", { name });
}

/** The form a ToDo points at, or the ToDo itself when it points nowhere. */
export function deskUrl(todo) {
	return todo.reference_type && todo.reference_name
		? frappe.utils.get_form_link(todo.reference_type, todo.reference_name)
		: frappe.utils.get_form_link("ToDo", todo.name);
}

/** The whole open list, which is where "See all" goes. */
export function listUrl() {
	return frappe.utils.generate_route({
		type: "doctype",
		name: "ToDo",
		doc_view: "List",
		route_options: { status: "Open" },
	});
}
