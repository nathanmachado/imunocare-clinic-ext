"""Hooks de Patient Appointment para o domínio de imunização (Fase 2).

Popula ``imun_application_address_display`` automaticamente a partir da
modalidade do atendimento:
- Clínica   → endereço curto da clínica (site_config ``imunocare_clinic_address_short``)
- Domiciliar → endereço primário do paciente (Dynamic Link em Address)

O campo é read-only na UI; serve de snapshot para os templates HSM de
WhatsApp (Fase 7/8) e para impressão.
"""

from __future__ import annotations

import frappe

_DEFAULT_CLINIC_ADDRESS = "Imunocare - Unidade Pátio Sabiá"


def before_save(doc, method=None) -> None:
	"""Popula ``imun_application_address_display`` conforme a modalidade."""
	modalidade = doc.get("imun_modalidade") or "Clínica"

	if modalidade == "Domiciliar":
		doc.imun_application_address_display = _patient_address(doc.get("patient")) or ""
	else:
		doc.imun_application_address_display = _clinic_address()


def after_insert(doc, method=None) -> None:
	"""Enfileira (sem enviar) a confirmação de agendamento para autorização."""
	if not doc.get("imun_vaccines"):
		return
	from imunocare_clinic_ext.dispatch import enfileirar_para_appointment

	enfileirar_para_appointment(doc.name, "Confirmação de agendamento")


def on_update(doc, method=None) -> None:
	"""Enfileira reagendamento quando data ou hora mudam em um doc já existente."""
	if doc.is_new() or not doc.get("imun_vaccines"):
		return
	before = doc.get_doc_before_save()
	if not before:
		return
	if (before.get("appointment_date") == doc.get("appointment_date")
			and before.get("appointment_time") == doc.get("appointment_time")):
		return
	from imunocare_clinic_ext.dispatch import enfileirar_para_appointment

	enfileirar_para_appointment(doc.name, "Reagendamento")


def _clinic_address() -> str:
	"""Endereço curto da clínica vindo de site_config (fallback hardcoded)."""
	return frappe.conf.get("imunocare_clinic_address_short") or _DEFAULT_CLINIC_ADDRESS


def _patient_address(patient: str | None) -> str | None:
	"""Resolve o endereço primário do paciente como string inline.

	Healthcare liga Patient a Address via Dynamic Link (link_doctype=Patient).
	Pega o Address marcado como ``is_primary_address`` ou, na falta, o primeiro.
	"""
	if not patient:
		return None

	address_names = frappe.get_all(
		"Dynamic Link",
		filters={
			"link_doctype": "Patient",
			"link_name": patient,
			"parenttype": "Address",
		},
		pluck="parent",
	)
	if not address_names:
		return None

	addresses = frappe.get_all(
		"Address",
		filters={"name": ("in", address_names)},
		fields=["name", "is_primary_address", "address_line1", "address_line2", "city", "state"],
		order_by="is_primary_address desc",
	)
	if not addresses:
		return None

	addr = addresses[0]
	parts = [
		addr.get("address_line1"),
		addr.get("address_line2"),
		addr.get("city"),
		addr.get("state"),
	]
	return " - ".join(p for p in parts if p)
