"""Hooks de Healthcare Practitioner (Fase 4 / RNDS).

O CPF é do colaborador (Employee). Ao salvar o profissional de saúde, resolve o
CNS no RNDS (GET /Practitioner) usando o CPF do Employee vinculado. Read-only,
não-bloqueante; alerta se o colaborador não tiver CPF ou o CNS não for achado.
"""

from __future__ import annotations

import frappe
from frappe import _


def validate(doc, method=None) -> None:
	_resolve_cns(doc)


def _resolve_cns(doc) -> None:
	if not doc.get("employee"):
		return

	cpf = frappe.db.get_value("Employee", doc.employee, "cpf")
	if not cpf:
		frappe.msgprint(
			_("O colaborador vinculado não possui CPF cadastrado — CNS não pôde ser resolvido."),
			indicator="orange",
			alert=True,
		)
		return

	emp_mudou = True if doc.is_new() else doc.has_value_changed("employee")
	if doc.get("cns") and not emp_mudou:
		return

	try:
		from imunocare_clinic_ext.rnds_client import resolve_cns_profissional

		cns = resolve_cns_profissional(cpf)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"RNDS: falha ao resolver CNS do profissional (cadastro segue sem CNS)",
		)
		return

	if cns:
		doc.cns = cns
	else:
		frappe.msgprint(
			_("CNS do profissional não encontrado no RNDS para o CPF do colaborador."),
			indicator="orange",
			alert=True,
		)
