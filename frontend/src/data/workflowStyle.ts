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

/**
 * One outcome the server will accept, and how it reads.
 *
 * All three fields are the server's. `style` is the site's -- a Workflow State's
 * where a workflow is running, and the section's default otherwise -- and
 * `confirm` says whether this outcome deserves a second look before it is
 * written. Inferring that here from the button's own colour meant a site that
 * added an outcome silently got whatever the inference happened to decide.
 */
export interface Decision {
  value: string
  style: string | null
  confirm: boolean
}

export interface DecisionButton {
  decision: string
  label: string
  theme: ButtonTheme
  variant: 'solid' | 'subtle'
  icon: string
  /** Whether to ask again before writing it. The server's answer, not a guess
   *  read off the variant beside it. */
  confirm: boolean
}

/**
 * How one decision button reads.
 *
 * Which outcomes exist, how each is styled and which needs confirming are all
 * the server's. `labels` is the calling section's wording, and only wording: an
 * outcome it does not know keeps the server's name for it, which is what a site
 * that added one would want it called.
 */
export function decisionButton(
  decision: Decision,
  labels: Record<string, string> = {}
): DecisionButton {
  const theme = buttonTheme(decision.style)
  return {
    decision: decision.value,
    label: labels[decision.value] ?? decision.value,
    theme,
    variant: decision.confirm ? 'subtle' : 'solid',
    icon: themeIcon(theme),
    confirm: decision.confirm,
  }
}

/**
 * The buttons for one row: the outcomes the server said this row accepts, in
 * the order the vocabulary offers them, and at most one of them solid.
 *
 * One solid button is frappe-ui's convention: the affirmative outcome -- the one
 * the server did not ask to have confirmed -- is the call to action, and
 * everything else stays subtle so a row reads as one choice rather than a wall
 * of filled buttons.
 */
export function decisionButtons(
  offered: string[] | undefined,
  vocabulary: Decision[],
  labels: Record<string, string> = {}
): DecisionButton[] {
  let solidTaken = false
  return vocabulary
    .filter((decision) => offered?.includes(decision.value))
    .map((decision) => {
      const button = decisionButton(decision, labels)
      if (button.variant !== 'solid') return button
      if (solidTaken) return { ...button, variant: 'subtle' as const }
      solidTaken = true
      return button
    })
}
