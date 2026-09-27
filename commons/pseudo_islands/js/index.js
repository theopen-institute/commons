/**
 * Desk islands on Frappe v16: the desk half of `commons.pseudo_islands`.
 *
 * Installs frappe develop's `frappe.ui.mount_island` where Commons Settings
 * switches desk islands on, and never over a Frappe that has one of its own,
 * so this is inert on v17 until the module is deleted. The page helper is
 * always there, because a page script calls it either way and it draws the
 * off state itself. See `commons/pseudo_islands/README.md`.
 */

import { install } from "./loader";
import "./island_page";

if (frappe.boot?.commons_features?.pseudo_islands && !frappe.ui?.mount_island) {
	install();
}
