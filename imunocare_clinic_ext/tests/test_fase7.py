from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_months, nowdate

from imunocare_clinic_ext.install import install_imunization_customizations
from imunocare_clinic_ext.whatsapp_helpers import (
	format_vaccine_list,
	get_appointment_whatsapp_params,
	modalidade_label,
)

_EMAIL = "wpp.teste@example.com"
_MOBILE = "+5511911111111"
_CPF = "15350946056"  # CPF válido para teste


def _cleanup():
	for ap in frappe.get_all("Patient Appointment", filters={"patient_name": ("like", "WPP Teste%")}, pluck="name"):
		try:
			frappe.delete_doc("Patient Appointment", ap, force=True, ignore_permissions=True)
		except Exception:
			pass
	for pat in frappe.get_all("Patient", filters={"first_name": "WPP Teste"}, pluck="name"):
		try:
			frappe.delete_doc("Patient", pat, force=True, ignore_permissions=True)
		except Exception:
			pass
	for ct in frappe.get_all("Contact", filters={"email_id": _EMAIL}, pluck="name"):
		try:
			frappe.delete_doc("Contact", ct, force=True, ignore_permissions=True)
		except Exception:
			pass
	for cust in frappe.get_all("Customer", filters={"customer_name": ("like", "WPP Teste%")}, pluck="name"):
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


class TestFormatVaccineList(FrappeTestCase):
	def test_empty(self):
		self.assertEqual(format_vaccine_list([]), "")
		self.assertEqual(format_vaccine_list([None, "", "  "]), "")

	def test_single(self):
		self.assertEqual(format_vaccine_list(["Gripe"]), "Gripe")

	def test_two(self):
		self.assertEqual(format_vaccine_list(["Gripe", "Meningite B"]), "Gripe e Meningite B")

	def test_three_or_more(self):
		self.assertEqual(
			format_vaccine_list(["Gripe", "Meningite B", "Meningite ACWY"]),
			"Gripe, Meningite B e Meningite ACWY",
		)

	def test_modalidade_label(self):
		self.assertEqual(modalidade_label("Clínica"), "Atendimento CLÍNICA")
		self.assertEqual(modalidade_label("Domiciliar"), "Atendimento DOMICILIAR")
		self.assertEqual(modalidade_label(None), "Atendimento CLÍNICA")


class TestAppointmentWhatsappParams(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()
		_cleanup()
		cls.patient = frappe.get_doc(
			{
				"doctype": "Patient",
				"first_name": "WPP Teste",
				"middle_name": "de",
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

		practitioner = frappe.db.get_value("Healthcare Practitioner", {}, "name")
		appt = frappe.get_doc(
			{
				"doctype": "Patient Appointment",
				"patient": cls.patient,
				"practitioner": practitioner,
				"appointment_date": "2026-05-28",
				"appointment_time": "14:30:00",
				"imun_modalidade": "Domiciliar",
				"imun_vaccines": [
					{"medication": "Influenza Tetravalente", "dose_numero": 1},
					{"medication": "Meningocócica B", "dose_numero": 1},
				],
			}
		)
		appt.insert(ignore_permissions=True, ignore_mandatory=True)
		frappe.db.commit()
		cls.appointment = appt.name

	@classmethod
	def tearDownClass(cls):
		_cleanup()
		super().tearDownClass()

	def test_params_structure(self):
		params = get_appointment_whatsapp_params(self.appointment)
		self.assertEqual(set(params.keys()), {"nome", "vacinas", "data", "hora", "modalidade", "endereco", "pagamento"})

	def test_nome_and_vaccines(self):
		params = get_appointment_whatsapp_params(self.appointment)
		self.assertEqual(params["nome"], "WPP Teste de Silva")
		self.assertEqual(params["vacinas"], "Influenza Tetravalente e Meningocócica B")

	def test_date_time_formatting(self):
		params = get_appointment_whatsapp_params(self.appointment)
		self.assertEqual(params["data"], "28/05/2026")
		self.assertEqual(params["hora"], "14:30")

	def test_modalidade_and_address(self):
		params = get_appointment_whatsapp_params(self.appointment)
		self.assertEqual(params["modalidade"], "Atendimento DOMICILIAR")
		# Sem Address vinculado, endereço domiciliar fica vazio (hook before_save).
		self.assertIsInstance(params["endereco"], str)

	def test_payment_defaults_to_a_pagar(self):
		params = get_appointment_whatsapp_params(self.appointment)
		self.assertEqual(params["pagamento"], "A pagar")
