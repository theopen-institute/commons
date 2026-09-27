// The `commons.capture` island: document capture, for a desk page. Built by
// `build-islands.mjs`; drawn at /app/commons-capture. See `frame.ts`.
import DocumentCaptureScreen from '@/screens/DocumentCaptureScreen.vue'
import { pageIsland } from './frame'

export const mount = pageIsland(DocumentCaptureScreen)
