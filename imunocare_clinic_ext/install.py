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

# Property setters em campos NATIVOS (não são custom fields).
# (doctype, fieldname, property, value, property_type)
NATIVE_PROPERTY_SETTERS = [
	# UID genérico do Patient — CPF é o documento primário (ver ADR-0001).
	("Patient", "uid", "hidden", "1", "Check"),
	# Campos obrigatórios no cadastro do paciente (first_name já é reqd nativo).
	("Patient", "middle_name", "reqd", "1", "Check"),
	("Patient", "last_name", "reqd", "1", "Check"),
	("Patient", "dob", "reqd", "1", "Check"),
	("Patient", "mobile", "reqd", "1", "Check"),
	("Patient", "email", "reqd", "1", "Check"),
	# Label sem "(opcional)" agora que middle_name é obrigatório.
	("Patient", "middle_name", "label", "Nome do Meio", "Data"),
	# Seção demográfica renomeada para "Paciente".
	("Patient", "basic_info", "label", "Paciente", "Data"),
	# Labels com termos mais claros / corrigindo tradução pt-BR ruim.
	("Patient", "mobile", "label", "Celular / Whatsapp", "Data"),
	("Patient", "report_preference", "label", "Preferência de Relatório", "Data"),
	# Colaborador (Employee) obrigatório no cadastro do profissional de saúde.
	("Healthcare Practitioner", "employee", "reqd", "1", "Check"),
]

# Custom fields obsoletos a remover (idempotente).
OBSOLETE_CUSTOM_FIELDS = [
	# CPF migrou de Healthcare Practitioner para Employee (cadastro primário).
	("Healthcare Practitioner", "cpf"),
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
	_remove_obsolete_fields()
	_apply_property_setters()
	_register_patient_history_doctypes()
	_register_client_scripts()
	frappe.clear_cache()


def _remove_obsolete_fields() -> None:
	"""Remove custom fields que foram movidos/descontinuados (idempotente)."""
	for dt, fieldname in OBSOLETE_CUSTOM_FIELDS:
		name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": fieldname})
		if name:
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)

	# Import tardio: seed precisa que os custom fields existam no schema.
	from imunocare_clinic_ext.seed import seed_pni_2026

	seed_pni_2026()


def _apply_property_setters() -> None:
	"""Aplica Property Setters em campos nativos (idempotente)."""
	for doctype, fieldname, prop, value, prop_type in NATIVE_PROPERTY_SETTERS:
		make_property_setter(
			doctype,
			fieldname,
			prop,
			value,
			prop_type,
			for_doctype=False,
			validate_fields_for_doctype=False,
		)


_PATIENT_CNS_SCRIPT_NAME = "Imunocare - Patient Buscar CNS RNDS"
_PATIENT_CNS_SCRIPT = """
frappe.ui.form.on('Patient', {
	refresh(frm) {
		// CNS editável quando VAZIO (entrada manual de fallback) e read-only
		// quando preenchido (protege o valor resolvido/digitado). NÃO usar
		// set_df_property('read_only') — o Frappe oculta read-only vazio.
		const f = frm.get_field('cns');
		if (f && f.$input) {
			const locked = !!frm.doc.cns;
			f.$input.attr('readonly', locked);
			f.$input.css('background-color', locked ? 'var(--disabled-control-bg)' : '');
		}
	},
	before_save(frm) {
		// Resolução do CNS no RNDS roda no validate server-side só quando vazio.
		if (frm.doc.cpf && !frm.doc.cns) {
			frappe.show_alert(
				{ message: __('Consultando CNS no RNDS antes de salvar...'), indicator: 'blue' },
				10
			);
		}
	},
});
""".strip()


_PRACTITIONER_CNS_SCRIPT_NAME = "Imunocare - Practitioner CNS RNDS"
_PRACTITIONER_CNS_SCRIPT = """
frappe.ui.form.on('Healthcare Practitioner', {
	refresh(frm) {
		// CNS editável quando vazio (fallback manual), read-only quando preenchido.
		const f = frm.get_field('cns');
		if (f && f.$input) {
			const locked = !!frm.doc.cns;
			f.$input.attr('readonly', locked);
			f.$input.css('background-color', locked ? 'var(--disabled-control-bg)' : '');
		}
	},
	before_save(frm) {
		if (frm.doc.employee && !frm.doc.cns) {
			frappe.show_alert(
				{ message: __('Consultando CNS do profissional no RNDS antes de salvar...'), indicator: 'blue' },
				10
			);
		}
	},
});
""".strip()


def _register_client_scripts() -> None:
	"""Cria/atualiza Client Scripts (idempotente). Armazenados no DB — não
	dependem de build de assets, ideal para deploy em produção Docker."""
	if not frappe.db.exists("DocType", "Client Script"):
		return
	for name, dt, script in (
		(_PATIENT_CNS_SCRIPT_NAME, "Patient", _PATIENT_CNS_SCRIPT),
		(_PRACTITIONER_CNS_SCRIPT_NAME, "Healthcare Practitioner", _PRACTITIONER_CNS_SCRIPT),
	):
		if frappe.db.exists("Client Script", name):
			doc = frappe.get_doc("Client Script", name)
		else:
			doc = frappe.new_doc("Client Script")
			doc.name = name
		doc.dt = dt
		doc.view = "Form"
		doc.enabled = 1
		doc.script = script
		doc.save(ignore_permissions=True)


def _register_patient_history_doctypes() -> None:
	"""Adiciona Adverse Reaction à timeline do paciente (Patient History).

	Idempotente: só insere a linha em ``custom_doctypes`` se ainda não existir.
	Pulado se o DocType ainda não foi migrado (primeira passada do install).
	"""
	if not frappe.db.exists("DocType", "Adverse Reaction"):
		return
	if not frappe.db.exists("DocType", "Patient History Settings"):
		return

	settings = frappe.get_single("Patient History Settings")
	already = any(d.document_type == "Adverse Reaction" for d in settings.custom_doctypes)
	if already:
		return

	settings.append(
		"custom_doctypes",
		{
			"document_type": "Adverse Reaction",
			"date_fieldname": "data_inicio",
			"selected_fields": frappe.as_json(
				[
					{"label": "Gravidade", "fieldname": "gravidade", "fieldtype": "Select"},
					{"label": "Sintomas", "fieldname": "sintomas", "fieldtype": "Small Text"},
					{"label": "Vacina/Medicação suspeita", "fieldname": "medication", "fieldtype": "Link"},
					{"label": "Desfecho", "fieldname": "desfecho", "fieldtype": "Select"},
				]
			),
		},
	)
	settings.save(ignore_permissions=True)


def after_install() -> None:
	"""Hook ``after_install``: roda na primeira instalação do app no site."""
	install_imunization_customizations()


def after_migrate() -> None:
	"""Hook ``after_migrate``: cobertura para sites com app já instalado.

	Garante que custom fields novos adicionados ao ``custom_fields.py`` entre
	migrações sejam aplicados sem depender de execução manual do patch.
	"""
	install_imunization_customizations()
