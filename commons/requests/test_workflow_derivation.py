"""What the app reads off the active Workflow, without a running site.

These replaced two constants -- the approver role and the open request states --
so the first thing each suite pins is that the derivation still answers exactly
what the constants said, against a chain shaped the way those constants assumed.
The rest is what the constants could not do: follow whatever an administrator
actually built -- which, since nothing installs a chain, is every workflow there
will ever be.

The chain below is this suite's own fixture and nothing else's. It is not a
configuration the app ships or suggests: a site builds its own, and the point of
the tests is that it may be shaped quite differently.
"""

from types import SimpleNamespace
from unittest import TestCase

from commons.requests import procurement_workflow as wf

# What a caller passes to say "there is no workflow" without going to the
# database for one. `None` means the opposite -- look it up.
NO_WORKFLOW = False


# A conventional purchasing chain: the author sends it on, procurement costs it,
# a named approver decides, and procurement can override. Written out here
# because the two fallbacks are only defensible if a chain of this ordinary shape
# still derives exactly what they name.
BY_APPROVER = "doc.approver == frappe.session.user"
CONVENTIONAL_STATES = [
	("Draft", 0),
	("Pending", 0),
	("Under Review", 0),
	("Approved", 1),
	("Rejected", 0),
	("Completed", 1),
	("Canceled", 2),
]
CONVENTIONAL_TRANSITIONS = [
	("Draft", "Pending", "Employee", None),
	("Pending", "Under Review", "Purchase User", None),
	("Under Review", "Approved", "Expense Approver", BY_APPROVER),
	("Under Review", "Rejected", "Expense Approver", BY_APPROVER),
	("Under Review", "Approved", "Purchase User", None),
	("Under Review", "Rejected", "Purchase User", None),
	("Approved", "Canceled", "Purchase User", None),
	("Rejected", "Pending", "Purchase User", None),
]


def conventional_workflow():
	"""A chain of the shape the fallbacks assume, as an object tree."""
	return workflow(CONVENTIONAL_STATES, CONVENTIONAL_TRANSITIONS)


def workflow(states, transitions):
	return SimpleNamespace(
		workflow_state_field="status",
		states=[SimpleNamespace(state=state, doc_status=doc_status) for state, doc_status in states],
		transitions=[
			SimpleNamespace(
				state=state,
				next_state=next_state,
				allowed=allowed,
				condition=condition,
			)
			for state, next_state, allowed, condition in transitions
		],
	)


class TestApproverRoles(TestCase):
	def test_a_conventional_chain_answers_the_role_the_constant_used_to_name(self):
		self.assertEqual(wf.approver_roles(conventional_workflow()), {"Expense Approver"})

	def test_an_unconditioned_override_is_not_this_pages_queue(self):
		"""Purchase User can approve, but not as a request's named approver."""
		roles = wf.approver_roles(
			workflow(
				[("Review", 0), ("Done", 1)],
				[
					("Review", "Done", "Reviewer", "doc.approver == frappe.session.user"),
					("Review", "Done", "Overrider", None),
				],
			)
		)
		self.assertEqual(roles, {"Reviewer"})

	def test_a_retuned_workflow_moves_the_page_with_it(self):
		roles = wf.approver_roles(
			workflow(
				[("Review", 0), ("Done", 1)],
				[("Review", "Done", "Budget Holder", "doc.approver == frappe.session.user")],
			)
		)
		self.assertEqual(roles, {"Budget Holder"})

	def test_a_workflow_that_names_nobody_falls_back(self):
		roles = wf.approver_roles(
			workflow([("Review", 0), ("Done", 1)], [("Review", "Done", "Reviewer", None)])
		)
		self.assertEqual(roles, {wf.FALLBACK_APPROVER_ROLE})

	def test_no_workflow_is_no_queue_rather_than_the_fallback_role(self):
		"""Without a workflow there are no transitions to hold, so no page."""
		self.assertEqual(wf.approver_roles(NO_WORKFLOW), set())


class TestOpenRequestStates(TestCase):
	def test_a_conventional_chain_answers_the_states_the_constant_used_to_name(self):
		self.assertEqual(wf.open_request_states(conventional_workflow()), ("Pending", "Under Review"))

	def test_the_initial_state_is_the_authors_own_copy_not_an_open_ask(self):
		states = wf.open_request_states(
			workflow(
				[("Draft", 0), ("Sent", 0), ("Done", 1)],
				[("Draft", "Sent", "Author", None), ("Sent", "Done", "Decider", None)],
			)
		)
		self.assertEqual(states, ("Sent",))

	def test_a_state_reached_by_turning_a_request_down_is_a_decision(self):
		"""Refusing and approving are the same person's two answers."""
		states = wf.open_request_states(
			workflow(
				[("Draft", 0), ("Review", 0), ("Refused", 0), ("Done", 1)],
				[
					("Draft", "Review", "Author", None),
					("Review", "Done", "Decider", None),
					("Review", "Refused", "Decider", None),
				],
			)
		)
		self.assertEqual(states, ("Review",))

	def test_an_added_review_step_is_counted_without_being_named_here(self):
		states = wf.open_request_states(
			workflow(
				[("Draft", 0), ("Costed", 0), ("Review", 0), ("Refused", 0), ("Done", 1)],
				[
					("Draft", "Costed", "Author", None),
					("Costed", "Review", "Buyer", None),
					("Review", "Done", "Decider", None),
					("Review", "Refused", "Decider", None),
				],
			)
		)
		self.assertEqual(states, ("Costed", "Review"))

	def test_no_workflow_falls_back_to_the_named_states(self):
		self.assertEqual(wf.open_request_states(NO_WORKFLOW), wf.FALLBACK_OPEN_REQUEST_STATES)

	def test_a_workflow_with_nothing_open_answers_so_rather_than_falling_back(self):
		"""Only the *absence* of a workflow falls back to the named states."""
		self.assertEqual(wf.open_request_states(workflow([("Done", 1)], [])), ())
