"""Testes da baixa de estoque na aplicação de vacina (fecha Fase 10↔11↔12)."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

from imunocare_clinic_ext.install import install_imunization_customizations
from imunocare_clinic_ext.medication_items import item_de_cobranca, item_de_estoque
from imunocare_clinic_ext.stock_immunization import (
	_warehouse_de_origem,
	baixar_dose,
	on_encounter_submit,
)

VACINA = "BCG"
ITEM_VACINA = "imunocare-vacina-bcg"


class TestBaixaEstoque(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()  # semeia o Item/Medication BCG
		# Patient sem customer dispara create_customer (link_customer_to_patient);
		# os defaults precisam ser não-grupo, senão Customer.validate quebra.
		frappe.db.set_single_value(
			"Selling Settings",
			"customer_group",
			frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
		)
		frappe.db.set_single_value(
			"Selling Settings",
			"territory",
			frappe.db.get_value("Territory", {"is_group": 0}, "name"),
		)
		cls.company = frappe.db.get_value("Company", {}, "name")
		cls.customer = _ensure_customer("Cliente Estoque Teste")
		# Recebe o estoque EXATAMENTE no depósito que o código de produção resolve,
		# garantindo qty + valuation onde o Material Issue vai debitar.
		cls.warehouse = _warehouse_de_origem(ITEM_VACINA, cls.company) or _ensure_warehouse(
			cls.company
		)
		make_stock_entry(
			item_code=ITEM_VACINA, to_warehouse=cls.warehouse, qty=50, rate=10, company=cls.company
		)

	def _encounter_com_vacina(self, medication=VACINA, lote="LOTE-A1"):
		paciente = _ensure_patient(self.customer)
		enc = frappe.new_doc("Patient Encounter")
		enc.name = "TEST-ENC-" + frappe.generate_hash(length=8)
		enc.flags.name_set = True
		enc.patient = paciente
		enc.company = self.company
		enc.encounter_date = nowdate()
		enc.db_insert()

		dp = frappe.new_doc("Drug Prescription")
		dp.parent = enc.name
		dp.parenttype = "Patient Encounter"
		dp.parentfield = "drug_prescription"
		dp.idx = 1
		dp.medication = medication
		dp.dose_numero = 1
		dp.lote = lote
		dp.db_insert()
		return enc, dp

	def _bin_atual(self):
		return frappe.db.get_value(
			"Bin", {"item_code": ITEM_VACINA, "warehouse": self.warehouse}, "actual_qty"
		) or 0

	# --- caminho feliz ------------------------------------------------------

	def test_baixa_gera_material_issue_e_reduz_bin(self):
		antes = self._bin_atual()
		enc, dp = self._encounter_com_vacina()

		baixar_dose(enc.name, dp.name)

		se_name = frappe.db.get_value("Drug Prescription", dp.name, "imun_stock_entry")
		self.assertTrue(se_name, "imun_stock_entry não foi gravado")
		se = frappe.get_doc("Stock Entry", se_name)
		self.assertEqual(se.stock_entry_type, "Material Issue")
		self.assertEqual(se.docstatus, 1)
		self.assertEqual(len(se.items), 1)
		self.assertEqual(se.items[0].item_code, ITEM_VACINA)
		self.assertEqual(se.items[0].qty, 1)
		self.assertEqual(se.items[0].s_warehouse, self.warehouse)
		self.assertEqual(self._bin_atual(), antes - 1)

	# --- idempotência -------------------------------------------------------

	def test_idempotente_nao_baixa_duas_vezes(self):
		enc, dp = self._encounter_com_vacina(lote="LOTE-B2")
		baixar_dose(enc.name, dp.name)
		se1 = frappe.db.get_value("Drug Prescription", dp.name, "imun_stock_entry")
		bin_apos_1 = self._bin_atual()

		baixar_dose(enc.name, dp.name)  # segunda chamada não deve baixar de novo
		se2 = frappe.db.get_value("Drug Prescription", dp.name, "imun_stock_entry")
		self.assertEqual(se1, se2)
		self.assertEqual(self._bin_atual(), bin_apos_1)

	# --- guardas ------------------------------------------------------------

	def test_medicamento_nao_vacina_e_ignorado(self):
		med = _ensure_medication_nao_vacina()
		antes = self._bin_atual()
		enc, dp = self._encounter_com_vacina(medication=med)
		baixar_dose(enc.name, dp.name)
		self.assertFalse(frappe.db.get_value("Drug Prescription", dp.name, "imun_stock_entry"))
		self.assertEqual(self._bin_atual(), antes)

	def test_on_submit_nao_quebra_sem_vacinas(self):
		enc = frappe.new_doc("Patient Encounter")
		enc.name = "TEST-ENC-" + frappe.generate_hash(length=8)
		enc.flags.name_set = True
		enc.patient = _ensure_patient(self.customer)
		enc.company = self.company
		enc.encounter_date = nowdate()
		enc.db_insert()
		on_encounter_submit(enc)  # sem drug_prescription: não deve levantar

	# --- resolução de depósito ---------------------------------------------

	def test_warehouse_de_origem_usa_item_default(self):
		self.assertEqual(_warehouse_de_origem(ITEM_VACINA, self.company), self.warehouse)


class TestBaixaPorLote(FrappeTestCase):
	"""Modelo 2026-06-06: insumo lotado (has_batch_no) + item de serviço.

	A baixa usa o lote registrado na prescrição; sem casar, FIFO por validade.
	"""

	INSUMO = "imun-test-vac-lotada"
	SERVICO = "imun-test-aplic-lotada"
	MED = "Vacina Lotada Teste"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()
		frappe.db.set_single_value(
			"Selling Settings", "customer_group",
			frappe.db.get_value("Customer Group", {"is_group": 0}, "name"))
		frappe.db.set_single_value(
			"Selling Settings", "territory",
			frappe.db.get_value("Territory", {"is_group": 0}, "name"))
		cls.company = frappe.db.get_value("Company", {}, "name")
		cls.customer = _ensure_customer("Cliente Estoque Teste")
		cls.warehouse = _ensure_warehouse(cls.company)
		_ensure_item_lotado(cls.INSUMO, cls.company, cls.warehouse)
		_ensure_item_servico(cls.SERVICO)
		_ensure_medication_vacina(cls.MED, [cls.INSUMO, cls.SERVICO])
		# dois lotes: o que vence primeiro NÃO é o da prescrição
		cls.lote_vence_antes = _receber_lote(
			cls.INSUMO, cls.warehouse, cls.company, "LT-VENCE-ANTES", "2026-12-31", 5)
		cls.lote_prescrito = _receber_lote(
			cls.INSUMO, cls.warehouse, cls.company, "LT-PRESCRITO", "2027-12-31", 5)

	def _encounter(self, lote):
		paciente = _ensure_patient(self.customer)
		enc = frappe.new_doc("Patient Encounter")
		enc.name = "TEST-ENC-" + frappe.generate_hash(length=8)
		enc.flags.name_set = True
		enc.patient = paciente
		enc.company = self.company
		enc.encounter_date = nowdate()
		enc.db_insert()
		dp = frappe.new_doc("Drug Prescription")
		dp.parent = enc.name
		dp.parenttype = "Patient Encounter"
		dp.parentfield = "drug_prescription"
		dp.idx = 1
		dp.medication = self.MED
		dp.dose_numero = 1
		dp.lote = lote
		dp.db_insert()
		return enc, dp

	def _se_da_dose(self, dp):
		se_name = frappe.db.get_value("Drug Prescription", dp.name, "imun_stock_entry")
		self.assertTrue(se_name, "baixa não aconteceu")
		return frappe.get_doc("Stock Entry", se_name)

	def test_resolucao_insumo_vs_cobranca(self):
		self.assertEqual(item_de_estoque(self.MED), self.INSUMO)
		self.assertEqual(item_de_cobranca(self.MED), self.SERVICO)

	def test_baixa_usa_lote_da_prescricao(self):
		enc, dp = self._encounter(lote="LT-PRESCRITO")
		baixar_dose(enc.name, dp.name)
		se = self._se_da_dose(dp)
		self.assertEqual(se.items[0].item_code, self.INSUMO)
		self.assertEqual(se.items[0].batch_no, self.lote_prescrito)

	def test_baixa_sem_lote_cai_para_fifo_por_validade(self):
		enc, dp = self._encounter(lote="LOTE-QUE-NAO-EXISTE")
		baixar_dose(enc.name, dp.name)
		se = self._se_da_dose(dp)
		self.assertEqual(se.items[0].batch_no, self.lote_vence_antes)

	def test_sem_saldo_em_lote_nao_baixa_nem_quebra(self):
		# item lotado sem NENHUM recebimento → loga e não cria Stock Entry
		_ensure_item_lotado("imun-test-vac-sem-saldo", self.company, self.warehouse)
		_ensure_medication_vacina("Vacina Sem Saldo Teste", ["imun-test-vac-sem-saldo"])
		paciente = _ensure_patient(self.customer)
		enc = frappe.new_doc("Patient Encounter")
		enc.name = "TEST-ENC-" + frappe.generate_hash(length=8)
		enc.flags.name_set = True
		enc.patient = paciente
		enc.company = self.company
		enc.encounter_date = nowdate()
		enc.db_insert()
		dp = frappe.new_doc("Drug Prescription")
		dp.parent = enc.name
		dp.parenttype = "Patient Encounter"
		dp.parentfield = "drug_prescription"
		dp.idx = 1
		dp.medication = "Vacina Sem Saldo Teste"
		dp.dose_numero = 1
		dp.db_insert()
		baixar_dose(enc.name, dp.name)
		self.assertFalse(frappe.db.get_value("Drug Prescription", dp.name, "imun_stock_entry"))


class TestInsumoNaoFaturavelPermaneceAtivo(FrappeTestCase):
	"""O on_update nativo do Medication desativa toda linha não-faturável; o hook
	imunocare (medication_hooks) reabilita o insumo (item de estoque) — senão ele
	some do De-Para da NF-e e trava entrada/baixa (item disabled não transaciona)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_imunization_customizations()
		cls.company = frappe.db.get_value("Company", {}, "name")
		cls.warehouse = _ensure_warehouse(cls.company)

	def test_insumo_nao_faturavel_continua_ativo_apos_insert(self):
		insumo = _ensure_item_lotado("imun-test-insumo-ativo", self.company, self.warehouse)
		servico = _ensure_item_servico("imun-test-servico-ativo")
		_medication_com_billable(
			"Vacina Insumo Ativo Teste", [(insumo, 0), (servico, 1)])  # insumo NÃO faturável
		self.assertFalse(
			frappe.db.get_value("Item", insumo, "disabled"),
			"insumo não-faturável foi desativado pelo Medication nativo")
		self.assertFalse(frappe.db.get_value("Item", servico, "disabled"))

	def test_reabilita_a_cada_save(self):
		insumo = _ensure_item_lotado("imun-test-insumo-resave", self.company, self.warehouse)
		nome = _medication_com_billable("Vacina Resave Teste", [(insumo, 0)])
		# simula um novo save do Medication (cenário real: editar o cadastro)
		frappe.db.set_value("Item", insumo, "disabled", 1)
		med = frappe.get_doc("Medication", nome)
		med.flags.ignore_mandatory = True
		med.save(ignore_permissions=True)
		self.assertFalse(frappe.db.get_value("Item", insumo, "disabled"))


def _ensure_item_lotado(code: str, company: str, warehouse: str) -> str:
	if not frappe.db.exists("Item", code):
		frappe.get_doc({
			"doctype": "Item", "item_code": code, "item_name": code,
			"item_group": "All Item Groups", "stock_uom": "Unidade",
			"is_stock_item": 1, "is_sales_item": 0, "has_batch_no": 1,
			"item_defaults": [{"company": company, "default_warehouse": warehouse}],
		}).insert(ignore_permissions=True)
	return code


def _ensure_item_servico(code: str) -> str:
	if not frappe.db.exists("Item", code):
		frappe.get_doc({
			"doctype": "Item", "item_code": code, "item_name": code,
			"item_group": "All Item Groups", "stock_uom": "Unidade",
			"is_stock_item": 0, "is_sales_item": 1,
		}).insert(ignore_permissions=True)
	return code


def _ensure_medication_vacina(nome: str, item_codes: list[str]) -> str:
	if frappe.db.exists("Medication", nome):
		return nome
	m = frappe.new_doc("Medication")
	m.generic_name = nome
	m.is_vaccine = 1
	for code in item_codes:
		m.append("linked_items", {
			"item_code": code, "item_group": "All Item Groups", "stock_uom": "Unidade",
		})
	m.flags.ignore_mandatory = True
	m.insert(ignore_permissions=True)
	return m.name


def _medication_com_billable(nome: str, rows: list[tuple[str, int]]) -> str:
	"""Cria Medication com is_billable controlado por linha. rows = [(item_code, is_billable), ...]."""
	if frappe.db.exists("Medication", nome):
		return nome
	m = frappe.new_doc("Medication")
	m.generic_name = nome
	m.is_vaccine = 1
	for code, billable in rows:
		m.append("linked_items", {
			"item_code": code, "item_group": "All Item Groups",
			"stock_uom": "Unidade", "is_billable": billable,
		})
	m.flags.ignore_mandatory = True
	m.insert(ignore_permissions=True)
	return m.name


def _receber_lote(item: str, warehouse: str, company: str, lote: str, validade: str, qty: float) -> str:
	batch = frappe.db.get_value("Batch", {"item": item, "batch_id": lote}, "name")
	if not batch:
		batch = frappe.get_doc({
			"doctype": "Batch", "item": item, "batch_id": lote, "expiry_date": validade,
		}).insert(ignore_permissions=True).name
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Receipt"
	se.company = company
	se.append("items", {
		"item_code": item, "qty": qty, "t_warehouse": warehouse, "basic_rate": 10,
		"use_serial_batch_fields": 1, "batch_no": batch,
	})
	se.flags.ignore_permissions = True
	se.insert()
	se.submit()
	return batch


def _ensure_warehouse(company: str) -> str:
	existente = frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 0, "disabled": 0}, "name"
	)
	if existente:
		return existente
	abbr = frappe.db.get_value("Company", company, "abbr")
	wh = frappe.new_doc("Warehouse")
	wh.warehouse_name = "Estoque Vacinas Teste"
	wh.company = company
	wh.insert(ignore_permissions=True)
	return wh.name


def _ensure_customer(nome: str) -> str:
	existente = frappe.db.get_value("Customer", {"customer_name": nome}, "name")
	if existente:
		return existente
	c = frappe.new_doc("Customer")
	c.customer_name = nome
	c.customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
	c.territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
	c.insert(ignore_permissions=True)
	return c.name


def _ensure_patient(customer: str) -> str:
	existente = frappe.db.get_value("Patient", {"first_name": "Paciente Estoque Teste"}, "name")
	if existente:
		return existente
	p = frappe.new_doc("Patient")
	p.first_name = "Paciente Estoque Teste"
	p.customer = customer  # evita o auto-create de Customer (link_customer_to_patient)
	p.flags.ignore_mandatory = True
	p.insert(ignore_permissions=True)
	return p.name


def _ensure_medication_nao_vacina() -> str:
	nome = "Dipirona Teste"
	if frappe.db.exists("Medication", nome):
		return nome
	m = frappe.new_doc("Medication")
	m.generic_name = nome
	m.is_vaccine = 0
	m.flags.ignore_mandatory = True
	m.insert(ignore_permissions=True)
	return m.name
