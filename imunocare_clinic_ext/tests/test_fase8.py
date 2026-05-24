from __future__ import annotations

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_months, nowdate

from imunocare_clinic_ext.dispatch import (
	TEMPLATE_SPECS,
	enfileirar_para_appointment,
)
from imunocare_clinic_ext.install import install_imunization_customizations

_EMAIL = "disparo.teste@example.com"
_MOBILE = "+5511944440000"
_CPF = "73862347087"  # CPF válido para teste


def _cleanup():
	for wd in frappe.get_all("WhatsApp Dispatch", filters={"to": _MOBILE}, pluck="name"):
		try:
			frappe.delete_doc("WhatsApp Dispatch", wd, force=True, ignore_permissions=True)
		except Exception:
			pass
	for ap in frappe.get_all("Patient Appointment", filters={"patient_name": ("like", "Disparo Teste%")}, pluck="name"):
		try:
			frappe.delete_doc("Patient Appointment", ap, force=True, ignore_permissions=True)
		except Exception:
			pass
	for pat in frappe.get_all("Patient", filters={"first_name": "Disparo Teste"}, pluck="name"):
		try:
			frappe.delete_doc("Patient", pat, force=True, ignore_permissions=True)
		except Exception:
			pass
	for ct in frappe.get_all("Contact", filters={"email_id": _EMAIL}, pluck="name"):
		try:
			frappe.delete_doc("Contact", ct, force=True, ignore_permissions=True)
		except Exception:
			pass
	for cust in frappe.get_all("Customer", filters={"customer_name": ("like", "Disparo Teste%")}, pluck="name"):
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


class TestDispatchQueue(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()
		_cleanup()
		cls.patient = frappe.get_doc(
			{
				"doctype": "Patient", "first_name": "Disparo Teste", "middle_name": "de",
				"last_name": "Lima", "sex": "Male", "dob": add_months(nowdate(), -30 * 12),
				"mobile": _MOBILE, "email": _EMAIL, "cpf": _CPF,
				"pais_nascimento": "Brazil", "cidade_nascimento": "Uberlândia",
				"customer_group": "Pessoa Física",
			}
		).insert(ignore_permissions=True).name
		practitioner = frappe.db.get_value("Healthcare Practitioner", {}, "name")
		cls.appt = frappe.get_doc(
			{
				"doctype": "Patient Appointment", "patient": cls.patient, "practitioner": practitioner,
				"appointment_date": "2026-06-10", "appointment_time": "09:00:00",
				"imun_modalidade": "Clínica",
				"imun_vaccines": [{"medication": "Influenza Tetravalente", "dose_numero": 1}],
			}
		).insert(ignore_permissions=True, ignore_mandatory=True).name
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		_cleanup()
		super().tearDownClass()

	def _dispatch_for(self, template_key):
		# Filtra por 'to' (mobile único desta classe) em vez de reference_name:
		# o rollback transacional entre classes de teste pode reciclar o name do
		# Patient Appointment, colidindo com dispatches de outros módulos.
		name = frappe.db.get_value(
			"WhatsApp Dispatch",
			{"to": _MOBILE, "template_key": template_key},
			"name",
		)
		return frappe.get_doc("WhatsApp Dispatch", name) if name else None

	def test_appointment_insert_enqueues_confirmation(self):
		# after_insert do appointment já criou a confirmação (status Pendente).
		wd = self._dispatch_for("Confirmação de agendamento")
		self.assertIsNotNone(wd)
		self.assertEqual(wd.status, "Pendente")
		self.assertEqual(wd.to, _MOBILE)
		self.assertEqual(wd.template, "confirmacao_agendamento-pt_BR")

	def test_body_param_order(self):
		wd = self._dispatch_for("Confirmação de agendamento")
		params = json.loads(wd.body_param)
		# 7 variáveis na ordem; {{1}} = nome
		self.assertEqual(params["1"], "Disparo Teste de Lima")
		self.assertEqual(params["2"], "Influenza Tetravalente")
		self.assertEqual(params["3"], "10/06/2026")
		self.assertEqual(params["5"], "Atendimento CLÍNICA")

	def test_preview_rendered(self):
		wd = self._dispatch_for("Confirmação de agendamento")
		self.assertIn("Disparo Teste de Lima", wd.preview)
		self.assertIn("Influenza Tetravalente", wd.preview)
		self.assertIn("Atendimento CLÍNICA", wd.preview)

	def test_idempotent_enqueue(self):
		# Enfileirar de novo não duplica (já existe Pendente).
		before = frappe.db.count("WhatsApp Dispatch", {"reference_name": self.appt, "template_key": "Confirmação de agendamento"})
		enfileirar_para_appointment(self.appt, "Confirmação de agendamento")
		after = frappe.db.count("WhatsApp Dispatch", {"reference_name": self.appt, "template_key": "Confirmação de agendamento"})
		self.assertEqual(before, after)

	def test_cancelar(self):
		wd = self._dispatch_for("Confirmação de agendamento")
		wd.cancelar()
		self.assertEqual(wd.status, "Cancelado")
		# Após cancelar, pode reenfileirar.
		novo = enfileirar_para_appointment(self.appt, "Confirmação de agendamento")
		self.assertIsNotNone(novo)
		frappe.delete_doc("WhatsApp Dispatch", novo, force=True, ignore_permissions=True)
		# Restaura o original para Pendente (isola de outros testes da classe).
		wd.db_set("status", "Pendente")

	def test_template_specs_cover_all(self):
		# Todos os template_key do Select têm spec.
		for key in ("Confirmação de agendamento", "Lembrete (D-1)", "Reagendamento", "Lembrete de reforço"):
			self.assertIn(key, TEMPLATE_SPECS)

	def test_authorize_only_pending(self):
		wd = self._dispatch_for("Confirmação de agendamento")
		wd.db_set("status", "Enviado")
		with self.assertRaises(frappe.ValidationError):
			wd.autorizar_e_enviar()
		wd.db_set("status", "Pendente")
