"""APIs de apoio ao Dashboard de Imunização (Fase 10).

Reuso máximo do que já existe (ver feedback_reuse_first):
- estoque vem do ``Bin`` nativo (ERPNext Stock) via os ``linked_items`` do
  Medication (Healthcare) — não criamos controle de estoque próprio;
- "pago" é derivado dos campos nativos do Patient Appointment
  (``invoiced`` / ``paid_amount`` / ``ref_sales_invoice``);
- "atrasado" reusa a mesma noção operacional do report Agenda de Imunização.

Estas funções alimentam Number Cards (tipo Custom) e o Script Report, todos
armazenados no banco — sem build de assets.
"""

from __future__ import annotations

import frappe
from frappe.utils import nowdate

# Status do Patient Appointment que indicam atendimento já realizado.
STATUS_REALIZADO = ("Closed", "Checked Out")
# Status que tiram o agendamento da fila (não contam como atraso operacional).
STATUS_ENCERRADO = ("Cancelled", "No Show")


def estoque_da_vacina(medication: str | None) -> float:
	"""Soma do estoque (Bin.actual_qty) dos itens vinculados a uma vacina.

	Medication (Healthcare) → ``linked_items`` → Item estocável → soma das
	posições de estoque em todos os depósitos. Retorna 0 se a vacina não tiver
	item vinculado ou não houver Bin.
	"""
	if not medication:
		return 0.0

	item_codes = frappe.get_all(
		"Medication Linked Item",
		filters={"parent": medication, "parenttype": "Medication"},
		pluck="item_code",
	)
	item_codes = [c for c in item_codes if c]
	if not item_codes:
		return 0.0

	res = frappe.get_all(
		"Bin",
		filters={"item_code": ("in", item_codes)},
		fields=["sum(actual_qty) as qty"],
	)
	return float(res[0].qty or 0) if res else 0.0


def _vacinas_em_falta_codes() -> list[str]:
	"""Medications marcadas como vacina cujo estoque somado é <= 0."""
	vacinas = frappe.get_all(
		"Medication",
		filters={"is_vaccine": 1, "disabled": 0},
		pluck="name",
	)
	return [v for v in vacinas if estoque_da_vacina(v) <= 0]


@frappe.whitelist()
def vacinas_em_falta() -> int:
	"""Number Card (Custom): nº de vacinas ativas com estoque zerado/negativo."""
	return len(_vacinas_em_falta_codes())


@frappe.whitelist()
def atrasados_pagos() -> int:
	"""Number Card (Custom): agendamentos PAGOS, vencidos e não realizados.

	É o alerta crítico da operação: o paciente pagou pela aplicação mas o
	atendimento ficou para trás (data passada e status ainda em aberto).
	"""
	hoje = nowdate()
	rows = frappe.get_all(
		"Patient Appointment",
		filters={
			"appointment_date": ("<", hoje),
			"status": ("not in", STATUS_REALIZADO + STATUS_ENCERRADO),
		},
		fields=["name", "invoiced", "paid_amount", "ref_sales_invoice"],
	)
	return sum(1 for r in rows if _is_pago(r))


def _is_pago(row) -> bool:
	"""Pago = faturado, ou com valor recebido, ou com fatura de venda vinculada."""
	return bool(row.get("invoiced") or (row.get("paid_amount") or 0) > 0 or row.get("ref_sales_invoice"))
