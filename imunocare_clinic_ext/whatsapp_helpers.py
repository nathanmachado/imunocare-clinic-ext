"""Helpers de formatação para os templates HSM de WhatsApp (Fase 7).

Esta camada (no domínio de imunização) extrai e formata as variáveis que os
templates aprovados esperam. O ENVIO em si (chamar a API do frappe_whatsapp via
hooks/schedulers) fica no imunocare_crm_custom (Fase 8).

Templates cobertos aqui:
- confirmacao_agendamento / lembrete_agendamento_d1 / reagendamento (7 vars do
  Patient Appointment) → get_appointment_whatsapp_params.
- lembrete_reforco_dose (3 vars, Medication Request) → get_dose_reminder_whatsapp_params.

Strings de modalidade/pagamento batem exatamente com os exemplos submetidos à
Meta (ver project-whatsapp-templates).
"""

from __future__ import annotations

import frappe
from frappe.utils import formatdate, get_time, getdate

_MODALIDADE_MAP = {
	"Clínica": "Atendimento CLÍNICA",
	"Domiciliar": "Atendimento DOMICILIAR",
}
_PAGO_INVOICE_STATUS = {"Paid", "Partly Paid"}


def format_vaccine_list(items: list[str]) -> str:
	"""Concatena nomes em PT-BR: 'A', 'A e B', 'A, B e C'."""
	items = [str(s).strip() for s in (items or []) if s and str(s).strip()]
	if not items:
		return ""
	if len(items) == 1:
		return items[0]
	if len(items) == 2:
		return f"{items[0]} e {items[1]}"
	return ", ".join(items[:-1]) + f" e {items[-1]}"


def modalidade_label(value: str | None) -> str:
	"""Converte o valor do campo (Clínica/Domiciliar) na string do template."""
	return _MODALIDADE_MAP.get(value or "Clínica", "Atendimento CLÍNICA")


def payment_status_label(appointment) -> str:
	"""Deriva 'Pago' / 'A pagar' do Sales Invoice vinculado ao appointment."""
	invoice = appointment.get("ref_sales_invoice")
	if invoice:
		status = frappe.db.get_value("Sales Invoice", invoice, "status")
		if status in _PAGO_INVOICE_STATUS:
			return "Pago"
	return "A pagar"


def get_appointment_vaccines(appointment) -> list[str]:
	"""Nomes das vacinas do agendamento (child table imun_vaccines)."""
	nomes = []
	for row in appointment.get("imun_vaccines") or []:
		medication = row.get("medication")
		if medication:
			nomes.append(medication)
	return nomes


def _format_time(value) -> str:
	"""Time (timedelta/str) → 'HH:MM'."""
	if not value:
		return ""
	try:
		t = get_time(value)
		return f"{t.hour:02d}:{t.minute:02d}"
	except Exception:
		return str(value)[:5]


def get_appointment_whatsapp_params(appointment_name: str) -> dict:
	"""Variáveis dos templates de agendamento (confirmação/lembrete/reagendamento).

	Retorna dict com chaves estáveis; o hook de envio (Fase 8) monta a lista
	ordenada de parâmetros conforme cada template::

	    {{1}} nome · {{2}} vacinas · {{3}} data · {{4}} hora ·
	    {{5}} modalidade · {{6}} endereço · {{7}} pagamento
	"""
	appt = frappe.get_doc("Patient Appointment", appointment_name)
	return {
		"nome": appt.get("patient_name") or "",
		"vacinas": format_vaccine_list(get_appointment_vaccines(appt)),
		"data": formatdate(appt.get("appointment_date"), "dd/MM/yyyy") if appt.get("appointment_date") else "",
		"hora": _format_time(appt.get("appointment_time")),
		"modalidade": modalidade_label(appt.get("imun_modalidade")),
		"endereco": appt.get("imun_application_address_display") or "",
		"pagamento": payment_status_label(appt),
	}


def _dose_label(medication: str, dose_numero: int | None) -> str:
	"""'Hepatite B (3ª dose)' a partir da vacina e do número da dose."""
	if dose_numero:
		return f"{medication} ({dose_numero}ª dose)"
	return medication


def get_dose_reminder_whatsapp_params(patient_name: str, medication_requests: list[str]) -> dict:
	"""Variáveis do template lembrete_reforco_dose (Fase 5/8).

	Recebe o nome do paciente e os Medication Requests de doses pendentes.
	Retorna::

	    {{1}} nome · {{2}} doses (lista) · {{3}} prazo sugerido (menor expected_date)
	"""
	docs = [frappe.get_doc("Medication Request", mr) for mr in medication_requests]
	doses = [_dose_label(d.get("medication"), d.get("dose_numero")) for d in docs]
	datas = [getdate(d.get("expected_date")) for d in docs if d.get("expected_date")]
	prazo = formatdate(min(datas), "dd/MM/yyyy") if datas else ""
	return {
		"nome": patient_name or "",
		"doses": format_vaccine_list(doses),
		"prazo": prazo,
	}
