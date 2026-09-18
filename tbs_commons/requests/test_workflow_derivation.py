"""What the app reads off the active Workflow, without a running site.

These replaced two constants -- the approver role and the open request states --
so the first thing each suite pins is that the derivation still answers exactly
what the constant said, against the workflow `install.py` actually seeds. The
rest is what the constants could not do: follow a workflow an administrator has
retuned.
"""

from types import SimpleNamespace
from unittest import TestCase

from tbs_commons.requests import procurement_workflow as wf
from tbs_commons.requests.install import WORKFLOW_STATES, WORKFLOW_TRANSITIONS

# What a caller passes to say "there is no workflow" without going to the
# database for one. `None` means the opposite -- look it up.
NO_WORKFLOW = False


def seeded_workflow():
	"""The workflow `sync_procurement_workflow` installs, as an object tree."""
	return SimpleNamespace(
		workflow_state_field="status",
		states=[SimpleNamespace(**row) for row in WORKFLOW_STATES],
		transitions=[
			SimpleNamespace(**{"condition": None, "allow_self_approval": 0, **row})
			for row in WORKFLOW_TRANSITIONS
		],
	)


def workflow(states, transitions):
	return SimpleNamespace(
		workflow_state_field="status",
		states=[
			SimpleNamespace(state=state, doc_status=doc_status)
			for state, doc_status in states
		],
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
	def test_the_seeded_workflow_still_answers_the_role_it_used_to_name(self):
		self.assertEqual(wf.approver_roles(seeded_workflow()), {"Expense Approver"})

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

	def test_a_workflow_that_names_nobody_falls_back_to_the_seeded_role(self):
		roles = wf.approver_roles(
			workflow([("Review", 0), ("Done", 1)], [("Review", "Done", "Reviewer", None)])
		)
		self.assertEqual(roles, {wf.SEEDED_APPROVER_ROLE})

	def test_no_workflow_is_no_queue_rather_than_the_seeded_role(self):
		"""Without a workflow there are no transitions to hold, so no page."""
		self.assertEqual(wf.approver_roles(NO_WORKFLOW), set())


class TestOpenRequestStates(TestCase):
	def test_the_seeded_workflow_still_answers_the_states_it_used_to_name(self):
		self.assertEqual(
			wf.open_request_states(seeded_workflow()), ("Pending", "Under Review")
		)

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

	def test_no_workflow_falls_back_to_what_the_app_seeds(self):
		self.assertEqual(wf.open_request_states(NO_WORKFLOW), wf.SEEDED_OPEN_REQUEST_STATES)

	def test_a_workflow_with_nothing_open_answers_so_rather_than_falling_back(self):
		"""Only the *absence* of a workflow falls back to the seeded names."""
		self.assertEqual(wf.open_request_states(workflow([("Done", 1)], [])), ())
