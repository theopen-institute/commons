"""The icons a self-service record may wear in the sidebar.

Tailwind compiles an icon class only when it can see the literal string in a
file it scans -- the classes are generated per name by frappe-ui's
`iconPackPlugin`, and emitting all two thousand lucide icons would cost nearly
two megabytes of CSS. An icon that appears nowhere in the scanned source
therefore has no rule at all, and a sidebar row wearing it draws an empty
square rather than a mark. That is what happened to both seeded record types:
their icons were configuration, held here and in the database, and the build
had no way to know about them.

So this module is the one place the names are written down, and
`frontend/tailwind.config.js` scans it for exactly that reason. Being a closed
set also lets `Self Service Record` refuse an icon that would not draw, so an
administrator hears it while saving rather than from a blank sidebar.

Adding one: put the lucide name here, then rebuild the frontend.
"""

# Lucide names, prefixed as the class is written. The set is a nav palette --
# what a record type about a person, their money or their paperwork is likely
# to want -- not the whole of lucide.
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
	"lucide-key",
	"lucide-laptop",
	"lucide-mail",
	"lucide-map-pin",
	"lucide-paperclip",
	"lucide-phone",
	"lucide-plane",
	"lucide-receipt",
	"lucide-shield",
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
