"""Schedulers de enfileiramento de disparos WhatsApp (Fase 8).

Enfileiram WhatsApp Dispatch pendentes (não enviam) — a autorização é manual.
"""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe.utils import add_days, nowdate

from imunocare_clinic_ext.dispatch import enfileirar_para_appointment, enfileirar_reforco
from imunocare_clinic_ext.imunocare_clinic_ext.report.retornos_pendentes.retornos_pendentes import (
	STATUS_FINALIZADOS,
)

# Quantos dias antes do vencimento da dose enfileirar o lembrete de reforço.
REFORCO_ANTECEDENCIA_DIAS = 7


def enfileirar_lembretes_d1():
	"""Lembrete D-1: agendamentos de amanhã com vacinas definidas."""
	amanha = add_days(nowdate(), 1)
	appointments = frappe.get_all(
		"Patient Appointment",
		filters={
			"appointment_date": amanha,
			"status": ("in", ["Scheduled", "Open", "Confirmed", "Checked In"]),
		},
		pluck="name",
	)
	for name in appointments:
		if frappe.db.exists("Imunocare Appointment Vaccine", {"parent": name}):
			enfileirar_para_appointment(name, "Lembrete (D-1)")


def enfileirar_lembretes_reforco():
	"""Lembrete de reforço: doses pendentes vencendo na janela de antecedência.

	Agrupa os Medication Requests pendentes por paciente para um único disparo
	com a lista de doses.
	"""
	limite = add_days(nowdate(), REFORCO_ANTECEDENCIA_DIAS)
	requests = frappe.get_all(
		"Medication Request",
		filters={
			"docstatus": ("<", 2),
			"status": ("not in", STATUS_FINALIZADOS),
			"expected_date": ("<=", limite),
		},
		fields=["name", "patient"],
		order_by="patient, expected_date",
	)
	por_paciente: dict[str, list[str]] = defaultdict(list)
	for r in requests:
		por_paciente[r["patient"]].append(r["name"])

	for patient, mrs in por_paciente.items():
		enfileirar_reforco(patient, mrs)
