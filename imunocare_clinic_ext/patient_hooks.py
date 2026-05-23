"""Hooks de Patient para o domínio de imunização (Fase 2 / ajuste CPF).

CPF é o documento primário de identificação (ADR-0001, atualização 2026-05-22).
A maioria dos pacientes não tem o cartão SUS (CNS) em mãos na vacinação; o RNDS
aceita CPF como identificador e resolve o CNS via GET /patient (Fase 4).

Este hook valida o CPF (regras da Receita Federal) e o normaliza para 11 dígitos
— formato exigido pelo identifier FHIR do RNDS.
"""

from __future__ import annotations

import re

import frappe
from frappe import _


def validate(doc, method=None) -> None:
	"""Valida e normaliza o CPF do paciente, se preenchido."""
	cpf_raw = doc.get("cpf")
	if not cpf_raw:
		return

	cpf_digits = re.sub(r"\D", "", cpf_raw)
	if not is_valid_cpf(cpf_digits):
		frappe.throw(_("CPF inválido: {0}").format(cpf_raw))

	# Armazena só dígitos (padrão para o identifier FHIR do RNDS).
	doc.cpf = cpf_digits


def is_valid_cpf(cpf: str) -> bool:
	"""Valida CPF pelas regras da Receita Federal (dígitos verificadores).

	Espera ``cpf`` já com apenas dígitos. Rejeita comprimento != 11 e
	sequências repetidas (ex.: 11111111111), que passam no cálculo mas são
	inválidas por convenção.
	"""
	if len(cpf) != 11 or not cpf.isdigit():
		return False
	if cpf == cpf[0] * 11:
		return False

	for length in (9, 10):
		soma = sum(int(cpf[i]) * (length + 1 - i) for i in range(length))
		digito = (soma * 10 % 11) % 10
		if digito != int(cpf[length]):
			return False
	return True
