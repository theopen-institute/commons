// Everything this app adds to the desk's scripts, in one entry: `app_include_js`
// names this file. Each import below draws itself only where its Commons Settings
// switch or its data says so. Two things are not here: the Email Template
// designer, a bundle of its own (`email_designer.bundle.js`) loaded when it is
// opened, and the Permission Manager's gate checkbox (`permission_manager_gate.js`),
// which `page_js` loads on that page alone.
import "./unencoded_at_in_routes";
// Before anything that adds to the user menu: see the file.
import "./user_menu_rows";
// Bikram Sambat dates beside Gregorian ones; see `commons/sambat/README.md`.
import "../../sambat/js/date_control";
import "../../sambat/js/table_cells";
import "./desk_todos";
import "./derived_docfields";
import "./email_extensions";
import "./email_mjml";
import "./email_composer";
import "./print_templates";
import "./hide_cancelled";
import "./hide_internal_accounts";
// Desk islands, until Frappe v17 ships them. Kept together so the whole of it
// can be deleted as one folder; see `commons/pseudo_islands/README.md`.
import "../../pseudo_islands/js/index";
