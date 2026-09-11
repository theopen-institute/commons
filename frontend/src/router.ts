import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: { name: 'EmployeeList' },
  },
  {
    path: '/employees',
    name: 'EmployeeList',
    component: () => import('@/pages/EmployeeList.vue'),
  },
  {
    path: '/employees/new',
    name: 'NewEmployee',
    component: () => import('@/pages/NewEmployee.vue'),
  },
  {
    // Employee names come from a naming series (HR-EMP-00001), so a plain
    // param is enough — no slashes to worry about.
    path: '/employees/:name',
    name: 'Employee',
    component: () => import('@/pages/EmployeeDetail.vue'),
    props: true,
  },
  {
    path: '/leave',
    name: 'MyLeave',
    component: () => import('@/pages/MyLeave.vue'),
  },
  {
    path: '/approvals',
    name: 'LeaveApprovals',
    component: () => import('@/pages/LeaveApprovals.vue'),
  },
]

export default createRouter({
  history: createWebHistory('/tbsapp'),
  routes,
})
