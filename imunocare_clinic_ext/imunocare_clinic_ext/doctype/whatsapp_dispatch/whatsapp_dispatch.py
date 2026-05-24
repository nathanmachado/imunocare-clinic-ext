"""WhatsApp Dispatch — fila de disparos com autorização manual (Fase 8).

Eventos de imunização (agendamento, lembrete, reforço) NÃO enviam WhatsApp
direto: enfileiram um WhatsApp Dispatch com status "Pendente" e uma
pré-visualização. Um usuário revisa e autoriza cada disparo (botão no form ou
ação em massa na lista). Só então a mensagem é enviada via frappe_whatsapp.

Garante revisão humana por paciente antes de qualquer envio.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class WhatsAppDispatch(Document):
	@frappe.whitelist()
	def autorizar_e_enviar(self):
		"""Autoriza e envia o disparo via frappe_whatsapp. Idempotente por status."""
		if self.status != "Pendente":
			frappe.throw(_("Apenas disparos Pendentes podem ser enviados (status atual: {0}).").format(self.status))

		self.authorized_by = frappe.session.user
		self.authorized_on = now_datetime()

		try:
			msg = frappe.get_doc(
				{
					"doctype": "WhatsApp Message",
					"type": "Outgoing",
					"to": self.to,
					"template": self.template,
					"use_template": 1,
					"body_param": self.body_param,
					"reference_doctype": self.reference_doctype,
					"reference_name": self.reference_name,
				}
			)
			msg.insert(ignore_permissions=True)  # before_insert dispara o envio
		except Exception as e:
			self.status = "Erro"
			self.error_log = str(e)[:2000]
			self.save(ignore_permissions=True)
			frappe.log_error(frappe.get_traceback(), "WhatsApp Dispatch falhou")
			frappe.throw(_("Falha no envio: {0}").format(str(e)))

		self.status = "Enviado"
		self.sent_on = now_datetime()
		self.whatsapp_message = msg.name
		self.save(ignore_permissions=True)
		return self.status

	@frappe.whitelist()
	def cancelar(self):
		"""Cancela um disparo pendente."""
		if self.status != "Pendente":
			frappe.throw(_("Apenas disparos Pendentes podem ser cancelados."))
		self.status = "Cancelado"
		self.save(ignore_permissions=True)
		return self.status


@frappe.whitelist()
def autorizar_em_massa(names: str) -> dict:
	"""Autoriza e envia vários disparos (ação em massa na lista).

	``names`` é um JSON array de nomes de WhatsApp Dispatch.
	"""
	names = json.loads(names) if isinstance(names, str) else names
	enviados, erros = 0, 0
	for name in names:
		doc = frappe.get_doc("WhatsApp Dispatch", name)
		if doc.status != "Pendente":
			continue
		try:
			doc.autorizar_e_enviar()
			enviados += 1
		except Exception:
			erros += 1
	return {"enviados": enviados, "erros": erros}
