"""Seed do calendário PNI 2026 (Fase 1) — idempotente. **Só roda em testes.**

Cria/atualiza Items, Medications (is_vaccine=1), Therapy Types e Therapy Plan
Templates (is_pni=1) a partir de ``data/pni_2026.py``.

Idempotência: cada peça é criada apenas se ainda não existir (lookup por
nome). Custom fields aplicados separadamente em ``install.install_imunization_customizations``.

DESATIVADO fora de testes em 2026-06-06: os cadastros semeados eram de
validação e foram apagados de produção; o catálogo passou a ser mantido
manualmente pelo operador com os nomes corretos. Em ``frappe.flags.in_test``
o install ainda chama o seed (as suítes Fase 2/5/10/12 dependem do catálogo
de referência). Rodável manualmente via
``bench execute imunocare_clinic_ext.seed.seed_pni_2026`` se um dia for útil.
"""

from __future__ import annotations

import frappe

from imunocare_clinic_ext.data.pni_2026 import (
	CALENDARIOS,
	ITEM_GROUP_VACINAS,
	VACINAS,
)

_STOCK_UOM_DEFAULT = "Unidade"
_MEDICATION_CLASS_VACINAS = "Vacinas"


def seed_pni_2026() -> None:
	"""Entry-point idempotente do seed."""
	if not _custom_fields_ready():
		# Custom fields ainda não instalados → install.py vai chamar de novo
		# após a primeira passada do create_custom_fields. Sair silenciosamente.
		return

	_ensure_item_group(ITEM_GROUP_VACINAS)
	_ensure_medication_class(_MEDICATION_CLASS_VACINAS)
	for vacina in VACINAS:
		_ensure_item(vacina)
		_ensure_medication(vacina)
		_ensure_therapy_type(vacina)
	for calendario in CALENDARIOS:
		_ensure_therapy_plan_template(calendario)


def _custom_fields_ready() -> bool:
	"""Checa se os custom fields críticos do seed já existem no schema."""
	return bool(
		frappe.db.exists("Custom Field", {"dt": "Medication", "fieldname": "is_vaccine"})
		and frappe.db.exists("Custom Field", {"dt": "Therapy Plan Template", "fieldname": "is_pni"})
		and frappe.db.exists(
			"Custom Field", {"dt": "Therapy Plan Template Detail", "fieldname": "medication"}
		)
	)


def _ensure_item_group(name: str) -> None:
	if frappe.db.exists("Item Group", name):
		return
	frappe.get_doc(
		{
			"doctype": "Item Group",
			"item_group_name": name,
			"is_group": 0,
			"parent_item_group": "All Item Groups",
		}
	).insert(ignore_permissions=True)


def _ensure_medication_class(name: str) -> None:
	if frappe.db.exists("Medication Class", name):
		return
	frappe.get_doc(
		{
			"doctype": "Medication Class",
			"medication_class": name,
		}
	).insert(ignore_permissions=True)


def _ensure_item(vacina: dict) -> None:
	if frappe.db.exists("Item", vacina["code"]):
		return
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": vacina["code"],
			"item_name": vacina["item_name"],
			"item_group": ITEM_GROUP_VACINAS,
			"stock_uom": _STOCK_UOM_DEFAULT,
			"is_stock_item": 1,
			"include_item_in_manufacturing": 0,
			"description": vacina["item_name"],
		}
	).insert(ignore_permissions=True)


def _ensure_medication(vacina: dict) -> None:
	if frappe.db.exists("Medication", vacina["medication_name"]):
		return
	doc = frappe.get_doc(
		{
			"doctype": "Medication",
			"name": vacina["medication_name"],
			"generic_name": vacina["medication_name"],
			"medication_class": _MEDICATION_CLASS_VACINAS,
			"strength": 0.5,
			"strength_uom": _STOCK_UOM_DEFAULT,
			"is_vaccine": 1,
			"codigo_rnds": vacina["codigo_rnds"],
			"tipo_imunizacao": vacina["tipo_imunizacao"],
			"via_administracao_padrao": vacina["via_administracao_padrao"],
			"local_anatomico_padrao": vacina["local_anatomico_padrao"],
			"obrigatoria_pni": vacina["obrigatoria_pni"],
			"pni_idade_meses_inicio": vacina.get("pni_idade_meses_inicio") or 0,
			"linked_items": [
				{
					"item_code": vacina["code"],
					"item_group": ITEM_GROUP_VACINAS,
					"stock_uom": _STOCK_UOM_DEFAULT,
					"is_billable": 1,
				}
			],
		}
	)
	doc.insert(ignore_permissions=True)


def _ensure_therapy_type(vacina: dict) -> None:
	"""Cria Therapy Type 'Aplicação - <vacina>'.

	Therapy Type.after_insert do Healthcare cria automaticamente um Item de
	serviço (is_service_item=1, is_stock_item=0) usando ``item_code`` e
	``item_name`` do Therapy Type. Esse item de SERVIÇO é DIFERENTE do Item
	de INSUMO criado em ``_ensure_item`` — o de insumo é estocável (a vacina
	física), o de serviço é a cobrança pela aplicação.
	"""
	therapy_type_name = f"Aplicação - {vacina['medication_name']}"
	if frappe.db.exists("Therapy Type", therapy_type_name):
		return
	service_item_code = f"aplicacao-{vacina['code']}"
	frappe.get_doc(
		{
			"doctype": "Therapy Type",
			"therapy_type": therapy_type_name,
			"item_code": service_item_code,
			"item_name": therapy_type_name,
			"item_group": ITEM_GROUP_VACINAS,
			"is_billable": 1,
			"default_duration": 10,
			"description": f"Procedimento de aplicação da vacina {vacina['medication_name']}.",
		}
	).insert(ignore_permissions=True)


def _ensure_therapy_plan_template(calendario: dict) -> None:
	if frappe.db.exists("Therapy Plan Template", calendario["template_name"]):
		return
	therapy_types = []
	for dose in calendario["doses"]:
		therapy_type_name = f"Aplicação - {dose['medication_name']}"
		therapy_types.append(
			{
				"therapy_type": therapy_type_name,
				"no_of_sessions": 1,
				"medication": dose["medication_name"],
				"dose_numero": dose["dose"],
				"intervalo_dias_min": dose["intervalo_dias"],
				"idade_meses_ideal": dose["idade_meses"],
			}
		)
	frappe.get_doc(
		{
			"doctype": "Therapy Plan Template",
			"plan_name": calendario["template_name"],
			"item_code": f"plano-{calendario['template_name'].lower().replace(' ', '-')}",
			"item_name": calendario["template_name"],
			"item_group": ITEM_GROUP_VACINAS,
			"description": f"Calendário vacinal PNI — {calendario['template_name']}",
			"is_pni": 1,
			"versao_pni": calendario["versao_pni"],
			"therapy_types": therapy_types,
		}
	).insert(ignore_permissions=True)
