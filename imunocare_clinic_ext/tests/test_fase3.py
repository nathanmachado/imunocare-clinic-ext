from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_months, now_datetime, nowdate

from imunocare_clinic_ext.install import install_imunization_customizations

_EMAIL = "adulto.teste.esavi@example.com"
_MOBILE = "+5511922222222"
_CPF = "39053344705"  # CPF válido para teste


def _cleanup():
	for ar in frappe.get_all("Adverse Reaction", filters={"patient_name": ("like", "Adulto ESAVI%")}, pluck="name"):
		try:
			doc = frappe.get_doc("Adverse Reaction", ar)
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc("Adverse Reaction", ar, force=True, ignore_permissions=True)
		except Exception:
			pass
	for pat in frappe.get_all("Patient", filters={"first_name": "Adulto ESAVI"}, pluck="name"):
		try:
			frappe.delete_doc("Patient", pat, force=True, ignore_permissions=True)
		except Exception:
			pass
	for ct in frappe.get_all("Contact", filters={"email_id": _EMAIL}, pluck="name"):
		try:
			frappe.delete_doc("Contact", ct, force=True, ignore_permissions=True)
		except Exception:
			pass
	for cust in frappe.get_all("Customer", filters={"customer_name": ("like", "Adulto ESAVI%")}, pluck="name"):
		try:
			frappe.delete_doc("Customer", cust, force=True, ignore_permissions=True)
		except Exception:
			pass
	if frappe.db.exists("User", _EMAIL):
		try:
			frappe.delete_doc("User", _EMAIL, force=True, ignore_permissions=True)
		except Exception:
			pass
	frappe.db.commit()


class TestAdverseReactionSetup(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()

	def test_doctype_exists_and_submittable(self):
		self.assertTrue(frappe.db.exists("DocType", "Adverse Reaction"))
		meta = frappe.get_meta("Adverse Reaction")
		self.assertTrue(meta.is_submittable)

	def test_registered_in_patient_history(self):
		row = frappe.db.get_value(
			"Patient History Custom Document Type",
			{"document_type": "Adverse Reaction"},
			"date_fieldname",
		)
		self.assertEqual(row, "data_inicio")


class TestAdverseReactionFlow(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()
		_cleanup()
		cls.patient = frappe.get_doc(
			{
				"doctype": "Patient",
				"first_name": "Adulto ESAVI",
				"middle_name": "de",
				"last_name": "Teste",
				"sex": "Male",
				"dob": add_months(nowdate(), -30 * 12),  # 30 anos
				"mobile": _MOBILE,
				"email": _EMAIL,
				"cpf": _CPF,
				"pais_nascimento": "Brazil",
				"cidade_nascimento": "Uberlândia",
				"customer_group": "Pessoa Física",
			}
		).insert(ignore_permissions=True).name
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		_cleanup()
		super().tearDownClass()

	def _make_reaction(self, gravidade="Leve", notificada=0):
		return frappe.get_doc(
			{
				"doctype": "Adverse Reaction",
				"patient": self.patient,
				"data_inicio": now_datetime(),
				"gravidade": gravidade,
				"sintomas": "Febre e dor local",
				"medication": "BCG",
				"lote": "LOTE-X1",
				"dose_numero": 1,
				"notificada_anvisa": notificada,
			}
		)

	def test_create_and_submit(self):
		doc = self._make_reaction()
		doc.insert(ignore_permissions=True)
		self.assertTrue(doc.name.startswith("ESAVI-"))
		doc.submit()
		self.assertEqual(doc.docstatus, 1)

	def test_patient_name_fetched(self):
		doc = self._make_reaction()
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.patient_name, "Adulto ESAVI de Teste")

	def test_serious_reaction_does_not_block(self):
		# Reação Grave não notificada apenas alerta (msgprint), não bloqueia.
		doc = self._make_reaction(gravidade="Grave", notificada=0)
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.gravidade, "Grave")
