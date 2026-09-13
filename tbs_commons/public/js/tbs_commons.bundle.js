// Keep this app's desk icons in the current window.
//
// Frappe builds the href of every `link_type: "External"` desk icon as
// `window.location.origin + link` (desk/page/desktop/desktop.js `get_route`),
// and then stamps `target="_blank"` on any route starting with "http" — which
// that prefix guarantees. So an icon pointing at a route on this same site
// opens a second tab, as Helpdesk's and Frappe HR's do too.
//
// A delegated listener rather than stripping the attribute: the desktop
// re-renders its icons (edit mode, folders, reordering), and anything written
// onto the element is lost on the next render. This has no timing dependency.
(function () {
	const APP_PREFIX = '/tbs_commons'

	function isInternalAppIcon(anchor) {
		if (!anchor) return false
		try {
			const url = new URL(anchor.href, window.location.origin)
			return (
				url.origin === window.location.origin &&
				(url.pathname === APP_PREFIX || url.pathname.startsWith(APP_PREFIX + '/'))
			)
		} catch (e) {
			// A malformed href is not ours to handle; let the browser decide.
			return false
		}
	}

	document.addEventListener(
		'click',
		function (event) {
			// A deliberate new tab stays a new tab: modified and middle clicks
			// are the user asking for one, and are left alone.
			if (event.defaultPrevented || event.button !== 0) return
			if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return

			const anchor = event.target.closest && event.target.closest('a.desktop-icon')
			if (!isInternalAppIcon(anchor)) return

			event.preventDefault()
			window.location.href = anchor.href
		},
		true,
	)
})()
