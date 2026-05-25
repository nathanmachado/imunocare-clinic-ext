"""Hooks de Employee (colaborador) — validação de CPF (Fase 4 / RNDS).

O CPF é o documento primário do colaborador e a chave para resolver o CNS no
RNDS (no cadastro do profissional de saúde vinculado).
"""

from __future__ import annotations

import re

import frappe
from frappe import _

from imunocare_clinic_ext.patient_hooks import is_valid_cpf


def validate(doc, method=None) -> None:
	raw = doc.get("cpf")
	if not raw:
		return
	digits = re.sub(r"\D", "", raw)
	if not is_valid_cpf(digits):
		frappe.throw(_("CPF inválido: {0}").format(raw))
	doc.cpf = digits
