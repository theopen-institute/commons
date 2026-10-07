# Pseudo Islands

Desk islands on Frappe v16. An island is a Vue screen from this app's frontend, built on its own
and mounted into a desk page inside a shadow root. frappe develop ships islands (PR #43050,
merged 2026-09-24); v16 does not. This module adds what v16 lacks, copied from develop at
**`beeaa33c6b`**, so this app's islands are already written the way v17 hosts them. Everything
in this folder is deleted on v17.

It is switched on per site by **Commons Settings → Core Overrides → Enable Desk Islands**
(`enable_pseudo_islands`, off by default). Off, nothing is installed on the desk, the boot carries
no island list, and the pages point to the same screens under `/commons`.

## What is where

The shims, all in this folder:

| File | What it is | Changed from develop |
| --- | --- | --- |
| `vendor/framework-ui/island/`, `vite/`, `patches/` | develop's `ui/island/`, `ui/vite/index.js`, `ui/vite/island/` (without the framework page-island build) and the reka-ui patch | Nothing. `package.json` is trimmed to these exports, and its `frappe-ui` peer floor is beta.63, not rc.1 |
| `registry.py` | develop's `frappe/utils/island.py` | `get_island_assets` refuses while the setting is off |
| `boot.py` | develop's `bootinfo.ui_islands`, from `frappe.sessions` | Gated by the setting, and yields to a Frappe that already sends the list |
| `js/loader.js` | develop's `frappe/public/js/frappe/ui/island/loader.js` | Imports the host loop by path; publishes from `install()` |
| `js/index.js` | Installs the loader | Only when the setting is on and `frappe.ui.mount_island` does not exist |
| `js/island_page.js` | develop's Frappe UI page host, from `pageview.js` | See below |
| `scss/island_page.scss` | develop's `frappe/public/scss/desk/island_page.scss` | Nothing |

`js/island_page.js` differs from develop's page host in three ways: it draws a pointer to
`/commons/...` when the setting is off; its error state draws its own markup, written when v16
had no `frappe.ui.empty_state` (Frappe 16.50 has one); and it passes `onReplaceQuery`, so a screen that keeps its view in the
query string can write it back (develop's host has no such event).

Outside this folder, each shim is a line or two that names it:

- `hooks.py`: `extend_bootinfo` → `boot.py`, and `override_whitelisted_methods` sends
  `frappe.utils.island.get_island_assets`, which is develop's URL, to `registry.py`
- `public/js/commons.bundle.js` and `public/scss/commons.bundle.scss`: one import each
- `commons_core/settings.py` and Commons Settings: `enable_pseudo_islands`
- `safer_permissions/test_permission_gate.py`: `NOT_REPORTS`, the override above
- `.pre-commit-config.yaml`: `vendor/` is excluded, so the copies stay byte-identical to develop
- `frontend/package.json`: `@framework/ui` links to `vendor/framework-ui`
- the three page scripts, `banking/page/commons_banking/commons_banking.js`,
  `document_capture/page/commons_capture/commons_capture.js` and
  `attendance_register/page/commons_attendance/commons_attendance.js`

What stays on v17, because it is how develop expects an app to ship islands:

- `frontend/build-islands.mjs`: `buildIslands`, with entries `commons.banking`,
  `commons.capture` and `commons.attendance`
- `frontend/src/islands/`: the entries, the shared `pageIsland` frame (provider, scroll box,
  CSRF token) and `contract.ts` (`title` / `actions`)
- `frontend/src/screens/`: the screens, hosted both by the SPA's pages and by the desk
- `frontend/src/types/framework-ui.d.ts`: develop's island package is plain JS
- the Pages' JSON, all Standard: `commons-banking` (module Banking) and `commons-capture` (module
  Document Capture), with roles System Manager, Accounts Manager and Accounts User; and
  `commons-attendance` (module Attendance Register), with roles System Manager, Academics User
  and Instructor. A site whose markers hold another role (a "Faculty", say) adds it to the page
  with Role Permission for Page and Report; the register itself still refuses anybody without
  write on Student Attendance

## Building

`yarn build` in the app root builds the SPA, then the islands (`yarn build:islands` in
`frontend/`). The islands land in `sites/assets/commons/dist/island/` and register themselves in
`assets.json`. `bench watch` does not rebuild them on v16; while working on one, run
`yarn dev:islands` in `frontend/` next to it, and the desk re-mounts the island in place on
each rebuild.

`yarn install` in `frontend/` applies develop's reka-ui patch, which lets a popover open over a
dialog inside a shadow root. The patch was made against reka-ui 2.10.1. It applies cleanly to
2.10.4, and patch-package warns about the version on every install.

## On Frappe v17

1. Delete this folder.
2. In `frontend/package.json`, set `"@framework/ui": "link:../../frappe/ui"`, then run
   `yarn install`. Check that frappe's `ui/patches/` still has a reka-ui patch for the installed
   version.
3. In `hooks.py`, remove the `extend_bootinfo` line and the `get_island_assets` override. Remove
   `NOT_REPORTS` from `test_permission_gate.py`, and the import lines from `commons.bundle.js` and
   `commons.bundle.scss`.
4. In each of the three Pages, set **Type** to "Frappe UI" and **Island** to `commons.banking`,
   `commons.capture` or `commons.attendance`, export them, and delete their `.js` files.
5. Remove `enable_pseudo_islands` from Commons Settings and `settings.py`, and remove
   `Pseudo Islands` from `modules.txt`. `drop_stale_module_defs` removes its Module Def.
6. Check whether develop's page host has gained a way for an island to write its query string.
   Until it does, the banking and attendance islands' filters still work but stop reaching the URL
   on the desk.
   `onReplaceQuery` is this module's own event.

Until step 1, every piece here stands aside for v17's own: the loader installs only where
`frappe.ui.mount_island` is missing, and the boot list is added only where Frappe has not sent one.
