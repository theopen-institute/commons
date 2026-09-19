"""The icons this app's sidebar can draw.

Tailwind compiles an icon class only when it can see the literal string in a
file it scans -- the classes are generated per name by frappe-ui's
`iconPackPlugin`, and emitting all two thousand lucide icons would cost nearly
two megabytes of CSS. An icon that appears nowhere in the scanned source
therefore has no rule at all, and a sidebar row wearing it draws an empty
square rather than a mark. That is what happens to a record type a site
configures: its icon is configuration, held in the database, and the build has
no way to know about it.

So this module is the one place the names are written down, and
`frontend/tailwind.config.js` scans it for exactly that reason. Being a closed
set also lets `Self Service Record` refuse an icon that would not draw, so an
administrator hears it while saving rather than from a blank sidebar.

Adding one: put the lucide name here, then rebuild the frontend.

Read by two doctypes now, for one reason. `Self Service Record` holds the icon
of a navigation row; `Commons Workspace` holds the mark beside a workspace in
the switcher, and the override a workspace row may put on a page. All three are
configuration -- stored in the database, sent down by the API, invisible to the
build -- so all three answer to this list. The module stays here rather than
moving somewhere neutral because self-service is what made it necessary, and a
second copy of the palette would be worse than an import across sections.
"""

# Lucide names, prefixed as the class is written. The set is a nav palette --
# what a record type about a person, their money or their paperwork is likely
# to want, plus the marks this app's own pages wear so a workspace can match one
# -- not the whole of lucide.
NAV_ICONS = (
	# The fallback the sidebar applies when a record names no icon at all.
	# Listed so this module stays the full account of what the sidebar can draw.
	"lucide-file-text",
	"lucide-id-card",
	"lucide-landmark",
	"lucide-award",
	"lucide-backpack",
	"lucide-badge-check",
	"lucide-banknote",
	"lucide-book",
	"lucide-briefcase",
	"lucide-building",
	"lucide-calendar",
	"lucide-car",
	"lucide-clipboard-list",
	"lucide-clock",
	"lucide-contact",
	"lucide-credit-card",
	"lucide-folder",
	"lucide-graduation-cap",
	"lucide-handshake",
	"lucide-heart-pulse",
	"lucide-house",
	"lucide-inbox",
	"lucide-key",
	"lucide-laptop",
	"lucide-mail",
	"lucide-map-pin",
	"lucide-megaphone",
	"lucide-palmtree",
	"lucide-paperclip",
	"lucide-phone",
	"lucide-plane",
	"lucide-receipt",
	"lucide-shield",
	"lucide-shopping-cart",
	"lucide-smartphone",
	"lucide-stethoscope",
	"lucide-truck",
	"lucide-user",
	"lucide-users",
	"lucide-wallet",
)

# What the sidebar uses for a record that names no icon. In the frontend too --
# a row renders `row.icon || 'lucide-file-text'` -- because the fallback has to
# survive a record saved before this field existed.
DEFAULT_NAV_ICON = "lucide-file-text"
