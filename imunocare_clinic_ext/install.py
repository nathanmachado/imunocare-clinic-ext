"""Install hooks para imunocare_clinic_ext.

``install_imunization_customizations`` é idempotente e pode ser chamado:
- via ``after_install`` (instalação inicial do app no site)
- via ``after_migrate`` (cobertura para sites antigos que migrarem com app já instalado)
- via patch ``v0_0/0001`` (cobertura explícita por versão).
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from imunocare_clinic_ext.custom_fields import CUSTOM_FIELDS

# Campos nativos escondidos da UI por serem redundantes no contexto Imunocare.
# (doctype, fieldname, property, value, property_type)
HIDDEN_NATIVE_FIELDS = [
	# UID genérico do Patient — CPF é o documento primário (ver ADR-0001).
	("Patient", "uid", "hidden", "1", "Check"),
]


def install_imunization_customizations() -> None:
	"""Instala/atualiza custom fields + property setters + seed PNI do domínio.

	Idempotente:
	- ``create_custom_fields`` faz upsert por (dt, fieldname).
	- ``make_property_setter`` faz upsert por (doctype, field, property).
	- ``seed_pni_2026`` checa existência antes de criar cada Item/Medication/
	  Therapy Type/Therapy Plan Template.

	Após custom fields, faz ``frappe.clear_cache`` para que o seed enxergue
	o novo schema (campos como ``is_vaccine`` em Medication).
	"""
	create_custom_fields(CUSTOM_FIELDS, update=True)
	_apply_property_setters()
	frappe.clear_cache()

	# Import tardio: seed precisa que os custom fields existam no schema.
	from imunocare_clinic_ext.seed import seed_pni_2026

	seed_pni_2026()


def _apply_property_setters() -> None:
	"""Aplica Property Setters em campos nativos (idempotente)."""
	for doctype, fieldname, prop, value, prop_type in HIDDEN_NATIVE_FIELDS:
		make_property_setter(
			doctype,
			fieldname,
			prop,
			value,
			prop_type,
			for_doctype=False,
			validate_fields_for_doctype=False,
		)


def after_install() -> None:
	"""Hook ``after_install``: roda na primeira instalação do app no site."""
	install_imunization_customizations()


def after_migrate() -> None:
	"""Hook ``after_migrate``: cobertura para sites com app já instalado.

	Garante que custom fields novos adicionados ao ``custom_fields.py`` entre
	migrações sejam aplicados sem depender de execução manual do patch.
	"""
	install_imunization_customizations()
