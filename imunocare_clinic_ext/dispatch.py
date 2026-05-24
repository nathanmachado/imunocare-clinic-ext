"""Enfileiramento de disparos WhatsApp (Fase 8).

Os eventos de imunização chamam estas funções para CRIAR um WhatsApp Dispatch
pendente (com pré-visualização) — nunca enviam direto. O envio acontece só após
autorização manual (ver whatsapp_dispatch.WhatsAppDispatch.autorizar_e_enviar).
"""

from __future__ import annotations

import json

import frappe

from imunocare_clinic_ext.whatsapp_helpers import (
	get_appointment_whatsapp_params,
	get_dose_reminder_whatsapp_params,
)

# Sufixo de idioma dos templates aprovados na Meta.
_LANG = "-pt_BR"

# template_key (legível) → (nome técnico do template, ordem das chaves do param)
TEMPLATE_SPECS = {
	"Confirmação de agendamento": (f"confirmacao_agendamento{_LANG}", ["nome", "vacinas", "data", "hora", "modalidade", "endereco", "pagamento"]),
	"Lembrete (D-1)": (f"lembrete_agendamento_d1{_LANG}", ["nome", "vacinas", "data", "hora", "modalidade", "endereco", "pagamento"]),
	"Reagendamento": (f"reagendamento{_LANG}", ["nome", "vacinas", "data", "hora", "modalidade", "endereco", "pagamento"]),
	"Lembrete de reforço": (f"lembrete_reforco_dose{_LANG}", ["nome", "doses", "prazo"]),
}

# Texto dos templates para renderizar a pré-visualização (sem depender do
# WhatsApp Templates record existir no site — em dev local ele não existe).
_PREVIEW_BODIES = {
	"Confirmação de agendamento": (
		"Olá, {nome}. Seu agendamento na Imunocare está confirmado.\n\n"
		"Vacinas: {vacinas}\nData: {data} às {hora}\nModalidade: {modalidade}\n"
		"Endereço: {endereco}\nPagamento: {pagamento}\n\n"
		"Para reagendar ou tirar dúvidas, responda esta mensagem."
	),
	"Lembrete (D-1)": (
		"Olá, {nome}. Passando para lembrar do seu agendamento amanhã na Imunocare.\n\n"
		"Vacinas: {vacinas}\nData: {data} às {hora}\nModalidade: {modalidade}\n"
		"Endereço: {endereco}\nPagamento: {pagamento}\n\n"
		"Estamos à disposição se precisar ajustar."
	),
	"Reagendamento": (
		"Olá, {nome}. Seu agendamento na Imunocare foi atualizado.\n\n"
		"Vacinas: {vacinas}\nNova data: {data} às {hora}\nModalidade: {modalidade}\n"
		"Endereço: {endereco}\nPagamento: {pagamento}\n\n"
		"Se este horário não funcionar, responda esta mensagem."
	),
	"Lembrete de reforço": (
		"Olá, {nome}. Identificamos que você tem dose(s) próxima(s) do vencimento.\n\n"
		"Próximas doses: {doses}\nRecomendamos agendar até: {prazo}\n\n"
		"Para agendar, responda esta mensagem."
	),
}


def _render_preview(template_key: str, params: dict) -> str:
	body = _PREVIEW_BODIES.get(template_key, "")
	try:
		return body.format(**{k: params.get(k, "") for k in params})
	except Exception:
		return body


def _body_param(template_key: str, params: dict) -> str:
	"""JSON ordenado {"1": v1, "2": v2, ...} conforme a ordem do template."""
	_, ordem = TEMPLATE_SPECS[template_key]
	return json.dumps({str(i + 1): params.get(chave, "") for i, chave in enumerate(ordem)})


def _ja_enfileirado(reference_doctype: str, reference_name: str, template_key: str) -> bool:
	"""Evita duplicar disparo do mesmo tipo para o mesmo documento de origem.

	Considera apenas disparos ainda Pendentes ou já Enviados (Cancelado/Erro
	podem ser refeitos).
	"""
	return bool(
		frappe.db.exists(
			"WhatsApp Dispatch",
			{
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
				"template_key": template_key,
				"status": ("in", ["Pendente", "Enviado"]),
			},
		)
	)


def enfileirar(patient, to, template_key, params, reference_doctype=None, reference_name=None):
	"""Cria um WhatsApp Dispatch pendente. Retorna o name, ou None se já existe/sem destino."""
	if not to:
		return None
	if reference_name and _ja_enfileirado(reference_doctype, reference_name, template_key):
		return None

	template_name, _ordem = TEMPLATE_SPECS[template_key]
	doc = frappe.get_doc(
		{
			"doctype": "WhatsApp Dispatch",
			"patient": patient,
			"to": to,
			"template_key": template_key,
			"template": template_name,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"body_param": _body_param(template_key, params),
			"preview": _render_preview(template_key, params),
			"status": "Pendente",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


# --- Builders por evento (chamados pelos hooks/schedulers) ---


def enfileirar_para_appointment(appointment_name: str, template_key: str) -> str | None:
	"""Enfileira um disparo de agendamento (confirmação/lembrete/reagendamento)."""
	appt = frappe.get_doc("Patient Appointment", appointment_name)
	to = _mobile_do_paciente(appt.get("patient"))
	params = get_appointment_whatsapp_params(appointment_name)
	return enfileirar(
		patient=appt.get("patient"),
		to=to,
		template_key=template_key,
		params=params,
		reference_doctype="Patient Appointment",
		reference_name=appointment_name,
	)


def enfileirar_reforco(patient: str, medication_requests: list[str]) -> str | None:
	"""Enfileira o lembrete de reforço para um paciente e suas doses pendentes."""
	if not medication_requests:
		return None
	patient_name = frappe.db.get_value("Patient", patient, "patient_name")
	to = _mobile_do_paciente(patient)
	params = get_dose_reminder_whatsapp_params(patient_name, medication_requests)
	# Usa o primeiro MR como referência de origem.
	return enfileirar(
		patient=patient,
		to=to,
		template_key="Lembrete de reforço",
		params=params,
		reference_doctype="Medication Request",
		reference_name=medication_requests[0],
	)


def _mobile_do_paciente(patient: str | None) -> str | None:
	if not patient:
		return None
	return frappe.db.get_value("Patient", patient, "mobile")
