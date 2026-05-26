"""Report Fechamento de Campanha (Fase 12, ver ADR-0002).

Uma linha por dose aplicada numa campanha corporativa: empresa, colaborador,
vacina, dose, data e valor (Item Price da tabela da campanha). Responde aos três
números do fechamento: quantas doses, quais colaboradores e quanto faturar
(total da coluna Valor).

Reuso: parte dos Patient Appointments marcados com ``imun_campaign`` + child
``imun_vaccines`` + preço via ``_preco_da_vacina`` (Item Price nativo).
"""

from __future__ import annotations

from frappe import _

from imunocare_clinic_ext.imunocare_clinic_ext.doctype.imunocare_vaccination_campaign.imunocare_vaccination_campaign import (
	_preco_da_vacina,
)
import frappe

_STATUS_FORA = ("Cancelled",)


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})
	return _columns(), _data(filters)


def _columns() -> list[dict]:
	return [
		{"label": _("Campanha"), "fieldname": "campaign", "fieldtype": "Link", "options": "Imunocare Vaccination Campaign", "width": 140},
		{"label": _("Empresa"), "fieldname": "empresa", "fieldtype": "Link", "options": "Customer", "width": 180},
		{"label": _("Colaborador"), "fieldname": "patient", "fieldtype": "Link", "options": "Patient", "width": 200},
		{"label": _("Vacina"), "fieldname": "medication", "fieldtype": "Link", "options": "Medication", "width": 180},
		{"label": _("Dose"), "fieldname": "dose_numero", "fieldtype": "Int", "width": 70},
		{"label": _("Data"), "fieldname": "appointment_date", "fieldtype": "Date", "width": 100},
		{"label": _("Valor"), "fieldname": "valor", "fieldtype": "Currency", "width": 110},
		{"label": _("Atendimento"), "fieldname": "appointment", "fieldtype": "Link", "options": "Patient Appointment", "width": 140},
	]


def _data(filters: frappe._dict) -> list[dict]:
	conditions = ["pa.imun_campaign IS NOT NULL", "pa.imun_campaign != ''", "pa.status NOT IN %(fora)s"]
	values = {"fora": _STATUS_FORA}
	if filters.get("campaign"):
		conditions.append("pa.imun_campaign = %(campaign)s")
		values["campaign"] = filters.get("campaign")
	if filters.get("empresa"):
		conditions.append("c.empresa = %(empresa)s")
		values["empresa"] = filters.get("empresa")

	rows = frappe.db.sql(
		f"""
		SELECT pa.imun_campaign AS campaign, c.empresa, c.price_list,
			pa.patient, pa.appointment_date, pa.name AS appointment,
			v.medication, v.dose_numero
		FROM `tabPatient Appointment` pa
		INNER JOIN `tabImunocare Appointment Vaccine` v
			ON v.parent = pa.name AND v.parenttype = 'Patient Appointment'
		INNER JOIN `tabImunocare Vaccination Campaign` c ON c.name = pa.imun_campaign
		WHERE {" AND ".join(conditions)}
		ORDER BY c.empresa, pa.imun_campaign, pa.patient, v.medication
		""",
		values,
		as_dict=True,
	)

	preco_cache: dict[tuple, float] = {}
	for r in rows:
		chave = (r.medication, r.price_list)
		if chave not in preco_cache:
			preco_cache[chave] = _preco_da_vacina(r.medication, r.price_list)
		r["valor"] = preco_cache[chave]
		r.pop("price_list", None)
	return rows
