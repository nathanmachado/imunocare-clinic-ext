"""Hooks de Patient Encounter para envio ao RNDS (Fase 4c).

Ao registrar aplicações de vacina (Drug Prescription com Medication is_vaccine),
enfileira o envio do RIA ao RNDS de forma assíncrona. Diferente dos disparos de
WhatsApp (que exigem aprovação manual), o registro no RNDS é compulsório por lei
— por isso é automático, com retry para falhas.
"""

from __future__ import annotations

import frappe


def on_update(doc, method=None) -> None:
	"""Enfileira o envio ao RNDS das vacinas ainda não enviadas do encounter."""
	for dp in doc.get("drug_prescription") or []:
		if not dp.get("medication"):
			continue
		if dp.get("rnds_status") == "Enviado":
			continue
		if not frappe.db.get_value("Medication", dp.medication, "is_vaccine"):
			continue

		if dp.get("rnds_status") in (None, "", "Não aplicável"):
			dp.db_set("rnds_status", "Pendente", update_modified=False)

		frappe.enqueue(
			"imunocare_clinic_ext.rnds_immunization.enviar_imunizacao",
			queue="long",
			enqueue_after_commit=True,
			encounter=doc.name,
			dp_name=dp.name,
		)
