/**
 * How the server's styling vocabulary reads on screen.
 *
 * Both sections send the style a site set on its Workflow State — and, where a
 * section runs without a workflow, the same names chosen server-side — so the
 * mapping from that vocabulary to a badge or a button belongs in one place.
 * Nothing here decides *which* style anything gets; that answer arrives.
 */

export type BadgeTheme = 'gray' | 'blue' | 'green' | 'amber' | 'red'

/** Frappe's own Workflow State styles. Anything else reads as no emphasis. */
const STYLE_THEMES: Record<string, BadgeTheme> = {
  Primary: 'blue',
  Info: 'blue',
  Success: 'green',
  Warning: 'amber',
  Danger: 'red',
  Inverse: 'gray',
}

export function styleTheme(style?: string | null): BadgeTheme {
  return STYLE_THEMES[style ?? ''] ?? 'gray'
}

/**
 * The same answer, narrowed to what a button can be.
 *
 * Frappe UI's Button takes four themes where its Badge takes five, so a state a
 * site styled as a warning reads as unemphasised on a button. Narrowed here
 * rather than by each caller, so the two never disagree about which four.
 */
export type ButtonTheme = 'gray' | 'blue' | 'green' | 'red'

export function buttonTheme(style?: string | null): ButtonTheme {
  const theme = styleTheme(style)
  return theme === 'amber' ? 'gray' : theme
}

/**
 * The icon that goes with a theme rather than with a named outcome.
 *
 * Keyed this way on purpose: a site whose workflow calls its approval something
 * this app has never heard of still gets a tick, because the site styled that
 * state as a success.
 */
const THEME_ICONS: Record<BadgeTheme, string> = {
  green: 'lucide-check',
  red: 'lucide-x',
  blue: 'lucide-arrow-right',
  amber: 'lucide-clock',
  gray: 'lucide-circle-dot',
}

export function themeIcon(theme: BadgeTheme): string {
  return THEME_ICONS[theme]
}
