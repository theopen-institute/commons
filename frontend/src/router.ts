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
    path: '/employees',
    name: 'EmployeeList',
    component: () => import('@/pages/EmployeeList.vue'),
    meta: { app: 'employees' },
  },
  {
    path: '/employees/new',
    name: 'NewEmployee',
    component: () => import('@/pages/NewEmployee.vue'),
    meta: { app: 'employees' },
  },
  {
    // Employee names come from a naming series (HR-EMP-00001), so a plain
    // param is enough — no slashes to worry about.
    path: '/employees/:name',
    name: 'Employee',
    component: () => import('@/pages/EmployeeDetail.vue'),
    props: true,
    meta: { app: 'employees' },
  },
  {
    // Above both sections, and ungated: every user of this app sees the same
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
    // The employee's own record, read only. Under `requests` rather than
    // `employees`: this is something a person does about themselves and waits
    // on an approver for, which is what that app is, and the directory next
    // door is the other half -- everyone else's records, for the people who
    // maintain them.
    path: '/profile',
    name: 'MyProfile',
    component: () => import('@/pages/MyProfile.vue'),
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
