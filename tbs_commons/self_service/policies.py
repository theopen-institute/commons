"""The self-service configuration this app ships, seeded once on install.

These are `Self Service Record` documents, not the configuration itself. The
configuration lives in the database where an administrator can see and change
it; this is the starting point, written once when the app is installed and never
rewritten afterwards -- see `install.sync_self_service`. A site that has since
added a field, removed one, or turned a record type off keeps what it decided.

What each section is for is explained on the doctype; what is worth recording
here is *why these particular fields*, because that is the judgement a site
inherits and may want to revisit.

In the employee set are the details the employee is the authority on: their
phone number, their address, who to call in an emergency, their passport number.
HR holds these because someone has to, not because HR knows them better. A
correction is the employee's to propose, and HR's only job is to believe them.

Viewable but not proposable is everything the employment relationship is made
of: company, status, joining date, department, designation, branch, who they
report to, their user account and their leave approver. Those are not facts
about a person that HR happens to store, they are decisions the organisation has
made -- an employee proposing a change to their own department is not correcting
a record, they are asking for a transfer, which is a different conversation with
a different approver. Name, gender and date of birth are viewable-only for a
nearer reason: payroll, statutory reporting and ID documents key on them, so a
change is a documents-in-hand conversation rather than a form.

Bank accounts are viewable and nothing more. Payroll destination details are the
classic payment-diversion target, so a form that changes them wants its own
verification rather than inheriting the profile's because the machinery was
there. `statement_password` and `integration_id` are absent altogether: the
first is a credential and the second belongs to whatever feed imports the
statements. Neither is a fact about the employee.
"""

# (section, fieldname, proposable)
EMPLOYEE_FIELDS = (
	("Basic information", "salutation", False),
	("Basic information", "first_name", False),
	("Basic information", "middle_name", False),
	("Basic information", "last_name", False),
	("Basic information", "gender", False),
	("Basic information", "date_of_birth", False),
	("Employment", "company", False),
	("Employment", "status", False),
	("Employment", "date_of_joining", False),
	("Employment", "employee_number", False),
	("Employment", "designation", False),
	("Employment", "department", False),
	("Employment", "branch", False),
	("Employment", "reports_to", False),
	("Employment", "holiday_list", False),
	("Access & approvals", "user_id", False),
	("Access & approvals", "leave_approver", False),
	("Contact", "cell_number", True),
	("Contact", "company_email", False),
	("Contact", "personal_email", True),
	("Contact", "prefered_contact_email", True),
	("Contact", "current_address", True),
	("Contact", "permanent_address", True),
	("Emergency contact", "person_to_be_contacted", True),
	("Emergency contact", "relation", True),
	("Emergency contact", "emergency_phone_number", True),
	("Personal details", "marital_status", True),
	("Personal details", "blood_group", True),
	("Personal details", "passport_number", True),
)

BANK_ACCOUNT_FIELDS = (
	("Account", "account_name", False),
	("Account", "bank", False),
	("Account", "account_type", False),
	("Account", "account_subtype", False),
	("Account", "is_default", False),
	("Account", "disabled", False),
	("Details", "bank_account_no", False),
	("Details", "iban", False),
	("Details", "branch_code", False),
)

SEED = (
	{
		"document_type": "Employee",
		"label": "My profile",
		"route_slug": "employee",
		"icon": "lucide-id-card",
		"nav_order": 10,
		"read_only_notice": (
			"Your details are held by HR. Fields you can correct have a pencil beside "
			"them — your change goes to HR as a proposal."
		),
		"empty_notice": ("There's no profile to show until HR links an employee record to your login."),
		# `user_id` is a Link to User, so it names the owner outright.
		"owner_field": "user_id",
		"title_field": "employee_name",
		# One employee record per login, so "my record" has a single answer.
		"is_singular": 1,
		# A leaver's record stops being theirs to correct.
		"record_filters": '{"status": "Active"}',
		"fields": EMPLOYEE_FIELDS,
	},
	{
		"document_type": "Bank Account",
		"label": "Bank accounts",
		"route_slug": "bank-accounts",
		"icon": "lucide-landmark",
		"nav_order": 20,
		"read_only_notice": (
			"Bank details are held by payroll. To change where you're paid, talk to "
			"them directly — this isn't something to send through a form."
		),
		"empty_notice": (
			"This is where the accounts payroll pays you into would appear. Ask "
			"whoever runs payroll if you expected one here."
		),
		# `party` is a Dynamic Link, so the doctype it points at is a field on the
		# row rather than a property of the schema -- which is why the filters pin
		# `party_type` as well. Without it this would claim every bank account
		# whose party id happened to match an employee id.
		"owner_field": "party",
		"owner_doctype": "Employee",
		"title_field": "account_name",
		# One employee, several accounts: the page lists them.
		"is_singular": 0,
		"record_filters": '{"party_type": "Employee"}',
		"fields": BANK_ACCOUNT_FIELDS,
	},
)
