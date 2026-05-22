"""Custom fields para o domínio de imunização — Fase 1 (ADR-0001).

Estende DocTypes nativos do Frappe Healthcare ao invés de criar paralelos.
Aplicado por ``install.install_imunization_customizations`` chamado de
``after_install``, ``after_migrate`` e via patch ``v0_0/0001``.

Idempotente: ``frappe.custom.doctype.custom_field.custom_field.create_custom_fields``
faz upsert por (dt, fieldname).
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
}
