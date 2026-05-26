"""Testes da Projeção de Estoque de Vacinas (Fase 11)."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate, nowdate

from imunocare_clinic_ext.api.dashboard import (
	_MESES_PT,
	_meses_horizonte,
	posicao_estoque,
	projetar_estoque,
	vacinas_a_repor,
)
from imunocare_clinic_ext.install import (
	_NC_VACINAS_REPOR,
	_REPORT_PROJECAO,
	_WORKSPACE_NAME,
	install_imunization_customizations,
)
from imunocare_clinic_ext.imunocare_clinic_ext.report.projeção_de_estoque_de_vacinas.projeção_de_estoque_de_vacinas import (
	_columns,
	execute,
)


class TestFase11Projecao(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()

	# --- registro -----------------------------------------------------------

	def test_number_card_repor_registrado(self):
		self.assertTrue(frappe.db.exists("Number Card", _NC_VACINAS_REPOR))
		method = frappe.db.get_value("Number Card", _NC_VACINAS_REPOR, "method")
		self.assertEqual(method, "imunocare_clinic_ext.api.dashboard.vacinas_a_repor")

	def test_report_registrado(self):
		self.assertTrue(frappe.db.exists("Report", _REPORT_PROJECAO))
		self.assertEqual(
			frappe.db.get_value("Report", _REPORT_PROJECAO, "report_type"), "Script Report"
		)

	def test_workspace_tem_shortcut_projecao(self):
		ws = frappe.get_doc("Workspace", _WORKSPACE_NAME)
		labels = {s.label for s in ws.shortcuts}
		self.assertIn("Projeção de Estoque", labels)

	# --- horizonte de meses (pura) ------------------------------------------

	def test_meses_horizonte_tamanho_e_rotulos(self):
		h = _meses_horizonte(3)
		self.assertEqual(len(h), 3)
		hoje = getdate(nowdate())
		# primeiro mês é o corrente
		self.assertEqual(h[0][0], hoje.year)
		self.assertEqual(h[0][1], hoje.month)
		# rótulo no formato "Mmm/AA"
		self.assertTrue(h[0][2].startswith(_MESES_PT[hoje.month]))

	def test_meses_horizonte_vira_o_ano(self):
		# Dezembro + 2 meses → Dez, Jan(+1), Fev(+1)
		h = _meses_horizonte(24)
		anos = {y for y, _m, _r in h}
		self.assertGreaterEqual(len(anos), 2)  # cobre virada de ano

	# --- posição de estoque (reuso do Bin) ----------------------------------

	def test_posicao_estoque_vazia(self):
		self.assertEqual(posicao_estoque(None), {"actual": 0.0, "ordered": 0.0})
		self.assertEqual(posicao_estoque("__inexistente__"), {"actual": 0.0, "ordered": 0.0})

	# --- projeção -----------------------------------------------------------

	def test_projetar_estoque_estrutura(self):
		proj = projetar_estoque(meses=3)
		self.assertIn("meses", proj)
		self.assertIn("linhas", proj)
		self.assertEqual(len(proj["meses"]), 3)
		# Cada linha tem um saldo por mês e os agregados.
		for l in proj["linhas"]:
			self.assertEqual(len(l["saldos"]), 3)
			for chave in ("medication", "estoque", "em_pedido", "demanda_total", "repor"):
				self.assertIn(chave, l)
			# repor nunca negativo
			self.assertGreaterEqual(l["repor"], 0)
			# saldo final = inicial - demanda; repor cobre exatamente o déficit final
			self.assertAlmostEqual(l["repor"], max(0.0, -l["saldos"][-1]))

	def test_projetar_ordenado_por_repor_desc(self):
		linhas = projetar_estoque(meses=3)["linhas"]
		repores = [l["repor"] for l in linhas]
		self.assertEqual(repores, sorted(repores, reverse=True))

	def test_vacinas_a_repor_int(self):
		self.assertIsInstance(vacinas_a_repor(), int)
		self.assertGreaterEqual(vacinas_a_repor(), 0)

	# --- colunas do report --------------------------------------------------

	def test_columns_dinamicas_por_mes(self):
		cols = _columns(["Mai/26", "Jun/26", "Jul/26"])
		fieldnames = [c["fieldname"] for c in cols]
		# Vacina + Estoque + Em pedido + 3 saldos + Demanda + Repor = 8
		self.assertEqual(len(cols), 8)
		self.assertIn("saldo_0", fieldnames)
		self.assertIn("saldo_2", fieldnames)
		self.assertEqual(cols[3]["label"], "Mai/26")

	def test_execute_retorna_colunas_e_lista(self):
		columns, data = execute({"meses": 3})
		fieldnames = {c["fieldname"] for c in columns}
		for esperado in ("medication", "estoque", "em_pedido", "demanda_total", "repor", "saldo_0"):
			self.assertIn(esperado, fieldnames)
		self.assertIsInstance(data, list)
