from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_months, getdate, nowdate

from imunocare_clinic_ext.dose_schedule import gerar_cronograma_doses
from imunocare_clinic_ext.install import install_imunization_customizations
from imunocare_clinic_ext.whatsapp_helpers import get_dose_reminder_whatsapp_params

_EMAIL = "combo.teste@example.com"
_MOBILE = "+5511900000000"
_CPF = "40532176871"  # CPF válido para teste
_SCHEMA = "Calendário PNI 0-1 ano"  # do seed (BCG, Hep B x3, Meningo B x3)


def _cleanup():
	for pat in frappe.get_all("Patient", filters={"first_name": "Combo Teste"}, pluck="name"):
		for mr in frappe.get_all("Medication Request", filters={"patient": pat}, pluck="name"):
			try:
				frappe.delete_doc("Medication Request", mr, force=True, ignore_permissions=True)
			except Exception:
				pass
		try:
			frappe.delete_doc("Patient", pat, force=True, ignore_permissions=True)
		except Exception:
			pass
	for ct in frappe.get_all("Contact", filters={"email_id": _EMAIL}, pluck="name"):
		try:
			frappe.delete_doc("Contact", ct, force=True, ignore_permissions=True)
		except Exception:
			pass
	for cust in frappe.get_all("Customer", filters={"customer_name": ("like", "Combo Teste%")}, pluck="name"):
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


class TestFase5CustomFields(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()

	def test_treatment_plan_template_fields(self):
		for fieldname in ("is_vaccine_combo", "vaccination_schedule"):
			self.assertTrue(
				frappe.db.exists("Custom Field", {"dt": "Treatment Plan Template", "fieldname": fieldname})
			)

	def test_medication_request_fields(self):
		for fieldname in ("dose_numero", "therapy_plan"):
			self.assertTrue(
				frappe.db.exists("Custom Field", {"dt": "Medication Request", "fieldname": fieldname})
			)


class TestDoseSchedule(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()
		_cleanup()
		cls.patient = frappe.get_doc(
			{
				"doctype": "Patient",
				"first_name": "Combo Teste",
				"middle_name": "de",
				"last_name": "Souza",
				"sex": "Male",
				"dob": add_months(nowdate(), -2),  # bebê 2 meses
				"mobile": _MOBILE,
				"email": _EMAIL,
				"cpf": _CPF,
				"pais_nascimento": "Brazil",
				"cidade_nascimento": "Uberlândia",
				"nome_responsavel": "Responsável Combo",
				"cpf_responsavel": "52998224725",
				"customer_group": "Pessoa Física",
			}
		).insert(ignore_permissions=True).name
		frappe.db.commit()
		cls.data_inicio = nowdate()
		cls.mrs = gerar_cronograma_doses(cls.patient, _SCHEMA, data_inicio=cls.data_inicio)

	@classmethod
	def tearDownClass(cls):
		_cleanup()
		super().tearDownClass()

	def test_creates_one_request_per_dose(self):
		# Calendário 0-1 ano do seed: BCG(1) + Hep B(3) + Meningo B(3) = 7 doses
		self.assertEqual(len(self.mrs), 7)

	def test_requests_linked_to_patient(self):
		for mr in self.mrs:
			doc = frappe.get_doc("Medication Request", mr)
			self.assertEqual(doc.patient, self.patient)
			self.assertEqual(doc.status, "active-Request Status")
			self.assertTrue(doc.dose_numero >= 1)

	def test_expected_dates_are_cumulative(self):
		# Hep B: dose1 intervalo 0, dose2 +30, dose3 +120 (do anterior).
		hep = sorted(
			(
				frappe.get_doc("Medication Request", mr)
				for mr in self.mrs
			),
			key=lambda d: (d.medication, d.dose_numero),
		)
		hep_b = [d for d in hep if d.medication == "Hepatite B"]
		self.assertEqual(len(hep_b), 3)
		d1, d2, d3 = hep_b
		base = getdate(self.data_inicio)
		self.assertEqual(getdate(d1.expected_date), base)
		self.assertEqual((getdate(d2.expected_date) - base).days, 30)
		self.assertEqual((getdate(d3.expected_date) - base).days, 150)  # 30 + 120

	def test_dose_reminder_whatsapp_params(self):
		# Pega 2 doses pendentes e formata o template 5.
		hep_b = [
			mr for mr in self.mrs
			if frappe.db.get_value("Medication Request", mr, "medication") == "Hepatite B"
		][:2]
		params = get_dose_reminder_whatsapp_params("Combo Teste de Souza", hep_b)
		self.assertEqual(set(params.keys()), {"nome", "doses", "prazo"})
		self.assertEqual(params["nome"], "Combo Teste de Souza")
		self.assertIn("Hepatite B", params["doses"])
		self.assertIn("dose)", params["doses"])
		self.assertTrue(params["prazo"])
