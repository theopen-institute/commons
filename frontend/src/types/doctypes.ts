interface DocType {
    name: string;
    creation: string;
    modified: string;
    owner: string;
    modified_by: string;
  }

  interface ChildDocType extends DocType {
    parent?: string;
    parentfield?: string;
    parenttype?: string;
    idx?: number;
  }
  
// Last updated: 2024-03-27 13:09:38.507746
export interface EmployeeEducation extends ChildDocType {
  /** School/University: Small Text */
  school_univ?: string;
  /** Qualification: Data */
  qualification?: string;
  /** Level: Select */
  level?: 'Graduate' | 'Post Graduate' | 'Under Graduate';
  /** Year of Passing: Int */
  year_of_passing?: number;
  /** Class / Percentage: Data */
  class_per?: string;
  /** Major/Optional Subjects: Text */
  maj_opt_subj?: string;
}

// Last updated: 2024-03-27 13:09:38.624280
export interface EmployeeExternalWorkHistory extends ChildDocType {
  /** Company: Data */
  company_name?: string;
  /** Designation: Data */
  designation?: string;
  /** Salary: Currency */
  salary?: any;
  /** Address: Small Text */
  address?: string;
  /** Contact: Data */
  contact?: string;
  /** Total Experience: Data */
  total_experience?: string;
}

// Last updated: 2024-03-27 13:09:39.822645
export interface EmployeeInternalWorkHistory extends ChildDocType {
  /** Branch: Link (Branch) */
  branch?: string;
  /** Department: Link (Department) */
  department?: string;
  /** Designation: Link (Designation) */
  designation?: string;
  /** From Date: Date */
  from_date?: string;
  /** To Date: Date */
  to_date?: string;
}

// Last updated: 2026-08-21 23:11:42.091886
export interface Employee extends DocType {
  /** Employee: Data */
  employee?: string;
  /** Series: Select */
  naming_series?: 'HR-EMP-';
  /** Salutation: Link (Salutation) */
  salutation?: string;
  /** First Name: Data */
  first_name: string;
  /** Middle Name: Data */
  middle_name?: string;
  /** Last Name: Data */
  last_name?: string;
  /** Full Name: Data */
  employee_name?: string;
  /** Image: Attach Image */
  image?: string;
  /** Company: Link (Company) */
  company: string;
  /** Status: Select */
  status: 'Active' | 'Inactive' | 'Suspended' | 'Left';
  /** Employee Number: Data */
  employee_number?: string;
  /** Gender: Link (Gender) */
  gender: string;
  /** Date of Birth: Date */
  date_of_birth: string;
  /** Date of Joining: Date */
  date_of_joining: string;
  /** Emergency Phone: Data */
  emergency_phone_number?: string;
  /** Emergency Contact Name: Data */
  person_to_be_contacted?: string;
  /** Relation: Data */
  relation?: string;
  /** User ID: Link (User) */
  user_id?: string;
  /** Create User Permission: Check */
  create_user_permission: 0 | 1;
  /** Create User Automatically: Check */
  create_user_automatically: 0 | 1;
  /** Offer Date: Date */
  scheduled_confirmation_date?: string;
  /** Confirmation Date: Date */
  final_confirmation_date?: string;
  /** Contract End Date: Date */
  contract_end_date?: string;
  /** Notice (days): Int */
  notice_number_of_days?: number;
  /** Date Of Retirement: Date */
  date_of_retirement?: string;
  /** Department: Link (Department) */
  department?: string;
  /** Designation: Link (Designation) */
  designation?: string;
  /** Reports to: Link (Employee) */
  reports_to?: string;
  /** Branch: Link (Branch) */
  branch?: string;
  /** Holiday List: Link (Holiday List) */
  holiday_list?: string;
  /** Salary Mode: Select */
  salary_mode?: '' | 'Bank' | 'Cash' | 'Cheque';
  /** Bank Name: Data */
  bank_name?: string;
  /** Bank A/C No.: Data */
  bank_ac_no?: string;
  /** Mobile: Data */
  cell_number?: string;
  /** Preferred Contact Email: Select */
  prefered_contact_email?: '' | 'Company Email' | 'Personal Email' | 'User ID';
  /** Preferred Email: Data */
  prefered_email?: string;
  /** Company Email: Data */
  company_email?: string;
  /** Personal Email: Data */
  personal_email?: string;
  /** Unsubscribed: Check */
  unsubscribed: 0 | 1;
  /** Permanent Address Is: Select */
  permanent_accommodation_type?: '' | 'Rented' | 'Owned';
  /** Permanent Address: Small Text */
  permanent_address?: string;
  /** Current Address Is: Select */
  current_accommodation_type?: '' | 'Rented' | 'Owned';
  /** Current Address: Small Text */
  current_address?: string;
  /** Bio / Cover Letter: Text Editor */
  bio?: string;
  /** Passport Number: Data */
  passport_number?: string;
  /** Date of Issue: Date */
  date_of_issue?: string;
  /** Valid Up To: Date */
  valid_upto?: string;
  /** Place of Issue: Data */
  place_of_issue?: string;
  /** Marital Status: Select */
  marital_status?: '' | 'Single' | 'Married' | 'Divorced' | 'Widowed';
  /** Blood Group: Select */
  blood_group?: '' | 'A+' | 'A-' | 'B+' | 'B-' | 'AB+' | 'AB-' | 'O+' | 'O-';
  /** Family Background: Small Text */
  family_background?: string;
  /** Health Details: Small Text */
  health_details?: string;
  /** Education: Table (Employee Education) */
  education: EmployeeEducation[];
  /** External Work History: Table (Employee External Work History) */
  external_work_history: EmployeeExternalWorkHistory[];
  /** Internal Work History: Table (Employee Internal Work History) */
  internal_work_history: EmployeeInternalWorkHistory[];
  /** Resignation Letter Date: Date */
  resignation_letter_date?: string;
  /** Relieving Date: Date */
  relieving_date?: string;
  /** Reason for Leaving: Small Text */
  reason_for_leaving?: string;
  /** Leave Encashed?: Select */
  leave_encashed?: '' | 'Yes' | 'No';
  /** Encashment Date: Date */
  encashment_date?: string;
  /** Exit Interview Held On: Date */
  held_on?: string;
  /** New Workplace: Data */
  new_workplace?: string;
  /** Feedback: Small Text */
  feedback?: string;
  /** lft: Int */
  lft?: number;
  /** rgt: Int */
  rgt?: number;
  /** Old Parent: Data */
  old_parent?: string;
  /** Attendance Device ID (Biometric/RF tag ID): Data */
  attendance_device_id?: string;
  /** Salary Currency: Link (Currency) */
  salary_currency?: string;
  /** Cost to Company (CTC): Currency */
  ctc?: any;
  /** IBAN: Data */
  iban?: string;
}
