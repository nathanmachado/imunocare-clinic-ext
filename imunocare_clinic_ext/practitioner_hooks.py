"""Hooks de Healthcare Practitioner (Fase 4 / RNDS).

Ao salvar o cadastro do profissional, resolve o CNS pelo CPF via RNDS
(GET /Practitioner) — análogo à resolução do CNS do paciente. Não-bloqueante:
falha do RNDS apenas loga. Se o CNS não for encontrado, alerta o usuário.
"""

from __future__ import annotations

import re

import frappe
from frappe import _

from imunocare_clinic_ext.patient_hooks import is_valid_cpf


def validate(doc, method=None) -> None:
	_validate_cpf(doc)
	_resolve_cns(doc)


def _validate_cpf(doc) -> None:
	raw = doc.get("cpf")
	if not raw:
		return
	digits = re.sub(r"\D", "", raw)
	if not is_valid_cpf(digits):
		frappe.throw(_("CPF inválido: {0}").format(raw))
	doc.cpf = digits


def _resolve_cns(doc) -> None:
	cpf = doc.get("cpf")
	if not cpf:
		return
	cpf_mudou = True if doc.is_new() else doc.has_value_changed("cpf")
	if doc.get("cns") and not cpf_mudou:
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
			_("CNS do profissional não encontrado no RNDS para o CPF informado."),
			indicator="orange",
			alert=True,
		)
