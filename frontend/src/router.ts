import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import type { AppKey } from '@/data/apps'

declare module 'vue-router' {
  interface RouteMeta {
    /** Which app this route belongs to — drives the sidebar. Every route
     *  except the landing redirect declares one. */
    app?: AppKey
  }
}

const routes: RouteRecordRaw[] = [
  {
    // Bare /tbsapp: which app to open depends on permissions that haven't
    // loaded yet, so a component decides rather than a static redirect.
    path: '/',
    name: 'Landing',
    component: () => import('@/pages/Landing.vue'),
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
    path: '/leave',
    name: 'MyLeave',
    component: () => import('@/pages/MyLeave.vue'),
    meta: { app: 'leave' },
  },
  {
    path: '/leave/approvals',
    name: 'LeaveApprovals',
    component: () => import('@/pages/LeaveApprovals.vue'),
    meta: { app: 'leave' },
  },
  {
    path: '/procurement',
    name: 'MyProcurement',
    component: () => import('@/pages/MyProcurement.vue'),
    meta: { app: 'procurement' },
  },
  {
    path: '/procurement/approvals',
    name: 'ProcurementApprovals',
    component: () => import('@/pages/ProcurementApprovals.vue'),
    meta: { app: 'procurement' },
  },
]

export default createRouter({
  history: createWebHistory('/tbsapp'),
  routes,
})
