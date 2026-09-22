// Keeps "@" literal in the desk address bar, so a document named after an email
// address reads as /desk/member/samana@theopen.institute rather than
// /desk/member/samana%40theopen.institute.
//
// The encoding is not required. RFC 3986 lists "@" in `pchar`, the set a path
// segment is built from, alongside ":" and the sub-delims -- it is reserved only
// in the *authority* part, where it separates userinfo from host. Frappe's own
// server-side builder already knows this: `frappe.utils.data.quoted` passes
// safe=b"~@#$&()*!+=:;,.?/'", so a link out of an email notification arrives
// with the "@" intact. Only the client router escapes it, and a desk-side
// navigation then rewrites the address bar into the escaped form.
//
// One seam, deliberately. `make_url` is the whole desk's URL builder --
// router.js captures every in-desk click and re-derives the address through it,
// so patching it alone covers clicks, awesomebar jumps and `frappe.set_route`
// calls alike. Its four callers in core (router.js `set_route`, awesome_bar.js,
// and two in search.js) all consume the result as a URL; none stores, parses or
// compares it. `frappe.utils.get_form_link` and the inline builders in
// list_view.js and formatters.js are left alone: they only affect the value
// behind "Copy link address", since clicking any of their anchors still lands
// on an address built here.
//
// We do not reimplement the function, only undo the one escape on the way out:
// `encodeURIComponent` emits %40 for "@" and for nothing else, so the
// substitution is its exact inverse and cannot touch a name that literally
// contains the three characters "%40" -- that encodes to %2540. Everything else
// stays escaped, which matters most for a name containing "/", which the router
// would otherwise read as a segment boundary.
//
// The round trip holds at both ends. `get_sub_path` decodes each segment with
// `decodeURIComponent`, which leaves a literal "@" alone; and "@" is not in the
// WHATWG path percent-encode set, so `location.pathname` reports it unescaped
// and `push_state`'s `window.location.pathname !== path` check still matches.
// That check is the one load-bearing assumption here -- were it to fail, every
// navigation would push a duplicate history entry and break the back button.
//
// If core reshapes this area the feature-detect below quietly disables us, and
// the worst case is today's behaviour.
(() => {
	if (!frappe.router || typeof frappe.router.make_url !== "function") return;

	const make_url = frappe.router.make_url;
	frappe.router.make_url = function (params) {
		return make_url.call(this, params).replace(/%40/g, "@");
	};
})();
