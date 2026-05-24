"""Geração de cronograma de doses (Fase 5).

Quando um paciente adquire um combo/calendário, gera-se um Medication Request
por dose futura, com ``expected_date`` calculada a partir do esquema biológico
(Therapy Plan Template is_pni + intervalos do Therapy Plan Template Detail).

Os Medication Requests são a fonte do dashboard "Retornos Pendentes" (Fase 6) e
do lembrete de reforço (template HSM 5, Fase 8).

Medication Request tem vários campos mandatory pouco relevantes para vacina
(dosage, dosage_form, practitioner...). Preenchemos defaults sensatos.
"""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe.utils import add_days, getdate, nowdate, nowtime

# Defaults para os campos mandatory do Medication Request no contexto de vacina.
_DEFAULT_DOSAGE = "0-0-1"
_DEFAULT_DOSAGE_FORM = "Injection"
_STATUS_ACTIVE = "active-Request Status"


def gerar_cronograma_doses(
	patient: str,
	therapy_plan_template: str,
	data_inicio: str | None = None,
	practitioner: str | None = None,
	company: str | None = None,
	therapy_plan: str | None = None,
) -> list[str]:
	"""Cria um Medication Request por dose do esquema. Retorna os nomes criados.

	``expected_date`` é acumulativa POR VACINA: para cada vacina, a 1ª dose cai
	em ``data_inicio`` (intervalo 0) e cada dose seguinte soma seu
	``intervalo_dias_min`` à data da dose anterior DA MESMA VACINA. Vacinas
	distintas têm cronogramas independentes (não se somam entre si).
	"""
	data_inicio = getdate(data_inicio or nowdate())
	company = company or _default_company()
	practitioner = practitioner or frappe.db.get_value("Healthcare Practitioner", {}, "name")

	por_vacina: dict[str, list[dict]] = defaultdict(list)
	for dose in _doses_do_esquema(therapy_plan_template):
		por_vacina[dose["medication"]].append(dose)

	criados: list[str] = []
	for medication, doses_vacina in por_vacina.items():
		medication_item = _medication_item(medication)
		data_corrente = data_inicio
		for dose in sorted(doses_vacina, key=lambda d: d["dose_numero"] or 0):
			data_corrente = add_days(data_corrente, dose["intervalo_dias_min"] or 0)
			mr = frappe.get_doc(
				{
					"doctype": "Medication Request",
					"patient": patient,
					"medication": medication,
					"medication_item": medication_item,
					"dose_numero": dose["dose_numero"],
					"therapy_plan": therapy_plan,
					"expected_date": data_corrente,
					"order_date": nowdate(),
					"order_time": nowtime(),
					"status": _STATUS_ACTIVE,
					"dosage": _DEFAULT_DOSAGE,
					"dosage_form": _DEFAULT_DOSAGE_FORM,
					"quantity": 1,
					"company": company,
					"practitioner": practitioner,
				}
			)
			mr.insert(ignore_permissions=True)
			criados.append(mr.name)

	return criados


def _doses_do_esquema(therapy_plan_template: str) -> list[dict]:
	"""Doses (medication, dose_numero, intervalo) de um Therapy Plan Template."""
	rows = frappe.get_all(
		"Therapy Plan Template Detail",
		filters={"parent": therapy_plan_template},
		fields=["medication", "dose_numero", "intervalo_dias_min"],
		order_by="dose_numero",
	)
	return [r for r in rows if r.get("medication")]


def _medication_item(medication: str) -> str | None:
	"""Item vinculado à Medication (Medication Linked Item)."""
	return frappe.db.get_value(
		"Medication Linked Item", {"parent": medication}, "item_code"
	)


def _default_company() -> str | None:
	return frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")
