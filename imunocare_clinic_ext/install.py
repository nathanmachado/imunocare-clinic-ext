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
	_register_dashboard()
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

		// Carteira de Vacinação: renderizada na aba (campo HTML imun_carteira_html).
		if (!frm.is_new()) {
			imunocare_render_carteira(frm);
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

function imunocare_render_carteira(frm) {
	const field = frm.get_field('imun_carteira_html');
	if (!field) return;
	frappe.call({
		method: 'imunocare_clinic_ext.api.vaccine_card.get_vaccine_card',
		args: { patient: frm.doc.name },
		callback: (r) => {
			const card = r.message || {};
			const cores = { 'Aplicada': 'green', 'Pendente': 'orange', 'Atrasada': 'red', 'Futura': 'gray' };
			const resumo = card.resumo || {};
			const idade = card.idade_meses != null
				? Math.floor(card.idade_meses / 12) + 'a ' + (card.idade_meses % 12) + 'm' : '—';

			let chips = '';
			['Aplicada', 'Pendente', 'Atrasada', 'Futura'].forEach((s) => {
				chips += `<span class="indicator-pill ${cores[s]}" style="margin-right:8px">${s}: ${resumo[s] || 0}</span>`;
			});

			let linhas = '';
			(card.doses || []).forEach((d) => {
				const dt = d.data_aplicacao ? frappe.datetime.str_to_user(d.data_aplicacao) : '';
				linhas += `<tr>
					<td>${frappe.utils.escape_html(d.vacina || '')}</td>
					<td style="text-align:center">${d.dose_numero || ''}</td>
					<td><span class="indicator-pill ${cores[d.status] || 'gray'}">${d.status}</span></td>
					<td>${dt}</td>
					<td>${frappe.utils.escape_html(d.lote || '')}</td>
					<td>${frappe.utils.escape_html(d.responsavel || '')}</td>
					<td>${frappe.utils.escape_html(d.calendario || '')}</td>
				</tr>`;
			});

			const html = `
				<div style="margin-bottom:12px">
					<b>${frappe.utils.escape_html(card.patient_name || '')}</b> &middot; ${idade}
				</div>
				<div style="margin-bottom:16px">${chips}</div>
				<table class="table table-bordered" style="font-size:13px">
					<thead><tr>
						<th>Vacina</th><th>Dose</th><th>Situação</th><th>Aplicada em</th><th>Lote</th><th>Responsável</th><th>Calendário</th>
					</tr></thead>
					<tbody>${linhas || '<tr><td colspan="7">Nenhuma dose no calendário PNI.</td></tr>'}</tbody>
				</table>`;
			field.$wrapper.html(html);
		},
	});
}
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


# ---------------------------------------------------------------------------
# Dashboard de Imunização (Fase 10) — Number Cards + Workspace, tudo no banco.
# Reuso máximo (ver feedback_reuse_first): Calendar View nativa do Patient
# Appointment, Script Reports e estoque do Bin. Nenhuma UI compilada.
# ---------------------------------------------------------------------------

_NC_ATEND_SEMANA = "Imunocare - Atendimentos da Semana"
_NC_DOMICILIAR = "Imunocare - Domiciliares da Semana"
_NC_ATRASADOS_PAGOS = "Imunocare - Atrasados Pagos"
_NC_VACINAS_FALTA = "Imunocare - Vacinas em Falta"
_NC_VACINAS_REPOR = "Imunocare - Vacinas a Repor"
_WORKSPACE_NAME = "Imunização"
_HEALTHCARE_CARD_LABEL = "Imunização"
_REPORT_PROJECAO = "Projeção de Estoque de Vacinas"

# (name, type, document_type, function, filters_json, method, color)
_NUMBER_CARDS = [
	(_NC_ATEND_SEMANA, "Document Type", "Patient Appointment", "Count",
	 [["appointment_date", "Timespan", "this week"]], None, "#449CF0"),
	(_NC_DOMICILIAR, "Document Type", "Patient Appointment", "Count",
	 [["appointment_date", "Timespan", "this week"], ["imun_modalidade", "=", "Domiciliar"]], None, "#7C4DFF"),
	(_NC_ATRASADOS_PAGOS, "Custom", "Patient Appointment", "Count",
	 None, "imunocare_clinic_ext.api.dashboard.atrasados_pagos", "#E24C4C"),
	(_NC_VACINAS_FALTA, "Custom", "Medication", "Count",
	 None, "imunocare_clinic_ext.api.dashboard.vacinas_em_falta", "#F8814F"),
	(_NC_VACINAS_REPOR, "Custom", "Medication", "Count",
	 None, "imunocare_clinic_ext.api.dashboard.vacinas_a_repor", "#B8860B"),
]


def _register_dashboard() -> None:
	"""Cria/atualiza Number Cards, a Workspace 'Imunização' e injeta o bloco
	'Imunização' na home do módulo Healthcare. Idempotente."""
	if not frappe.db.exists("DocType", "Patient Appointment"):
		return  # Healthcare ainda não instalado (primeira passada).
	_upsert_number_cards()
	_upsert_workspace()
	_inject_into_healthcare_workspace()


def _upsert_number_cards() -> None:
	for name, ctype, doctype, func, filters, method, color in _NUMBER_CARDS:
		if frappe.db.exists("Number Card", name):
			doc = frappe.get_doc("Number Card", name)
		else:
			doc = frappe.new_doc("Number Card")
			doc.name = name
			# Number Card.autoname() sobrescreve o name pelo label; trava o name.
			doc.flags.name_set = True
		doc.label = name.replace("Imunocare - ", "")
		doc.type = ctype
		doc.document_type = doctype
		doc.function = func
		doc.is_public = 1
		doc.show_percentage_stats = 0
		doc.color = color
		doc.filters_json = frappe.as_json(filters) if filters else "[]"
		doc.method = method or ""
		doc.save(ignore_permissions=True)
		# O frappe.db.exists acima cacheia um miss negativo para este nome; a
		# validação de link da Workspace usa get_value(cache=True) e pegaria
		# esse miss. Limpa o cache do documento para o link ser resolvido.
		frappe.clear_document_cache("Number Card", doc.name)


def _workspace_content() -> str:
	"""Blocos de layout da Workspace 'Imunização'."""
	blocks = [
		{"id": "imun_hdr", "type": "header",
		 "data": {"text": "<span class='h4'><b>Imunização — Painel Operacional</b></span>", "col": 12}},
		{"id": "imun_nc1", "type": "number_card", "data": {"number_card_name": _NC_ATEND_SEMANA, "col": 3}},
		{"id": "imun_nc2", "type": "number_card", "data": {"number_card_name": _NC_ATRASADOS_PAGOS, "col": 3}},
		{"id": "imun_nc3", "type": "number_card", "data": {"number_card_name": _NC_VACINAS_FALTA, "col": 3}},
		{"id": "imun_nc5", "type": "number_card", "data": {"number_card_name": _NC_VACINAS_REPOR, "col": 3}},
		{"id": "imun_nc4", "type": "number_card", "data": {"number_card_name": _NC_DOMICILIAR, "col": 3}},
		{"id": "imun_sc1", "type": "shortcut", "data": {"shortcut_name": "Agenda da Semana", "col": 3}},
		{"id": "imun_sc2", "type": "shortcut", "data": {"shortcut_name": "Calendário", "col": 3}},
		{"id": "imun_sc4", "type": "shortcut", "data": {"shortcut_name": "Projeção de Estoque", "col": 3}},
		{"id": "imun_sc3", "type": "shortcut", "data": {"shortcut_name": "Retornos Pendentes", "col": 3}},
		{"id": "imun_card", "type": "card", "data": {"card_name": "Cadastros de Imunização", "col": 6}},
	]
	return frappe.as_json(blocks)


def _upsert_workspace() -> None:
	if frappe.db.exists("Workspace", _WORKSPACE_NAME):
		doc = frappe.get_doc("Workspace", _WORKSPACE_NAME)
		doc.set("links", [])
		doc.set("shortcuts", [])
		doc.set("number_cards", [])
		doc.set("charts", [])
	else:
		doc = frappe.new_doc("Workspace")
		doc.name = _WORKSPACE_NAME

	doc.label = _WORKSPACE_NAME
	doc.title = _WORKSPACE_NAME
	doc.module = "Imunocare Clinic Ext"
	doc.public = 1
	doc.icon = "heart"
	doc.parent_page = "Healthcare" if frappe.db.exists("Workspace", "Healthcare") else ""
	doc.content = _workspace_content()

	for nc in (_NC_ATEND_SEMANA, _NC_ATRASADOS_PAGOS, _NC_VACINAS_FALTA, _NC_VACINAS_REPOR, _NC_DOMICILIAR):
		doc.append("number_cards", {"label": nc, "number_card_name": nc})

	doc.append("shortcuts", {
		"type": "Report", "label": "Agenda da Semana", "link_to": "Agenda de Imunização",
		"report_ref_doctype": "Patient Appointment", "color": "Green",
	})
	doc.append("shortcuts", {
		"type": "DocType", "label": "Calendário", "link_to": "Patient Appointment",
		"doc_view": "Calendar", "color": "Blue",
	})
	doc.append("shortcuts", {
		"type": "Report", "label": "Projeção de Estoque", "link_to": _REPORT_PROJECAO,
		"report_ref_doctype": "Patient Appointment", "color": "Yellow",
	})
	doc.append("shortcuts", {
		"type": "Report", "label": "Retornos Pendentes", "link_to": "Retornos Pendentes",
		"report_ref_doctype": "Medication Request", "color": "Orange",
	})

	# Card "Cadastros de Imunização": Card Break + Links (DocTypes nativos).
	doc.append("links", {"type": "Card Break", "label": "Cadastros de Imunização", "link_count": 4})
	for label, link_to, link_type, is_qr in (
		("Agendamentos", "Patient Appointment", "DocType", 0),
		("Reações Adversas", "Adverse Reaction", "DocType", 0),
		("Vacinas (Medication)", "Medication", "DocType", 0),
		("Calendários PNI", "Therapy Plan Template", "DocType", 0),
	):
		doc.append("links", {
			"type": "Link", "label": label, "link_to": link_to,
			"link_type": link_type, "is_query_report": is_qr, "hidden": 0, "onboard": 0, "link_count": 0,
		})

	doc.save(ignore_permissions=True)


def _inject_into_healthcare_workspace() -> None:
	"""Adiciona o bloco/card 'Imunização' na home do módulo Healthcare.

	Re-aplicado a cada ``after_migrate`` para sobreviver à re-sincronização da
	Workspace padrão do Healthcare. Idempotente: pula se o card já existe.
	"""
	if not frappe.db.exists("Workspace", "Healthcare"):
		return
	hc = frappe.get_doc("Workspace", "Healthcare")

	desejados = [
		("Agenda de Imunização", "Agenda de Imunização", "Report", 1),
		("Projeção de Estoque de Vacinas", _REPORT_PROJECAO, "Report", 1),
		("Retornos Pendentes", "Retornos Pendentes", "Report", 1),
		("Reações Adversas", "Adverse Reaction", "DocType", 0),
	]

	tem_card = any(l.type == "Card Break" and l.label == _HEALTHCARE_CARD_LABEL for l in hc.links)
	dirty = False

	if not tem_card:
		hc.append("links", {"type": "Card Break", "label": _HEALTHCARE_CARD_LABEL, "link_count": len(desejados)})
		dirty = True

	# Idempotente por link: adiciona só os que ainda faltam (cobre upgrades onde
	# o card já existia com menos links).
	existentes = {l.label for l in hc.links if l.type == "Link"}
	for label, link_to, link_type, is_qr in desejados:
		if label in existentes:
			continue
		hc.append("links", {
			"type": "Link", "label": label, "link_to": link_to,
			"link_type": link_type, "is_query_report": is_qr, "hidden": 0, "onboard": 0, "link_count": 0,
		})
		dirty = True

	# Bloco visual 'card' ao final do content da Healthcare (só uma vez).
	content = frappe.parse_json(hc.content or "[]")
	if not any(b.get("id") == "imun_hc_card" for b in content):
		content.append({"id": "imun_hc_card", "type": "card",
						"data": {"card_name": _HEALTHCARE_CARD_LABEL, "col": 4}})
		hc.content = frappe.as_json(content)
		dirty = True

	if dirty:
		hc.save(ignore_permissions=True)


def after_install() -> None:
	"""Hook ``after_install``: roda na primeira instalação do app no site."""
	install_imunization_customizations()


def after_migrate() -> None:
	"""Hook ``after_migrate``: cobertura para sites com app já instalado.

	Garante que custom fields novos adicionados ao ``custom_fields.py`` entre
	migrações sejam aplicados sem depender de execução manual do patch.
	"""
	install_imunization_customizations()
