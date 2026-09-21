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
]

export default createRouter({
  history: createWebHistory('/commons'),
  routes,
})
