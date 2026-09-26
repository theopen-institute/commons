import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import type { PageKey } from '@/data/shell'

declare module 'vue-router' {
  interface RouteMeta {
    /** Which of this app's own pages this route renders — what the sidebar
     *  works out the current workspace from, since a page sits in exactly one
     *  (see `data/shell.ts`). The self-service routes declare none: their slug
     *  is what says which row they are. Nor do the two landing redirects, which
     *  are on their way somewhere that does. */
    page?: PageKey
  }
}

const routes: RouteRecordRaw[] = [
  {
    // Bare /commons lands on announcements: the one page every user of this
    // app can open, so it needs no permission answer to redirect on.
    path: '/',
    redirect: { name: 'Announcements' },
  },
  {
    // Above the sections, and ungated: every user of this app sees the same
    // announcements. It is also where the desk icon lands.
    path: '/announcements',
    name: 'Announcements',
    component: () => import('@/pages/Announcements.vue'),
    meta: { page: 'announcements' },
  },
  {
    // The reader's own balances. Off the requests tree and alone at the top
    // level, because it is not one: nothing is raised here and nobody approves
    // anything, so it has neither an approvals tab nor a route to pair with.
    //
    // `/account` rather than `/balance` -- it is an account with a balance on
    // it, and the address outlives whatever the page's headline figure is
    // called. `search.py` holds the same path; see `PAGE_PATHS` there for why
    // the server needs its own copy.
    path: '/account',
    name: 'AccountBalance',
    component: () => import('@/pages/AccountBalance.vue'),
    meta: { page: 'statement' },
  },
  {
    // The teaching register. One page, no tabs: the term and the course it is
    // showing live in the query string rather than in the path, because they
    // are a view of it rather than a different page -- and because a link to
    // "this course, this term" is the thing colleagues actually send each
    // other. See `AttendanceRegister.vue`.
    path: '/attendance',
    name: 'AttendanceRegister',
    component: () => import('@/pages/AttendanceRegister.vue'),
    meta: { page: 'attendance' },
  },
  {
    // One bank account's statement for a period. Like the register, the
    // account, the dates and the view are in the query string, because "OI
    // Checking for July" is a view of this page and a link worth sending. See
    // `BankReconciliation.vue`.
    //
    // `/banking` rather than `/reconciliation`: it is where a bank account's
    // books are kept, and a page for importing statements would sit beside
    // it. `search.py` holds the same path.
    path: '/banking',
    name: 'BankReconciliation',
    component: () => import('@/pages/BankReconciliation.vue'),
    meta: { page: 'reconciliation' },
  },
  {
    // A scan in, a draft Purchase Invoice out. `/capture` rather than
    // `/purchase-invoices`, because it is where documents are read from scans
    // and bank statements are the next it should take. `search.py` holds the
    // same path.
    path: '/capture',
    name: 'DocumentCapture',
    component: () => import('@/pages/DocumentCapture.vue'),
    meta: { page: 'capture' },
  },
  {
    // Where the Requests tile lands: which of the two sections opens depends on
    // permissions that haven't loaded yet, so a component decides.
    //
    // The three sections live under it rather than beside it -- they are one
    // job in three forms, which is why they share a sidebar group, a Python
    // package and a data module. Flat paths rather than nested routes: nothing
    // is shared at render time, so there is no parent component to render a
    // `<router-view>` into.
    path: '/requests',
    name: 'RequestsHome',
    component: () => import('@/pages/RequestsHome.vue'),
  },
  {
    // Every self-service page, addressed by the slug its configuration gives it.
    // `/profile` alone lands on the first one this user can open, which is a
    // permission answer away -- so a component redirects, not a route.
    path: '/profile',
    name: 'SelfServiceHome',
    component: () => import('@/pages/SelfServiceHome.vue'),
  },
  {
    path: '/profile/:slug',
    name: 'SelfServiceRecord',
    component: () => import('@/pages/SelfServiceRecord.vue'),
    props: true,
  },
  {
    path: '/requests/leave',
    name: 'MyLeave',
    component: () => import('@/pages/MyLeave.vue'),
    meta: { page: 'leave' },
  },
  {
    path: '/requests/leave/approvals',
    name: 'LeaveApprovals',
    component: () => import('@/pages/LeaveApprovals.vue'),
    meta: { page: 'leave' },
  },
  {
    path: '/requests/expenses',
    name: 'MyExpenses',
    component: () => import('@/pages/MyExpenses.vue'),
    meta: { page: 'expense' },
  },
  {
    path: '/requests/expenses/approvals',
    name: 'ExpenseApprovals',
    component: () => import('@/pages/ExpenseApprovals.vue'),
    meta: { page: 'expense' },
  },
  {
    path: '/requests/procurement',
    name: 'MyProcurement',
    component: () => import('@/pages/MyProcurement.vue'),
    meta: { page: 'procurement' },
  },
  {
    path: '/requests/procurement/approvals',
    name: 'ProcurementApprovals',
    component: () => import('@/pages/ProcurementApprovals.vue'),
    meta: { page: 'procurement' },
  },
  {
    // Last, and matching anything the routes above do not. Without it an
    // address that names no page — an old link, a typo — rendered an empty
    // frame with no word as to why.
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/pages/NotFound.vue'),
  },
]

export default createRouter({
  history: createWebHistory('/commons'),
  routes,
})
