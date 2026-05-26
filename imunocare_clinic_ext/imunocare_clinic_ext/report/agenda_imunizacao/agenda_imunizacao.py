"""Report Agenda de Imunização (Fase 10).

Resumo operacional dos atendimentos de vacinação num horizonte de datas
(Hoje / Esta semana / Este mês / Personalizado). Uma linha por vacina de cada
Patient Appointment, com: paciente, vacina, dose, estoque da vacina, se está
pago, modalidade (Clínica/Domiciliar), endereço, situação operacional e um
botão de WhatsApp pré-preenchido.

Reuso (ver feedback_reuse_first): parte do Patient Appointment nativo + child
``imun_vaccines`` (Imunocare Appointment Vaccine), estoque do ``Bin`` via
``imunocare_clinic_ext.api.dashboard.estoque_da_vacina`` e "pago" dos campos
nativos do appointment. Nada de controle paralelo.

A renderização (cores, botão WhatsApp, presets de data) fica no
``agenda_imunizacao.js`` — armazenado em arquivo do app, carregado em runtime,
sem build de assets.
"""

from __future__ import annotations

from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import get_first_day, get_last_day, getdate, nowdate

from imunocare_clinic_ext.api.dashboard import (
	STATUS_ENCERRADO,
	STATUS_REALIZADO,
	_is_pago,
	estoque_da_vacina,
)

# Mensagem padrão do WhatsApp (o time ajusta antes de enviar).
_WA_MSG = (
	"Olá {nome}, aqui é da Imunocare. "
	"Sobre sua aplicação de {vacina} em {data}: podemos confirmar?"
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
		{"label": _("Data/Hora"), "fieldname": "appointment_datetime", "fieldtype": "Datetime", "width": 145},
		{"label": _("Paciente"), "fieldname": "patient", "fieldtype": "Link", "options": "Patient", "width": 110},
		{"label": _("Nome"), "fieldname": "patient_name", "fieldtype": "Data", "width": 150},
		{"label": _("Vacina"), "fieldname": "medication", "fieldtype": "Link", "options": "Medication", "width": 150},
		{"label": _("Dose"), "fieldname": "dose_numero", "fieldtype": "Int", "width": 55},
		{"label": _("Estoque"), "fieldname": "estoque", "fieldtype": "Float", "precision": "0", "width": 80},
		{"label": _("Pago?"), "fieldname": "pago", "fieldtype": "Data", "width": 80},
		{"label": _("Local"), "fieldname": "modalidade", "fieldtype": "Data", "width": 95},
		{"label": _("Situação"), "fieldname": "situacao", "fieldtype": "Data", "width": 110},
		{"label": _("Alerta"), "fieldname": "alerta", "fieldtype": "Data", "width": 130},
		{"label": _("WhatsApp"), "fieldname": "whatsapp", "fieldtype": "Data", "width": 95},
		{"label": _("Endereço"), "fieldname": "endereco", "fieldtype": "Data", "width": 220},
		{"label": _("Agendamento"), "fieldname": "appointment", "fieldtype": "Link", "options": "Patient Appointment", "width": 130},
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
			pa.patient, pa.patient_name,
			p.mobile,
			pa.status,
			pa.invoiced, pa.paid_amount, pa.ref_sales_invoice,
			pa.imun_modalidade AS modalidade,
			pa.imun_application_address_display AS endereco,
			v.medication, v.dose_numero
		FROM `tabPatient Appointment` pa
		LEFT JOIN `tabPatient` p ON pa.patient = p.name
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
				"patient_name": r.patient_name,
				"medication": med,
				"dose_numero": r.dose_numero,
				"estoque": estoque_cache.get(med, 0.0) if med else None,
				"pago": _("Pago") if pago else _("A pagar"),
				"modalidade": r.modalidade or _("Clínica"),
				"situacao": situacao,
				"alerta": _("⚠ PAGO E ATRASADO") if (atrasado and pago) else "",
				"whatsapp": _wa_link(r),
				"endereco": r.endereco,
			}
		)
	return resultado


def _situacao(r, hoje) -> str:
	status = r.get("status")
	if status in STATUS_ENCERRADO:
		return _("Cancelado/Falta")
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


def _wa_link(r) -> str | None:
	"""URL wa.me pré-preenchida; o ``.js`` transforma em botão clicável."""
	fone = _somente_digitos(r.get("mobile"))
	if not fone:
		return None
	if len(fone) <= 11:  # sem código do país → assume Brasil
		fone = "55" + fone
	data = frappe.utils.format_datetime(r.get("appointment_datetime"), "dd/MM HH:mm") if r.get("appointment_datetime") else ""
	msg = _WA_MSG.format(
		nome=(r.get("patient_name") or "").split(" ")[0],
		vacina=r.get("medication") or _("sua vacina"),
		data=data,
	)
	return f"https://wa.me/{fone}?text={quote(msg)}"


def _somente_digitos(valor: str | None) -> str:
	return "".join(c for c in (valor or "") if c.isdigit())
