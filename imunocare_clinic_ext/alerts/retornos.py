"""
Scheduler diário: envia lembretes de retorno por WhatsApp e e-mail.
Também cria Retorno Programado ao submeter Patient Appointment de vacinação.
"""

from __future__ import annotations
import frappe
from frappe.utils import add_days, today, getdate


# Dias antecedência para lembrete
_LEMBRETES = [
    (30, "lembrete_30d"),
    (7,  "lembrete_7d"),
    (1,  "lembrete_1d"),
]


def enviar_lembretes() -> None:
    """Verifica retornos pendentes e envia lembretes nos prazos configurados."""
    retornos = frappe.get_all(
        "Retorno Programado",
        filters={"status": ["in", ["Pendente", "Agendado"]]},
        fields=["name", "patient", "patient_name", "data_retorno",
                "whatsapp", "email_paciente", "lembrete_30d", "lembrete_7d", "lembrete_1d",
                "protocolo", "numero_dose"],
    )
    for r in retornos:
        data_ret = getdate(r.data_retorno)
        for dias, campo in _LEMBRETES:
            if r.get(campo):
                continue
            if getdate(add_days(today(), dias)) == data_ret:
                _enviar_lembrete(r, dias)
                frappe.db.set_value("Retorno Programado", r.name, campo, 1)
    frappe.db.commit()


def _enviar_lembrete(retorno: dict, dias: int) -> None:
    nome = retorno.patient_name or "paciente"
    vacina = retorno.protocolo or "vacina"
    dose = retorno.numero_dose or ""

    if dias == 1:
        prazo = "amanhã"
    elif dias == 7:
        prazo = "em 7 dias"
    else:
        prazo = f"em {dias} dias"

    mensagem = (
        f"Olá, {nome}! 💉 Lembrete Imunocare:\n"
        f"Sua próxima dose de *{vacina}*{(' — ' + dose) if dose else ''} está agendada para *{prazo}* "
        f"({retorno.data_retorno}).\n"
        "Confirme seu agendamento ou entre em contato: (XX) XXXX-XXXX."
    )

    if retorno.whatsapp:
        _enviar_whatsapp(retorno.whatsapp, mensagem)

    if retorno.email_paciente:
        frappe.sendmail(
            recipients=[retorno.email_paciente],
            subject=f"Lembrete: próxima dose de {vacina} — Imunocare",
            message=mensagem.replace("\n", "<br>"),
        )


def _enviar_whatsapp(numero: str, mensagem: str) -> None:
    try:
        canal = frappe.get_all("Canal WhatsApp", filters={"ativo": 1}, fields=["name"], limit=1)
        if not canal:
            return
        from imunocare_crm_custom.whatsapp.client import enviar_mensagem
        enviar_mensagem(numero=numero, mensagem=mensagem, canal_name=canal[0].name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Erro lembrete WhatsApp retorno")


def appointment_on_submit(doc, method=None) -> None:
    """Cria Retorno Programado ao confirmar agendamento de vacinação."""
    if doc.get("tipo_servico") != "Vacinação":
        return
    if not doc.get("protocolo_vacina"):
        return

    patient = frappe.get_doc("Patient", doc.patient)
    whatsapp = getattr(patient, "mobile", None) or getattr(patient, "phone", None) or ""

    retorno = frappe.get_doc({
        "doctype": "Retorno Programado",
        "patient": doc.patient,
        "protocolo": doc.get("protocolo_vacina"),
        "status": "Agendado",
        "whatsapp": whatsapp,
        "email_paciente": patient.email or "",
    })
    retorno.insert(ignore_permissions=True)
    frappe.db.commit()
