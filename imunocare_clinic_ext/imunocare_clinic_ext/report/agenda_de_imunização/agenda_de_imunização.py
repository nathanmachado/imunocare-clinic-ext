"""Report Agenda de Imunização (Fase 10).

Resumo operacional dos atendimentos de vacinação num horizonte de datas
(Hoje / Esta semana / Este mês / Personalizado). Uma linha por vacina de cada
Patient Appointment, com: paciente, vacina, dose, estoque da vacina, se está
pago, modalidade (Clínica/Domiciliar), endereço, situação operacional e um
botão de Atendimento que abre a comunicação com o paciente via Lead no CRM.

Reuso (ver feedback_reuse_first): parte do Patient Appointment nativo + child
``imun_vaccines`` (Imunocare Appointment Vaccine), estoque do ``Bin`` via
``imunocare_clinic_ext.api.dashboard.estoque_da_vacina`` e "pago" dos campos
nativos do appointment. Nada de controle paralelo.

A renderização (cores, botão Atendimento→CRM, presets de data, largura total)
fica no ``agenda_de_imunização.js`` — em arquivo do app, carregado em runtime,
sem build de assets.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import get_first_day, get_last_day, getdate, nowdate

from imunocare_clinic_ext.api.dashboard import (
	STATUS_CANCELADO,
	STATUS_REALIZADO,
	_is_pago,
	estoque_da_vacina,
)


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})
	de, ate = _intervalo(filters)
	return _columns(), _data(filters, de, ate)


def _intervalo(filters: frappe._dict) -> tuple[str, str]:
	"""Resolve o intervalo de datas a partir do preset ``periodo``.

	``Personalizado`` usa ``from_date``/``to_date``. ``Esta semana`` vai de
	segunda a domingo da semana corrente.
	"""
	hoje = getdate(nowdate())
	periodo = filters.get("periodo") or "Esta semana"

	if periodo == "Personalizado" and filters.get("from_date"):
		return filters.get("from_date"), filters.get("to_date") or filters.get("from_date")
	if periodo == "Hoje":
		return hoje, hoje
	if periodo == "Este mês":
		return get_first_day(hoje), get_last_day(hoje)
	# Esta semana (default): segunda a domingo.
	inicio = frappe.utils.add_days(hoje, -hoje.weekday())
	return inicio, frappe.utils.add_days(inicio, 6)


def _columns() -> list[dict]:
	return [
		{"label": _("Data/Hora"), "fieldname": "appointment_datetime", "fieldtype": "Datetime", "width": 150},
		{"label": _("Paciente"), "fieldname": "patient", "fieldtype": "Link", "options": "Patient", "width": 200},
		{"label": _("Vacina"), "fieldname": "medication", "fieldtype": "Link", "options": "Medication", "width": 180},
		{"label": _("Dose"), "fieldname": "dose_numero", "fieldtype": "Int", "width": 75},
		{"label": _("Estoque"), "fieldname": "estoque", "fieldtype": "Float", "precision": "0", "width": 90},
		{"label": _("Pago?"), "fieldname": "pago", "fieldtype": "Data", "width": 90},
		{"label": _("Local"), "fieldname": "modalidade", "fieldtype": "Data", "width": 110},
		{"label": _("Situação"), "fieldname": "situacao", "fieldtype": "Data", "width": 160},
		{"label": _("CRM"), "fieldname": "atendimento", "fieldtype": "Data", "width": 80},
		{"label": _("Endereço"), "fieldname": "endereco", "fieldtype": "Data", "width": 260},
		{"label": _("Agendamento"), "fieldname": "appointment", "fieldtype": "Link", "options": "Patient Appointment", "width": 140},
	]


def _data(filters: frappe._dict, de, ate) -> list[dict]:
	conditions = ["pa.appointment_date BETWEEN %(de)s AND %(ate)s"]
	values = {"de": de, "ate": ate}

	if filters.get("modalidade"):
		conditions.append("pa.imun_modalidade = %(modalidade)s")
		values["modalidade"] = filters.get("modalidade")
	if filters.get("patient"):
		conditions.append("pa.patient = %(patient)s")
		values["patient"] = filters.get("patient")

	rows = frappe.db.sql(
		f"""
		SELECT
			pa.name AS appointment,
			pa.appointment_datetime,
			pa.appointment_date,
			pa.patient,
			pa.status,
			pa.invoiced, pa.paid_amount, pa.ref_sales_invoice,
			pa.imun_modalidade AS modalidade,
			pa.imun_application_address_display AS endereco,
			v.medication, v.dose_numero
		FROM `tabPatient Appointment` pa
		LEFT JOIN `tabImunocare Appointment Vaccine` v
			ON v.parent = pa.name AND v.parenttype = 'Patient Appointment'
		WHERE {" AND ".join(conditions)}
		ORDER BY pa.appointment_datetime ASC, pa.name ASC
		""",
		values,
		as_dict=True,
	)

	hoje = getdate(nowdate())
	estoque_cache: dict[str, float] = {}
	resultado: list[dict] = []

	for r in rows:
		pago = _is_pago(r)
		situacao = _situacao(r, hoje)
		atrasado = situacao == "Atrasado"

		if filters.get("somente_pagos_atrasados") and not (atrasado and pago):
			continue

		med = r.get("medication")
		if med and med not in estoque_cache:
			estoque_cache[med] = estoque_da_vacina(med)

		resultado.append(
			{
				"appointment": r.appointment,
				"appointment_datetime": r.appointment_datetime,
				"patient": r.patient,
				"medication": med,
				"dose_numero": r.dose_numero,
				"estoque": estoque_cache.get(med, 0.0) if med else None,
				"pago": _("Pago") if pago else _("A pagar"),
				"modalidade": r.modalidade or _("Clínica"),
				"situacao": situacao,
				# Flag (sem coluna) consumida pelo .js: dobra o alerta de
				# "pago e atrasado" dentro da própria coluna Situação.
				"pago_atrasado": 1 if (atrasado and pago) else 0,
				# A coluna Atendimento é renderizada pelo .js a partir de "patient"
				# (abre a comunicação com o paciente via Lead no CRM).
				"atendimento": r.patient,
				"endereco": r.endereco,
			}
		)
	return resultado


def _situacao(r, hoje) -> str:
	"""Situação operacional, dirigida pela data.

	Só estados terminais escapam da regra de data: ``Cancelled`` (cancelado de
	propósito) e realizado (``Closed``/``Checked Out``). Todo o resto vencido —
	inclusive ``No Show``, para onde o Healthcare empurra agendamentos não
	atendidos — conta como **Atrasado**.
	"""
	status = r.get("status")
	if status in STATUS_CANCELADO:
		return _("Cancelado")
	if status in STATUS_REALIZADO:
		return _("Realizado")
	data = getdate(r.get("appointment_date")) if r.get("appointment_date") else None
	if not data:
		return _("Agendado")
	if data < hoje:
		return _("Atrasado")
	if data == hoje:
		return _("Hoje")
	return _("Futuro")
