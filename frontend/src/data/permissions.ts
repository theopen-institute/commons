import { useCall } from 'frappe-ui'

/**
 * One doctype-level permission question, asked of Frappe itself.
 *
 * `frappe.client.has_permission` rather than an endpoint of this app's: the
 * answer is the framework's, with role permissions and this app's gate in
 * `commons.safer_permissions` applied, and there is no reason to own a second
 * way of asking it. An empty `docname` asks about the doctype rather than a
 * document, which is what `frappe.has_permission` does with no doc.
 *
 * Fires as soon as it is created, so a module calling this at its top level
 * asks on import — which is why only lazily loaded page modules may. The
 * sidebar's answers come with the shell instead; see `serverGate` in
 * `data/shell.ts`.
 *
 * A doctype the site does not have is refused rather than answered, and the
 * answer reads as no: `data` stays null and `has_permission` with it.
 */
export function permissionCall(doctype: string, perm: string) {
  return useCall<
    { has_permission: boolean },
    { doctype: string; docname: string; perm_type: string }
  >({
    url: '/api/v2/method/frappe.client.has_permission',
    params: { doctype, docname: '', perm_type: perm },
  })
}
