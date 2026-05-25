"""Custom fields para o domínio de imunização — Fases 1 e 2 (ADR-0001).

Estende DocTypes nativos do Frappe Healthcare ao invés de criar paralelos.
Aplicado por ``install.install_imunization_customizations`` chamado de
``after_install``, ``after_migrate`` e via patch ``v0_0/0001``.

Idempotente: ``frappe.custom.doctype.custom_field.custom_field.create_custom_fields``
faz upsert por (dt, fieldname).

- Fase 1: Medication, Therapy Plan Template, Therapy Plan Template Detail.
- Fase 2: Patient (CNS), Drug Prescription (registro de aplicação + RNDS),
  Patient Appointment (modalidade + endereço de aplicação).
"""

from __future__ import annotations

# Strings padronizadas (templates HSM esperam essas strings inteiras).
VIA_OPTIONS = "Intramuscular\nSubcutânea\nIntradérmica\nOral\nNasal"
LOCAL_OPTIONS = (
	"Deltóide direito\nDeltóide esquerdo\n"
	"Vasto lateral direito\nVasto lateral esquerdo\n"
	"Glúteo direito\nGlúteo esquerdo\n"
	"Não se aplica"
)
TIPO_IMUNIZACAO_OPTIONS = "SUS\nParticular\nAmbas"
RNDS_STATUS_OPTIONS = "Não aplicável\nPendente\nEnviado\nErro"
# UI limpa; o helper WhatsApp (Fase 7) converte para "Atendimento CLÍNICA/DOMICILIAR".
MODALIDADE_OPTIONS = "Clínica\nDomiciliar"

CUSTOM_FIELDS = {
	"Medication": [
		{
			"fieldname": "imun_section",
			"label": "Imunização",
			"fieldtype": "Section Break",
			"insert_after": "staff_role",
			"collapsible": 1,
		},
		{
			"fieldname": "is_vaccine",
			"label": "É vacina",
			"fieldtype": "Check",
			"default": "0",
			"insert_after": "imun_section",
			"description": "Marque para incluir esta medicação no catálogo de vacinas (calendário PNI, carteira, RNDS).",
		},
		{
			"fieldname": "codigo_rnds",
			"label": "Código RNDS / CVX",
			"fieldtype": "Data",
			"depends_on": "eval:doc.is_vaccine",
			"insert_after": "is_vaccine",
			"description": "Código oficial CVX para registro no RNDS (DATASUS).",
		},
		{
			"fieldname": "tipo_imunizacao",
			"label": "Tipo",
			"fieldtype": "Select",
			"options": TIPO_IMUNIZACAO_OPTIONS,
			"depends_on": "eval:doc.is_vaccine",
			"insert_after": "codigo_rnds",
		},
		{
			"fieldname": "imun_col_break",
			"fieldtype": "Column Break",
			"insert_after": "tipo_imunizacao",
		},
		{
			"fieldname": "via_administracao_padrao",
			"label": "Via de administração padrão",
			"fieldtype": "Select",
			"options": VIA_OPTIONS,
			"depends_on": "eval:doc.is_vaccine",
			"insert_after": "imun_col_break",
		},
		{
			"fieldname": "local_anatomico_padrao",
			"label": "Local anatômico padrão",
			"fieldtype": "Select",
			"options": LOCAL_OPTIONS,
			"depends_on": "eval:doc.is_vaccine",
			"insert_after": "via_administracao_padrao",
		},
		{
			"fieldname": "obrigatoria_pni",
			"label": "Obrigatória PNI",
			"fieldtype": "Check",
			"default": "0",
			"depends_on": "eval:doc.is_vaccine",
			"insert_after": "local_anatomico_padrao",
		},
		{
			"fieldname": "pni_idade_meses_inicio",
			"label": "Idade início PNI (meses)",
			"fieldtype": "Int",
			"depends_on": "eval:doc.is_vaccine && doc.obrigatoria_pni",
			"insert_after": "obrigatoria_pni",
			"description": "Idade mínima (em meses) para iniciar o esquema vacinal segundo o PNI.",
		},
	],
	"Therapy Plan Template": [
		{
			"fieldname": "imun_section",
			"label": "Calendário PNI",
			"fieldtype": "Section Break",
			"insert_after": "total_amount",
			"collapsible": 1,
		},
		{
			"fieldname": "is_pni",
			"label": "Esquema PNI",
			"fieldtype": "Check",
			"default": "0",
			"insert_after": "imun_section",
			"description": "Marque se este template representa um calendário oficial do PNI brasileiro (não comercial).",
		},
		{
			"fieldname": "versao_pni",
			"label": "Versão PNI",
			"fieldtype": "Data",
			"depends_on": "eval:doc.is_pni",
			"insert_after": "is_pni",
			"description": "Ex.: 'PNI 2026'. Atualize anualmente ao acompanhar mudanças do Ministério da Saúde.",
		},
	],
	"Therapy Plan Template Detail": [
		{
			"fieldname": "medication",
			"label": "Vacina",
			"fieldtype": "Link",
			"options": "Medication",
			"insert_after": "therapy_type",
			"description": "Vacina aplicada nesta linha do calendário. Deve ter is_vaccine=1.",
		},
		{
			"fieldname": "dose_numero",
			"label": "Dose nº",
			"fieldtype": "Int",
			"default": "1",
			"insert_after": "no_of_sessions",
		},
		{
			"fieldname": "intervalo_dias_min",
			"label": "Intervalo mínimo após dose anterior (dias)",
			"fieldtype": "Int",
			"insert_after": "dose_numero",
			"description": "Intervalo mínimo entre esta dose e a anterior. Use 0 para 1ª dose.",
		},
		{
			"fieldname": "idade_meses_ideal",
			"label": "Idade ideal (meses)",
			"fieldtype": "Int",
			"insert_after": "intervalo_dias_min",
			"description": "Idade ideal do paciente para esta dose, segundo PNI.",
		},
	],
	# ---- Fase 2 ----
	"Patient": [
		{
			"fieldname": "cpf",
			"label": "CPF",
			"fieldtype": "Data",
			"insert_after": "uid",
			"unique": 1,
			"reqd": 1,
			"description": "",
		},
		{
			"fieldname": "cns",
			"label": "CNS (Cartão Nacional de Saúde)",
			"fieldtype": "Data",
			"insert_after": "cpf",
			# read_only=0 no schema: o Frappe OCULTA campos read-only vazios no
			# form. Mantemos editável no schema (sempre visível) e tornamos
			# read-only na UI via Client Script (set_df_property no refresh).
			"read_only": 0,
			"description": "Atualizado automaticamente",
		},
		{
			"fieldname": "imun_naturalidade_section",
			"label": "Naturalidade",
			"fieldtype": "Section Break",
			# Após o último campo da seção demográfica (user_id) para NÃO cortar
			# "Patient Demographics" — senão cpf/mobile/phone/email vazam para cá.
			"insert_after": "user_id",
		},
		{
			"fieldname": "pais_nascimento",
			"label": "País de nascimento",
			"fieldtype": "Link",
			"options": "Country",
			"default": "Brazil",
			"reqd": 1,
			"insert_after": "imun_naturalidade_section",
		},
		{
			"fieldname": "cidade_nascimento",
			"label": "Cidade de nascimento",
			"fieldtype": "Data",
			"reqd": 1,
			"insert_after": "pais_nascimento",
		},
		{
			"fieldname": "imun_responsavel_section",
			"label": "Responsável",
			"fieldtype": "Section Break",
			"insert_after": "cidade_nascimento",
		},
		{
			"fieldname": "nome_responsavel",
			"label": "Nome do responsável",
			"fieldtype": "Data",
			"insert_after": "imun_responsavel_section",
			"description": "Obrigatório para pacientes menores de 18 anos.",
		},
		{
			"fieldname": "cpf_responsavel",
			"label": "CPF do responsável",
			"fieldtype": "Data",
			"insert_after": "nome_responsavel",
			"description": "Obrigatório para pacientes menores de 18 anos.",
		},
	],
	"Drug Prescription": [
		{
			"fieldname": "imun_section",
			"label": "Registro de Aplicação (Imunização)",
			"fieldtype": "Section Break",
			"insert_after": "comment",
			"collapsible": 1,
			"depends_on": "eval:doc.medication",
		},
		{
			"fieldname": "dose_numero",
			"label": "Dose nº",
			"fieldtype": "Int",
			"insert_after": "imun_section",
		},
		{
			"fieldname": "lote",
			"label": "Lote",
			"fieldtype": "Data",
			"insert_after": "dose_numero",
		},
		{
			"fieldname": "fabricante",
			"label": "Fabricante",
			"fieldtype": "Data",
			"insert_after": "lote",
		},
		{
			"fieldname": "validade_lote",
			"label": "Validade do lote",
			"fieldtype": "Date",
			"insert_after": "fabricante",
		},
		{
			"fieldname": "imun_col_break",
			"fieldtype": "Column Break",
			"insert_after": "validade_lote",
		},
		{
			"fieldname": "local_anatomico_aplicado",
			"label": "Local anatômico aplicado",
			"fieldtype": "Select",
			"options": LOCAL_OPTIONS,
			"insert_after": "imun_col_break",
		},
		{
			"fieldname": "via_administracao_aplicada",
			"label": "Via de administração aplicada",
			"fieldtype": "Select",
			"options": VIA_OPTIONS,
			"insert_after": "local_anatomico_aplicado",
		},
		{
			"fieldname": "rnds_status",
			"label": "Status RNDS",
			"fieldtype": "Select",
			"options": RNDS_STATUS_OPTIONS,
			"default": "Não aplicável",
			"insert_after": "via_administracao_aplicada",
			"read_only": 1,
			"description": "Atualizado automaticamente pelo envio ao RNDS (Fase 4).",
		},
		{
			"fieldname": "rnds_id",
			"label": "RNDS ID",
			"fieldtype": "Data",
			"insert_after": "rnds_status",
			"read_only": 1,
		},
		{
			"fieldname": "rnds_payload",
			"label": "RNDS Payload (debug)",
			"fieldtype": "Long Text",
			"insert_after": "rnds_id",
			"read_only": 1,
			"hidden": 1,
		},
	],
	"Patient Appointment": [
		{
			"fieldname": "imun_section",
			"label": "Imunização",
			"fieldtype": "Section Break",
			"insert_after": "notes",
			"collapsible": 1,
		},
		{
			"fieldname": "imun_modalidade",
			"label": "Modalidade",
			"fieldtype": "Select",
			"options": MODALIDADE_OPTIONS,
			"default": "Clínica",
			"insert_after": "imun_section",
		},
		{
			"fieldname": "imun_application_address_display",
			"label": "Endereço de aplicação",
			"fieldtype": "Data",
			"insert_after": "imun_modalidade",
			"read_only": 1,
			"length": 140,
			"description": "Preenchido automaticamente: endereço da clínica (modalidade Clínica) ou do paciente (Domiciliar).",
		},
		{
			"fieldname": "imun_vaccines",
			"label": "Vacinas do agendamento",
			"fieldtype": "Table",
			"options": "Imunocare Appointment Vaccine",
			"insert_after": "imun_application_address_display",
			"description": "Vacinas planejadas para este atendimento (fonte da variável de vacinas dos templates WhatsApp).",
		},
	],
	# ---- Fase 5 ----
	"Treatment Plan Template": [
		{
			"fieldname": "is_vaccine_combo",
			"label": "Combo de vacinas",
			"fieldtype": "Check",
			"default": "0",
			"insert_after": "template_name",
			"description": "Marque para combos comerciais de vacinas (ex.: Meningite B 3 doses).",
		},
		{
			"fieldname": "vaccination_schedule",
			"label": "Esquema vacinal (calendário)",
			"fieldtype": "Link",
			"options": "Therapy Plan Template",
			"depends_on": "eval:doc.is_vaccine_combo",
			"insert_after": "is_vaccine_combo",
			"description": "Calendário biológico (Therapy Plan Template is_pni) cujas doses serão agendadas na compra.",
		},
	],
	"Medication Request": [
		{
			"fieldname": "dose_numero",
			"label": "Dose nº",
			"fieldtype": "Int",
			"insert_after": "medication",
		},
		{
			"fieldname": "therapy_plan",
			"label": "Plano de Tratamento (compra)",
			"fieldtype": "Link",
			"options": "Therapy Plan",
			"insert_after": "dose_numero",
		},
	],
	"Healthcare Practitioner": [
		{
			"fieldname": "cns",
			"label": "CNS (Cartão Nacional de Saúde)",
			"fieldtype": "Data",
			"insert_after": "employee",
			# read_only=0 no schema (Frappe oculta read-only vazio) + read-only na
			# UI via Client Script. Resolvido do RNDS pelo CPF do colaborador.
			"read_only": 0,
			"description": "Atualizado automaticamente (RNDS, a partir do CPF do colaborador).",
		},
	],
	"Employee": [
		{
			"fieldname": "cpf",
			"label": "CPF",
			"fieldtype": "Data",
			"insert_after": "date_of_birth",
			"reqd": 1,
			"description": "",
		},
	],
}
