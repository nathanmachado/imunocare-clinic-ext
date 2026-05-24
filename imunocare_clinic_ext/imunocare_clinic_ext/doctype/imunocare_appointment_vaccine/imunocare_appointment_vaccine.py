"""Imunocare Appointment Vaccine — child table de vacinas planejadas do agendamento.

Vacinas que serão aplicadas em um Patient Appointment (fonte da variável de
vacinas dos templates HSM de WhatsApp). Distinta do Medication Request (Fase 5),
que representa doses futuras de pacotes/combos.
"""

from __future__ import annotations

from frappe.model.document import Document


class ImunocareAppointmentVaccine(Document):
	pass
