"""Hooks de Patient para o domínio de imunização (Fase 2 / cadastro obrigatório).

CPF é o documento primário de identificação (ADR-0001, atualização 2026-05-22).
A maioria dos pacientes não tem o cartão SUS (CNS) em mãos na vacinação; o RNDS
aceita CPF como identificador e resolve o CNS via GET /patient (Fase 4).

Validações server-side (não burláveis por API/import):
- CPF do paciente e do responsável (regras da Receita Federal), normalizados.
- Para menores de 18 anos: nome e CPF do responsável obrigatórios.
- Endereço vinculado obrigatório (validado fora do primeiro insert — Address
  só pode ser vinculado depois que o Patient existe).
"""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

MAIORIDADE = 18


def validate(doc, method=None) -> None:
	"""Valida CPF, responsável (menores), endereço e resolve o CNS no RNDS."""
	_validate_and_normalize_cpf(doc, "cpf", _("CPF inválido: {0}"))
	_validate_and_normalize_cpf(doc, "cpf_responsavel", _("CPF do responsável inválido: {0}"))
	_validate_guardian(doc)
	_validate_address(doc)
	_resolve_cns(doc)


def _resolve_cns(doc) -> None:
	"""Resolve o CNS pelo CPF no RNDS durante o save (não-bloqueante).

	A busca acontece no fluxo de salvar — não depende de ação manual, evitando
	pacientes sem CNS e erros no registro RNDS. Só consulta quando há CPF e o
	CNS ainda não foi preenchido (ou o CPF mudou). Falhas do RNDS (timeout,
	indisponibilidade) NUNCA bloqueiam o cadastro: apenas logam.
	"""
	cpf = doc.get("cpf")
	if not cpf:
		return
	cpf_mudou = True if doc.is_new() else doc.has_value_changed("cpf")
	if doc.get("cns") and not cpf_mudou:
		return

	try:
		from imunocare_clinic_ext.rnds_client import resolve_cns

		cns = resolve_cns(cpf)
		if cns:
			doc.cns = cns
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"RNDS: falha ao resolver CNS no save do Patient (cadastro segue sem CNS)",
		)


def _validate_and_normalize_cpf(doc, fieldname: str, error_msg: str) -> None:
	raw = doc.get(fieldname)
	if not raw:
		return
	digits = re.sub(r"\D", "", raw)
	if not is_valid_cpf(digits):
		frappe.throw(error_msg.format(raw))
	setattr(doc, fieldname, digits)


def _validate_guardian(doc) -> None:
	"""Exige nome + CPF do responsável para pacientes menores de 18 anos."""
	idade = _idade_anos(doc.get("dob"))
	if idade is None or idade >= MAIORIDADE:
		return
	if not doc.get("nome_responsavel"):
		frappe.throw(_("Nome do responsável é obrigatório para pacientes menores de 18 anos."))
	if not doc.get("cpf_responsavel"):
		frappe.throw(_("CPF do responsável é obrigatório para pacientes menores de 18 anos."))


def _validate_address(doc) -> None:
	"""Exige ao menos um Address vinculado ao paciente.

	Pulado no primeiro insert: o Address nativo só pode referenciar o Patient
	depois que este existe (Dynamic Link precisa do nome do paciente). Em
	qualquer save subsequente o endereço passa a ser obrigatório.
	"""
	if doc.is_new():
		return
	if not _has_address(doc.name):
		frappe.throw(_("Endereço é obrigatório. Vincule um Endereço ao paciente."))


def _has_address(patient: str) -> bool:
	return bool(
		frappe.get_all(
			"Dynamic Link",
			filters={
				"link_doctype": "Patient",
				"link_name": patient,
				"parenttype": "Address",
			},
			limit=1,
		)
	)


def _idade_anos(dob) -> int | None:
	"""Idade exata em anos a partir do dob (None se ausente/futuro)."""
	if not dob:
		return None
	nascimento = getdate(dob)
	hoje = getdate(nowdate())
	if nascimento > hoje:
		return None
	return hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))


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
