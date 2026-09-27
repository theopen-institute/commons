// The `commons.banking` island: bank reconciliation, for a desk page. Built by
// `build-islands.mjs`; drawn at /app/commons-banking. See `frame.ts`.
import BankReconciliationScreen from '@/screens/BankReconciliationScreen.vue'
import { pageIsland } from './frame'

export const mount = pageIsland(BankReconciliationScreen)
