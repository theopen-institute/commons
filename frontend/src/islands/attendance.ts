// The `commons.attendance` island: the attendance register, for a desk page.
// Built by `build-islands.mjs`; drawn at /app/commons-attendance. See `frame.ts`.
import AttendanceRegisterScreen from '@/screens/AttendanceRegisterScreen.vue'
import { pageIsland } from './frame'

export const mount = pageIsland(AttendanceRegisterScreen)
