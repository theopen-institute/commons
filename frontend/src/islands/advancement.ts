// The `commons.advancement` island: moving a term's students on, for a desk page.
// Built by `build-islands.mjs`; drawn at /desk/commons-advancement. See `frame.ts`.
import StudentAdvancementScreen from '@/screens/StudentAdvancementScreen.vue'
import { pageIsland } from './frame'

export const mount = pageIsland(StudentAdvancementScreen)
