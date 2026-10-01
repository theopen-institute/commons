"""Department budgets off: every hook stands aside, and no site is needed to say so."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from commons.requests import budget


def material_request(**fields):
	doc = SimpleNamespace(
		**{
			"doctype": "Material Request",
			"material_request_type": "Purchase",
			"docstatus": 1,
			"company": "Company",
			"department": None,
			"items": [],
			**fields,
		}
	)
	doc.get = lambda key, default=None: getattr(doc, key, default)
	return doc


class TestBudgetsSwitchedOff(TestCase):
	def setUp(self):
		switch = patch.object(budget, "enforced", return_value=False)
		switch.start()
		self.addCleanup(switch.stop)
		# Anything that reaches an allocation has gone past the switch.
		reached = patch.object(budget, "find_budget", side_effect=AssertionError("asked for a budget"))
		reached.start()
		self.addCleanup(reached.stop)

	def test_a_material_request_with_no_department_or_budget_submits(self):
		self.assertIsNone(budget.validate_material_request(material_request()))

	def test_submitting_a_material_request_charges_nothing(self):
		with patch.object(budget, "persist_amounts", side_effect=AssertionError("charged")):
			budget.charge_material_request(material_request())

	def test_a_submitted_material_request_may_change(self):
		budget.protect_submitted_material_request(material_request(department="Dept"))

	def test_approving_a_procurement_request_asks_no_allocation(self):
		doc = SimpleNamespace(doctype=budget.REQUEST, docstatus=1)
		with patch.object(budget, "budget_name", side_effect=AssertionError("looked up")):
			budget.enforce_request_allocation(doc)

	def test_the_procurement_pages_show_no_budget(self):
		with patch.object(budget, "can_view_summary", side_effect=AssertionError("asked")):
			self.assertIsNone(budget.request_summary(SimpleNamespace()))


class TestTheSwitch(TestCase):
	def test_reads_its_own_setting(self):
		with patch.object(budget.settings, "feature_enabled", return_value=True) as read:
			self.assertTrue(budget.enforced())
		read.assert_called_once_with(budget.settings.ENABLE_DEPARTMENT_BUDGETS)
