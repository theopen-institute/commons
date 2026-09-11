import { toValue, type MaybeRefOrGetter } from 'vue'
import { useDoc, useList, useNewDoc } from 'frappe-ui'
import type { Filters } from 'frappe-ui'
import type { Employee } from '@/types/doctypes'
import { listFields } from './employeeFields'

export type { Employee }

/** The columns the list view reads. */
export type EmployeeListRow = Pick<
  Employee,
  (typeof listFields)[number] & keyof Employee
> & { name: string }

export function useEmployeeList(options: {
  search: MaybeRefOrGetter<string>
  status: MaybeRefOrGetter<string>
}) {
  return useList<EmployeeListRow>({
    doctype: 'Employee',
    fields: [...listFields],
    // A getter, so an empty box or "All statuses" drops the filter instead of
    // sending `status: ''` and matching nothing.
    filters: () => {
      const filters: Filters = {}
      const status = toValue(options.status)
      const search = toValue(options.search)
      if (status) filters.status = status
      // `like` gets its own `%` wrapping, and an empty term is dropped.
      if (search) filters.employee_name = ['like', search]
      return filters
    },
    orderBy: 'modified desc',
    limit: 20,
  })
}

export function useEmployee(name: MaybeRefOrGetter<string>) {
  return useDoc<Employee>({
    doctype: 'Employee',
    name,
  })
}

export function useNewEmployee() {
  return useNewDoc<Employee>('Employee', {
    // The two the server would reject a blank form on, prefilled with the
    // answer that is right nearly every time.
    status: 'Active',
    naming_series: 'HR-EMP-',
  })
}
