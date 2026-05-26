"""Testes do Dashboard de Imunização (Fase 10)."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, nowdate

from imunocare_clinic_ext.api.dashboard import (
	_is_pago,
	atrasados_pagos,
	estoque_da_vacina,
	vacinas_em_falta,
)
from imunocare_clinic_ext.install import (
	_NC_ATRASADOS_PAGOS,
	_NC_VACINAS_FALTA,
	_WORKSPACE_NAME,
	install_imunization_customizations,
)
from imunocare_clinic_ext.imunocare_clinic_ext.report.agenda_imunizacao.agenda_imunizacao import (
	_intervalo,
	_situacao,
	_wa_link,
	execute,
)


class TestFase10Dashboard(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()

	# --- registro de objetos no banco -------------------------------------

	def test_number_cards_registrados(self):
		for nc in (_NC_ATRASADOS_PAGOS, _NC_VACINAS_FALTA):
			self.assertTrue(frappe.db.exists("Number Card", nc), f"Number Card ausente: {nc}")

	def test_number_card_custom_tem_metodo(self):
		method = frappe.db.get_value("Number Card", _NC_VACINAS_FALTA, "method")
		self.assertEqual(method, "imunocare_clinic_ext.api.dashboard.vacinas_em_falta")

	def test_workspace_criada(self):
		self.assertTrue(frappe.db.exists("Workspace", _WORKSPACE_NAME))
		ws = frappe.get_doc("Workspace", _WORKSPACE_NAME)
		labels = {s.label for s in ws.shortcuts}
		self.assertIn("Agenda da Semana", labels)
		self.assertIn("Calendário", labels)
		# Calendário reusa a Calendar View NATIVA do Patient Appointment.
		cal = next(s for s in ws.shortcuts if s.label == "Calendário")
		self.assertEqual(cal.doc_view, "Calendar")
		self.assertEqual(cal.link_to, "Patient Appointment")

	def test_workspace_idempotente(self):
		install_imunization_customizations()
		ws = frappe.get_doc("Workspace", _WORKSPACE_NAME)
		# Não duplica shortcuts ao reinstalar.
		self.assertEqual(len([s for s in ws.shortcuts if s.label == "Calendário"]), 1)

	# --- estoque (reuso do Bin) -------------------------------------------

	def test_estoque_vazio_retorna_zero(self):
		self.assertEqual(estoque_da_vacina(None), 0.0)
		self.assertEqual(estoque_da_vacina("__inexistente__"), 0.0)

	def test_kpis_custom_retornam_int(self):
		self.assertIsInstance(vacinas_em_falta(), int)
		self.assertIsInstance(atrasados_pagos(), int)

	# --- lógica pura: pago / situação / whatsapp --------------------------

	def test_is_pago(self):
		self.assertTrue(_is_pago(frappe._dict(invoiced=1)))
		self.assertTrue(_is_pago(frappe._dict(paid_amount=50)))
		self.assertTrue(_is_pago(frappe._dict(ref_sales_invoice="SI-001")))
		self.assertFalse(_is_pago(frappe._dict(invoiced=0, paid_amount=0)))

	def test_situacao_operacional(self):
		hoje = getdate(nowdate())
		ontem = add_days(hoje, -1)
		amanha = add_days(hoje, 1)
		self.assertEqual(_situacao(frappe._dict(status="Open", appointment_date=ontem), hoje), "Atrasado")
		self.assertEqual(_situacao(frappe._dict(status="Open", appointment_date=hoje), hoje), "Hoje")
		self.assertEqual(_situacao(frappe._dict(status="Open", appointment_date=amanha), hoje), "Futuro")
		self.assertEqual(_situacao(frappe._dict(status="Closed", appointment_date=ontem), hoje), "Realizado")
		self.assertEqual(_situacao(frappe._dict(status="Cancelled", appointment_date=ontem), hoje), "Cancelado/Falta")

	def test_wa_link_normaliza_telefone(self):
		link = _wa_link(frappe._dict(mobile="(11) 93333-3333", patient_name="Maria Silva",
									 medication="Gripe", appointment_datetime=nowdate() + " 14:00:00"))
		self.assertIn("https://wa.me/5511933333333", link)
		self.assertIn("Maria", link)

	def test_wa_link_sem_telefone_retorna_none(self):
		self.assertIsNone(_wa_link(frappe._dict(mobile=None)))

	# --- report execute ----------------------------------------------------

	def test_intervalo_presets(self):
		hoje = getdate(nowdate())
		de, ate = _intervalo(frappe._dict(periodo="Hoje"))
		self.assertEqual(de, hoje)
		self.assertEqual(ate, hoje)
		de_s, ate_s = _intervalo(frappe._dict(periodo="Esta semana"))
		self.assertLessEqual(de_s, hoje)
		self.assertGreaterEqual(ate_s, hoje)

	def test_execute_retorna_colunas_e_lista(self):
		columns, data = execute({"periodo": "Este mês"})
		fieldnames = {c["fieldname"] for c in columns}
		for esperado in ("appointment_datetime", "medication", "estoque", "pago", "modalidade", "situacao", "whatsapp"):
			self.assertIn(esperado, fieldnames)
		self.assertIsInstance(data, list)
