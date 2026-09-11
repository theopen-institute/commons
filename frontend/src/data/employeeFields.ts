/**
 * The subset of Employee this tool edits.
 *
 * Employee carries 109 fields across nine tabs in the desk; almost none of
 * them belong in a tool whose job is "add a person and keep their details
 * right". These definitions are the whole UI contract: both the create form
 * and the detail page render from them, so a field is added in one place.
 *
 * Fieldnames, types, `required` flags and select options mirror the doctype in
 * erpnext/setup/doctype/employee. Where they disagree the server wins — it
 * validates every write — so keep them in step.
 */

export type EmployeeFieldType =
  | 'text'
  | 'email'
  | 'tel'
  | 'select'
  | 'date'
  | 'link'
  | 'textarea'

export interface SelectOption {
  label: string
  value: string
}

export interface EmployeeField {
  fieldname: string
  label: string
  type: EmployeeFieldType
  /** Server-enforced mandatory field. Marks the label and blocks submit. */
  required?: boolean
  /** `select` only. A leading blank option is added for optional fields. */
  options?: string[]
  /** `link` only. The doctype to search. */
  doctype?: string
  /** `link` only. Filters passed to the link search. */
  filters?: Record<string, unknown>
  placeholder?: string
  description?: string
  /** Included in the create form. Everything else is edit-only. */
  onCreate?: boolean
}

export interface EmployeeSection {
  title: string
  description?: string
  fields: EmployeeField[]
  /** Sections that only make sense for some records, e.g. Exit for leavers. */
  visibleWhen?: (doc: Record<string, unknown>) => boolean
}

const STATUS_OPTIONS = ['Active', 'Inactive', 'Suspended', 'Left']

export const employeeSections: EmployeeSection[] = [
  {
    title: 'Basic information',
    fields: [
      {
        fieldname: 'salutation',
        label: 'Salutation',
        type: 'link',
        doctype: 'Salutation',
      },
      {
        fieldname: 'first_name',
        label: 'First name',
        type: 'text',
        required: true,
        onCreate: true,
      },
      { fieldname: 'middle_name', label: 'Middle name', type: 'text' },
      {
        fieldname: 'last_name',
        label: 'Last name',
        type: 'text',
        onCreate: true,
      },
      {
        fieldname: 'gender',
        label: 'Gender',
        type: 'link',
        doctype: 'Gender',
        required: true,
        onCreate: true,
      },
      {
        fieldname: 'date_of_birth',
        label: 'Date of birth',
        type: 'date',
        required: true,
        onCreate: true,
      },
    ],
  },
  {
    title: 'Employment',
    fields: [
      {
        fieldname: 'company',
        label: 'Company',
        type: 'link',
        doctype: 'Company',
        required: true,
        onCreate: true,
      },
      {
        fieldname: 'status',
        label: 'Status',
        type: 'select',
        options: STATUS_OPTIONS,
        required: true,
        onCreate: true,
      },
      {
        fieldname: 'date_of_joining',
        label: 'Date of joining',
        type: 'date',
        required: true,
        onCreate: true,
      },
      {
        fieldname: 'employee_number',
        label: 'Employee number',
        type: 'text',
        description: 'Your own payroll or HR reference, if you use one.',
      },
      {
        fieldname: 'designation',
        label: 'Designation',
        type: 'link',
        doctype: 'Designation',
        onCreate: true,
      },
      {
        fieldname: 'department',
        label: 'Department',
        type: 'link',
        doctype: 'Department',
        onCreate: true,
      },
      {
        fieldname: 'branch',
        label: 'Branch',
        type: 'link',
        doctype: 'Branch',
      },
      {
        fieldname: 'reports_to',
        label: 'Reports to',
        type: 'link',
        doctype: 'Employee',
      },
      {
        fieldname: 'holiday_list',
        label: 'Holiday list',
        type: 'link',
        doctype: 'Holiday List',
      },
    ],
  },
  {
    title: 'Access & approvals',
    description:
      'What this employee can do in the system, and who signs off their leave.',
    fields: [
      {
        fieldname: 'user_id',
        label: 'User account',
        type: 'link',
        doctype: 'User',
        description:
          'The login this employee uses. Required before they can request their own leave.',
      },
      {
        fieldname: 'leave_approver',
        label: 'Leave approver',
        type: 'link',
        doctype: 'User',
        description:
          'The supervisor who approves this employee\'s leave. Needs the Leave Approver role.',
      },
    ],
  },
  {
    title: 'Contact',
    fields: [
      {
        fieldname: 'cell_number',
        label: 'Mobile',
        type: 'tel',
        onCreate: true,
      },
      {
        fieldname: 'company_email',
        label: 'Company email',
        type: 'email',
        onCreate: true,
      },
      { fieldname: 'personal_email', label: 'Personal email', type: 'email' },
      {
        fieldname: 'prefered_contact_email',
        label: 'Preferred email',
        type: 'select',
        options: ['Company Email', 'Personal Email', 'User ID'],
        description: 'Which address the system uses to reach this employee.',
      },
      {
        fieldname: 'current_address',
        label: 'Current address',
        type: 'textarea',
      },
      {
        fieldname: 'permanent_address',
        label: 'Permanent address',
        type: 'textarea',
      },
    ],
  },
  {
    title: 'Emergency contact',
    fields: [
      {
        fieldname: 'person_to_be_contacted',
        label: 'Contact name',
        type: 'text',
      },
      { fieldname: 'relation', label: 'Relation', type: 'text' },
      {
        fieldname: 'emergency_phone_number',
        label: 'Contact phone',
        type: 'tel',
      },
    ],
  },
  {
    title: 'Personal details',
    fields: [
      {
        fieldname: 'marital_status',
        label: 'Marital status',
        type: 'select',
        options: ['Single', 'Married', 'Divorced', 'Widowed'],
      },
      {
        fieldname: 'blood_group',
        label: 'Blood group',
        type: 'select',
        options: ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'],
      },
      {
        fieldname: 'passport_number',
        label: 'Passport number',
        type: 'text',
      },
    ],
  },
  {
    title: 'Exit',
    description: 'Shown because this employee is marked as having left.',
    visibleWhen: (doc) => doc.status === 'Left',
    fields: [
      { fieldname: 'relieving_date', label: 'Relieving date', type: 'date' },
      {
        fieldname: 'resignation_letter_date',
        label: 'Resignation letter date',
        type: 'date',
      },
      {
        fieldname: 'reason_for_leaving',
        label: 'Reason for leaving',
        type: 'textarea',
      },
      { fieldname: 'new_workplace', label: 'New workplace', type: 'text' },
    ],
  },
]

/** Flat list of every field this tool touches. */
export const allEmployeeFields: EmployeeField[] = employeeSections.flatMap(
  (section) => section.fields,
)

/**
 * The create form: the mandatory fields plus the handful worth capturing while
 * the details are in front of you. Everything else is a field on the record
 * once it exists.
 */
export const createSections: EmployeeSection[] = employeeSections
  .map((section) => ({
    ...section,
    fields: section.fields.filter((field) => field.onCreate),
  }))
  .filter((section) => section.fields.length > 0)

/** Fieldnames the list view needs beyond `name`. */
export const listFields = [
  'name',
  'employee_name',
  'designation',
  'department',
  'company',
  'status',
  'image',
  'date_of_joining',
  'company_email',
  'modified',
] as const

export function isFieldFilled(value: unknown): boolean {
  return value !== null && value !== undefined && value !== ''
}

/** Fieldnames of the required fields the given doc has not filled in. */
export function missingRequiredFields(
  doc: Record<string, unknown>,
  fields: EmployeeField[],
): EmployeeField[] {
  return fields.filter(
    (field) => field.required && !isFieldFilled(doc[field.fieldname]),
  )
}
