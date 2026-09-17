"""The records this app lets people read and propose corrections to, and the rules for each.

One policy per doctype. `Record Change Request` is deliberately generic -- it
names a doctype and a document, not an employee -- and this is where that
genericity gets its meaning: a doctype with no policy here is a doctype nobody
can raise a change request against, whatever their permissions.

The registry is assembled from the `self_service_records` hook (see
`tbs_commons.self_service.registry`), so another app adds a record type by
pointing the hook at a dict of its own. Nothing about the request document, the
queue, the workflow or the approval has to be touched to do that.

Each policy answers four questions.

`owner_field` / `owner_doctype` -- whose record is this? With no `owner_doctype`
the field is a Link to User and names the owner directly, which is how `Employee`
works (`user_id`). With one, the field links to another *registered* doctype and
ownership chains through that policy -- which is how a record that hangs off the
employee rather than off the login is meant to be added: an education history or
a set of bank details names its `Employee`, and the person who owns that Employee
owns it. The chain is resolved in `registry.owner_of`, and it is what stops each
new record type needing its own idea of what "mine" means.

`filters` -- extra conditions a record must meet before anyone can claim it.
`Employee` carries `status: Active` here so a leaver's record stops being theirs
to edit the day they leave, rather than on the day somebody remembers.

`proposable` -- the fields a request may name. This is a policy decision, not a
technical one, and the reasoning for `Employee`'s list is with the list.

`display` -- what a read-only page is allowed to show. Named rather than derived
because most doctypes carry fields that have no business on a self-service page
even for their owner; `Employee` carries salary, tax and bank details, and an
endpoint that returned the document would start returning the next such field
the day it is added.
"""

# What an employee may propose a change to.
#
# In the list are the details the employee is the authority on: their phone
# number, their address, who to call in an emergency, their passport number. HR
# holds these because someone has to, not because HR knows them better. A
# correction is the employee's to propose, and HR's only job is to believe them.
#
# Deliberately out is everything the employment relationship itself is made of:
# company, status, joining and relieving dates, department, designation, branch,
# who they report to, their holiday list, their user account and their leave
# approver. Those are not facts about a person that HR happens to store, they are
# decisions the organisation has made -- an employee proposing a change to their
# own department is not correcting a record, they are asking for a transfer,
# which is a different conversation with a different approver.
#
# Name, gender and date of birth are out for a nearer reason: they are identity
# fields that payroll, statutory reporting and ID documents key on, so a change
# to one is a documents-in-hand conversation rather than a form.
EMPLOYEE_PROPOSABLE = (
	# Contact
	"cell_number",
	"personal_email",
	"prefered_contact_email",
	"current_address",
	"permanent_address",
	# Emergency contact
	"person_to_be_contacted",
	"relation",
	"emergency_phone_number",
	# Personal details
	"marital_status",
	"blood_group",
	"passport_number",
)

# What the profile page shows, in the order its own sections run. The proposable
# fields plus the employment and identity context that makes them readable -- you
# cannot check your own record without seeing the parts of it you cannot change.
EMPLOYEE_DISPLAY = (
	"employee_name",
	"image",
	"modified",
	# Basic information
	"salutation",
	"first_name",
	"middle_name",
	"last_name",
	"gender",
	"date_of_birth",
	# Employment
	"company",
	"status",
	"date_of_joining",
	"employee_number",
	"designation",
	"department",
	"branch",
	"reports_to",
	"holiday_list",
	# Access & approvals
	"user_id",
	"leave_approver",
	# Contact
	"cell_number",
	"company_email",
	"personal_email",
	"prefered_contact_email",
	"current_address",
	"permanent_address",
	# Emergency contact
	"person_to_be_contacted",
	"relation",
	"emergency_phone_number",
	# Personal details
	"marital_status",
	"blood_group",
	"passport_number",
	# Exit -- shown only for a leaver, but the page needs the values to decide
	"relieving_date",
	"resignation_letter_date",
	"reason_for_leaving",
	"new_workplace",
)

EMPLOYEE = {
	"doctype": "Employee",
	# `user_id` is a Link to User, so it names the owner outright.
	"owner_field": "user_id",
	# A leaver's record stops being theirs to correct.
	"filters": {"status": "Active"},
	"title_field": "employee_name",
	# One employee record per login, so "my record" has a single answer and the
	# profile page can ask for it without naming one.
	"singular": True,
	"proposable": EMPLOYEE_PROPOSABLE,
	"display": EMPLOYEE_DISPLAY,
}


# What an employee may see of a bank account registered against them.
#
# Read-only: `proposable` is empty, deliberately. Payroll destination details are
# the classic payment-diversion target -- a request to change them is exactly
# what an attacker with a session would raise -- so routing them through a form
# an employee can submit is a decision to be taken on purpose, with its own
# verification, rather than inherited from the profile page because the
# machinery happened to be there. Until then this section shows what payroll
# holds and says who to talk to.
#
# `statement_password` and `integration_id` are absent from `display` and would
# be even if this were writable: the first is a Password field and the second is
# a credential for whatever feed imports the statements. Neither is a fact about
# the employee.
BANK_ACCOUNT_DISPLAY = (
	"account_name",
	"bank",
	"account_type",
	"account_subtype",
	"bank_account_no",
	"iban",
	"branch_code",
	"is_default",
	"disabled",
	"is_company_account",
	"party_type",
	"party",
	"modified",
)

BANK_ACCOUNT = {
	"doctype": "Bank Account",
	# `party` is a Dynamic Link, so the doctype it points at is a field on the
	# row rather than a property of the schema -- which is why `filters` pins
	# `party_type` as well. Without it this policy would claim every bank account
	# whose party id happened to match an employee id.
	"owner_field": "party",
	"owner_doctype": "Employee",
	"filters": {"party_type": "Employee"},
	"title_field": "account_name",
	# The reason this policy exists as a second shape: one employee, several
	# accounts. There is no "my bank account" to resolve, so the page lists them.
	"singular": False,
	"proposable": (),
	"display": BANK_ACCOUNT_DISPLAY,
}
