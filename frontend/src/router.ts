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
    // The employee's own record, read only: something a person does about
    // themselves and waits on an approver for, which is what this app is.
    path: '/profile',
    name: 'MyProfile',
    component: () => import('@/pages/MyProfile.vue'),
    meta: { app: 'requests' },
  },
  {
    // The accounts payroll holds against this employee. Its own page rather
    // than a section of the profile: they hang off the employee record instead
    // of living on it, there may be several, and they are read-only for a
    // reason the profile's fields are not -- see `BANK_ACCOUNT` in
    // `tbs_commons.self_service.policies`.
    path: '/profile/bank-accounts',
    name: 'MyBankAccounts',
    component: () => import('@/pages/MyBankAccounts.vue'),
    meta: { app: 'requests' },
  },
  {
    path: '/profile/approvals',
    name: 'ProfileChangeApprovals',
    component: () => import('@/pages/ProfileChangeApprovals.vue'),
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
