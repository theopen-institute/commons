import "./unencoded_at_in_routes";
// Before anything that adds to the user menu: see the file.
import "./user_menu_rows";
// Better Navigation keeps its browser halves beside its server halves. Only entry
// files have to be under public/ -- esbuild globs there for `*.bundle.js` --
// and an entry may import from anywhere in the app.
import "../../better_navigation/js/navigation_rail";
import "../../better_navigation/js/user_menu";
import "../../better_navigation/js/arrange";
import "./bikram_sambat/date_control";
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
