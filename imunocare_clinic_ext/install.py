"""Install hooks para imunocare_clinic_ext.

``install_imunization_customizations`` é idempotente e pode ser chamado:
- via ``after_install`` (instalação inicial do app no site)
- via ``after_migrate`` (cobertura para sites antigos que migrarem com app já instalado)
- via patch ``v0_0/0001`` (cobertura explícita por versão).
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from imunocare_clinic_ext.custom_fields import CUSTOM_FIELDS


def install_imunization_customizations() -> None:
	"""Instala/atualiza custom fields + seed PNI 2026 do domínio de imunização.

	Idempotente:
	- ``create_custom_fields`` faz upsert por (dt, fieldname).
	- ``seed_pni_2026`` checa existência antes de criar cada Item/Medication/
	  Therapy Type/Therapy Plan Template.

	Após custom fields, faz ``frappe.clear_cache`` para que o seed enxergue
	o novo schema (campos como ``is_vaccine`` em Medication).
	"""
	create_custom_fields(CUSTOM_FIELDS, update=True)
	frappe.clear_cache()

	# Import tardio: seed precisa que os custom fields existam no schema.
	from imunocare_clinic_ext.seed import seed_pni_2026

	seed_pni_2026()


def after_install() -> None:
	"""Hook ``after_install``: roda na primeira instalação do app no site."""
	install_imunization_customizations()


def after_migrate() -> None:
	"""Hook ``after_migrate``: cobertura para sites com app já instalado.

	Garante que custom fields novos adicionados ao ``custom_fields.py`` entre
	migrações sejam aplicados sem depender de execução manual do patch.
	"""
	install_imunization_customizations()
