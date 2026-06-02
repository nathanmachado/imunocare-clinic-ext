"""Baixa de estoque na aplicação de vacina — fecha o ciclo Fase 10 ↔ 11 ↔ 12.

Quando um Patient Encounter é submetido, cada Drug Prescription de vacina gera um
Stock Entry (Material Issue) de 1 unidade, debitando o depósito do Item. Assim a
Projeção de Estoque (Fase 11) reflete o consumo real e a Sales Invoice da campanha
(Fase 12, ``update_stock=0``) deixa de ser uma promissória.

Princípios (espelham o envio ao RNDS em ``encounter_hooks``):
- **Assíncrono e não-bloqueante**: a baixa roda em job (queue long) após o commit;
  uma falha de estoque (depósito ausente, estoque negativo) loga mas NUNCA impede o
  registro clínico da aplicação.
- **Idempotente por dose**: cada Drug Prescription guarda o Stock Entry em
  ``imun_stock_entry`` e não baixa duas vezes (re-submit/amend são seguros).

Depósito de origem (decisão do projeto): ``Item Default`` da company do encounter →
``Item Default`` de qualquer company → ``Stock Settings.default_warehouse`` → um
depósito não-grupo da company.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import nowdate


def on_encounter_submit(doc, method=None) -> None:
	"""Enfileira a baixa de estoque das vacinas do encounter recém-submetido."""
	for dp in doc.get("drug_prescription") or []:
		if not dp.get("medication") or dp.get("imun_stock_entry"):
			continue
		if not frappe.db.get_value("Medication", dp.medication, "is_vaccine"):
			continue
		frappe.enqueue(
			"imunocare_clinic_ext.stock_immunization.baixar_dose",
			queue="long",
			enqueue_after_commit=True,
			encounter=doc.name,
			dp_name=dp.name,
		)


def baixar_dose(encounter: str, dp_name: str) -> None:
	"""Job: gera o Material Issue de 1 dose e grava o vínculo na Drug Prescription."""
	enc = frappe.get_doc("Patient Encounter", encounter)
	dp = next((d for d in enc.drug_prescription if d.name == dp_name), None)
	if not dp or dp.get("imun_stock_entry") or not dp.get("medication"):
		return
	if not frappe.db.get_value("Medication", dp.medication, "is_vaccine"):
		return

	item_code = _item_code_da_vacina(dp.medication)
	if not item_code:
		return

	warehouse = _warehouse_de_origem(item_code, enc.company)
	if not warehouse:
		frappe.log_error(
			_("Sem depósito de origem para baixar {0} (encounter {1}).").format(item_code, encounter),
			"Imunocare: baixa de estoque",
		)
		return

	se = _criar_material_issue(enc, dp, item_code, warehouse)
	dp.db_set("imun_stock_entry", se.name, update_modified=False)


def _item_code_da_vacina(medication: str) -> str | None:
	return frappe.db.get_value(
		"Medication Linked Item",
		{"parent": medication, "parenttype": "Medication"},
		"item_code",
	)


def _warehouse_de_origem(item_code: str, company: str | None) -> str | None:
	for filtros in ({"parent": item_code, "company": company}, {"parent": item_code}):
		wh = frappe.db.get_value("Item Default", filtros, "default_warehouse")
		if wh:
			return wh
	wh = frappe.db.get_single_value("Stock Settings", "default_warehouse")
	if wh:
		return wh
	return frappe.db.get_value(
		"Warehouse",
		{"company": company, "is_group": 0, "disabled": 0},
		"name",
	)


def _criar_material_issue(enc, dp, item_code: str, warehouse: str):
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Issue"
	se.company = enc.company
	se.set_posting_time = 1
	se.posting_date = enc.encounter_date or nowdate()
	# allow_zero_valuation_rate: o objetivo é a baixa de QUANTIDADE (visão de doses
	# da Fase 11); não travar quando a valoração de custo ainda não está formada.
	se.append("items", {
		"item_code": item_code,
		"qty": 1,
		"s_warehouse": warehouse,
		"allow_zero_valuation_rate": 1,
	})
	se.remarks = _("Aplicação de vacina — Encounter {0} (lote {1}).").format(
		enc.name, dp.get("lote") or "-"
	)
	se.flags.ignore_permissions = True
	se.insert()
	se.submit()
	return se
