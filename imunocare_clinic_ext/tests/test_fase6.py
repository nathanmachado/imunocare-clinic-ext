from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_months, nowdate, nowtime

from imunocare_clinic_ext.imunocare_clinic_ext.report.retornos_pendentes.retornos_pendentes import (
	execute,
)
from imunocare_clinic_ext.install import install_imunization_customizations

_EMAIL = "retorno.teste@example.com"
_MOBILE = "+5511955550000"
_CPF = "62648716050"  # CPF válido para teste


def _cleanup():
	for pat in frappe.get_all("Patient", filters={"first_name": "Retorno Teste"}, pluck="name"):
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
	for cust in frappe.get_all("Customer", filters={"customer_name": ("like", "Retorno Teste%")}, pluck="name"):
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


class TestRetornosPendentes(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()
		_cleanup()
		cls.patient = frappe.get_doc(
			{
				"doctype": "Patient",
				"first_name": "Retorno Teste",
				"middle_name": "da",
				"last_name": "Silva",
				"sex": "Female",
				"dob": add_months(nowdate(), -30 * 12),
				"mobile": _MOBILE,
				"email": _EMAIL,
				"cpf": _CPF,
				"pais_nascimento": "Brazil",
				"cidade_nascimento": "Uberlândia",
				"customer_group": "Pessoa Física",
			}
		).insert(ignore_permissions=True).name
		# 3 Medication Requests: atrasada (-10d), vence em breve (+3d), futura (+40d)
		cls.mr_atrasada = cls._mr(add_days(nowdate(), -10), dose=1)
		cls.mr_breve = cls._mr(add_days(nowdate(), 3), dose=2)
		cls.mr_futura = cls._mr(add_days(nowdate(), 40), dose=3)
		frappe.db.commit()

	@classmethod
	def _mr(cls, expected_date, dose):
		practitioner = frappe.db.get_value("Healthcare Practitioner", {}, "name")
		item = frappe.db.get_value("Medication Linked Item", {"parent": "Hepatite B"}, "item_code")
		return frappe.get_doc(
			{
				"doctype": "Medication Request",
				"patient": cls.patient,
				"medication": "Hepatite B",
				"medication_item": item,
				"dose_numero": dose,
				"expected_date": expected_date,
				"order_date": nowdate(),
				"order_time": nowtime(),
				"status": "active-Request Status",
				"dosage": "0-0-1",
				"dosage_form": "Injection",
				"quantity": 1,
				"company": frappe.db.get_value("Company", {}, "name"),
				"practitioner": practitioner,
			}
		).insert(ignore_permissions=True).name

	@classmethod
	def tearDownClass(cls):
		_cleanup()
		super().tearDownClass()

	def _rows_for_patient(self, filters):
		_, data = execute({**filters, "patient": self.patient})
		return data

	def test_default_window_includes_overdue_and_soon(self):
		# Janela padrão (7 dias): atrasada + vence em breve (+3), não a futura (+40).
		rows = self._rows_for_patient({"dias_antecedencia": 7})
		mrs = {r["name"] for r in rows}
		self.assertIn(self.mr_atrasada, mrs)
		self.assertIn(self.mr_breve, mrs)
		self.assertNotIn(self.mr_futura, mrs)

	def test_apenas_atrasadas(self):
		rows = self._rows_for_patient({"apenas_atrasadas": 1})
		mrs = {r["name"] for r in rows}
		self.assertIn(self.mr_atrasada, mrs)
		self.assertNotIn(self.mr_breve, mrs)
		self.assertNotIn(self.mr_futura, mrs)

	def test_dias_atraso_and_situacao(self):
		rows = self._rows_for_patient({"dias_antecedencia": 7})
		atrasada = next(r for r in rows if r["name"] == self.mr_atrasada)
		self.assertEqual(atrasada["dias_atraso"], 10)
		self.assertIn("Atrasada", atrasada["situacao"])
		breve = next(r for r in rows if r["name"] == self.mr_breve)
		self.assertEqual(breve["dias_atraso"], -3)
		self.assertIn("Vence em 3", breve["situacao"])

	def test_wide_window_includes_future(self):
		rows = self._rows_for_patient({"dias_antecedencia": 60})
		self.assertIn(self.mr_futura, {r["name"] for r in rows})

	def test_completed_excluded(self):
		# Marca a atrasada como concluída → some do report.
		frappe.db.set_value("Medication Request", self.mr_atrasada, "status", "completed-Request Status")
		rows = self._rows_for_patient({"dias_antecedencia": 7})
		self.assertNotIn(self.mr_atrasada, {r["name"] for r in rows})
		frappe.db.set_value("Medication Request", self.mr_atrasada, "status", "active-Request Status")

	def test_row_has_contact_fields(self):
		rows = self._rows_for_patient({"dias_antecedencia": 7})
		row = rows[0]
		self.assertEqual(row["mobile"], _MOBILE)
		self.assertEqual(row["medication"], "Hepatite B")
