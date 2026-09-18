import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import type { AppKey } from '@/data/apps'

declare module 'vue-router' {
  interface RouteMeta {
    /** Which app this route belongs to — drives the sidebar. Every route that
     *  renders a page declares one; the landing redirect has none. */
    app?: AppKey
  }
}

const routes: RouteRecordRaw[] = [
  {
    // Bare /tbs_commons lands on announcements: the one page every user of this
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
    meta: { app: 'requests' },
  },
  {
    // Where the Requests tile lands: which of the two sections opens depends on
    // permissions that haven't loaded yet, so a component decides.
    path: '/requests',
    name: 'RequestsHome',
    component: () => import('@/pages/RequestsHome.vue'),
    meta: { app: 'requests' },
  },
  {
    // Every self-service page, addressed by the slug its configuration gives it.
    // `/profile` alone lands on the first one this user can open, which is a
    // permission answer away -- so a component redirects, not a route.
    path: '/profile',
    name: 'SelfServiceHome',
    component: () => import('@/pages/SelfServiceHome.vue'),
    meta: { app: 'requests' },
  },
  {
    path: '/profile/:slug',
    name: 'SelfServiceRecord',
    component: () => import('@/pages/SelfServiceRecord.vue'),
    props: true,
    meta: { app: 'requests' },
  },
  {
    path: '/leave',
    name: 'MyLeave',
    component: () => import('@/pages/MyLeave.vue'),
    meta: { app: 'requests' },
  },
  {
    path: '/leave/approvals',
    name: 'LeaveApprovals',
    component: () => import('@/pages/LeaveApprovals.vue'),
    meta: { app: 'requests' },
  },
  {
    path: '/expenses',
    name: 'MyExpenses',
    component: () => import('@/pages/MyExpenses.vue'),
    meta: { app: 'requests' },
  },
  {
    path: '/expenses/approvals',
    name: 'ExpenseApprovals',
    component: () => import('@/pages/ExpenseApprovals.vue'),
    meta: { app: 'requests' },
  },
  {
    path: '/procurement',
    name: 'MyProcurement',
    component: () => import('@/pages/MyProcurement.vue'),
    meta: { app: 'requests' },
  },
  {
    path: '/procurement/approvals',
    name: 'ProcurementApprovals',
    component: () => import('@/pages/ProcurementApprovals.vue'),
    meta: { app: 'requests' },
  },
]

export default createRouter({
  history: createWebHistory('/tbs_commons'),
  routes,
})
