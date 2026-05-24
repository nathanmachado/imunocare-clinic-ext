"""Report Retornos Pendentes (Fase 6).

Lista as doses pendentes de retorno do paciente a partir dos Medication Requests
(Fase 5): doses não finalizadas com ``expected_date`` vencida ou próxima. Mostra
dias de atraso, situação e status de faturamento, para a operação cobrar o
retorno proativamente.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, nowdate

# Status FHIR que indicam dose já encerrada — não são "pendentes".
STATUS_FINALIZADOS = (
	"completed-Request Status",
	"revoked-Request Status",
	"entered-in-error-Request Status",
	"unknown-Request Status",
)


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})
	return _columns(), _data(filters)


def _columns() -> list[dict]:
	return [
		{"label": _("Paciente"), "fieldname": "patient", "fieldtype": "Link", "options": "Patient", "width": 130},
		{"label": _("Nome"), "fieldname": "patient_name", "fieldtype": "Data", "width": 160},
		{"label": _("Celular"), "fieldname": "mobile", "fieldtype": "Data", "width": 120},
		{"label": _("Vacina"), "fieldname": "medication", "fieldtype": "Link", "options": "Medication", "width": 150},
		{"label": _("Dose"), "fieldname": "dose_numero", "fieldtype": "Int", "width": 60},
		{"label": _("Data prevista"), "fieldname": "expected_date", "fieldtype": "Date", "width": 110},
		{"label": _("Dias de atraso"), "fieldname": "dias_atraso", "fieldtype": "Int", "width": 110},
		{"label": _("Situação"), "fieldname": "situacao", "fieldtype": "Data", "width": 150},
		{"label": _("Faturamento"), "fieldname": "billing_status", "fieldtype": "Data", "width": 110},
		{"label": _("Med. Request"), "fieldname": "name", "fieldtype": "Link", "options": "Medication Request", "width": 130},
	]


def _data(filters: frappe._dict) -> list[dict]:
	dias_antecedencia = int(filters.get("dias_antecedencia") or 7)
	hoje = nowdate()
	limite = add_days(hoje, dias_antecedencia)

	conditions = ["mr.docstatus < 2", "mr.status NOT IN %(finalizados)s"]
	values = {"finalizados": STATUS_FINALIZADOS, "limite": limite, "hoje": hoje}

	if filters.get("apenas_atrasadas"):
		conditions.append("mr.expected_date < %(hoje)s")
	else:
		conditions.append("mr.expected_date <= %(limite)s")

	if filters.get("patient"):
		conditions.append("mr.patient = %(patient)s")
		values["patient"] = filters.get("patient")

	rows = frappe.db.sql(
		f"""
		SELECT
			mr.name, mr.patient, mr.patient_name, p.mobile,
			mr.medication, mr.dose_numero, mr.expected_date, mr.billing_status
		FROM `tabMedication Request` mr
		LEFT JOIN `tabPatient` p ON mr.patient = p.name
		WHERE {" AND ".join(conditions)}
		ORDER BY mr.expected_date ASC
		""",
		values,
		as_dict=True,
	)

	for row in rows:
		dias = date_diff(hoje, row["expected_date"]) if row.get("expected_date") else 0
		row["dias_atraso"] = dias
		row["situacao"] = _situacao(dias)
	return rows


def _situacao(dias_atraso: int) -> str:
	if dias_atraso > 0:
		return _("Atrasada ({0} dias)").format(dias_atraso)
	if dias_atraso == 0:
		return _("Vence hoje")
	return _("Vence em {0} dias").format(abs(dias_atraso))
