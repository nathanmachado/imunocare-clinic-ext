"""Catálogo PNI 2026 seed inicial (Fase 1) — 5 vacinas representativas.

Cobertura intencionalmente mínima para validar a arquitetura (ADR-0001).
TODO Fase 1b: expandir para PNI completo (~30 vacinas) com calendário oficial
do Ministério da Saúde — https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/c/calendario-nacional-de-vacinacao

Diversidade coberta nas 5 atuais:
- Dose única (BCG)
- Esquema múltiplo SUS (Hepatite B: 3 doses)
- Esquema múltiplo Particular (Meningocócica B: 3 doses)
- Dose anual / cobertura ampla (Influenza: SUS+Particular)
- Adolescente (HPV Nonavalente)
"""

from __future__ import annotations

ITEM_GROUP_VACINAS = "Vacinas"

# Cada vacina vira: Item + Medication (is_vaccine=1) + Therapy Type
# - code: identificador estável usado como nome do Item / Therapy Type
# - medication_name: nome único da Medication (será usado como Link em Therapy Plan Template Detail)
VACINAS = [
	{
		"code": "imunocare-vacina-bcg",
		"item_name": "Vacina BCG",
		"medication_name": "BCG",
		"codigo_rnds": "19",
		"tipo_imunizacao": "SUS",
		"via_administracao_padrao": "Intradérmica",
		"local_anatomico_padrao": "Deltóide direito",
		"obrigatoria_pni": 1,
		"pni_idade_meses_inicio": 0,
	},
	{
		"code": "imunocare-vacina-hepatite-b",
		"item_name": "Vacina Hepatite B",
		"medication_name": "Hepatite B",
		"codigo_rnds": "45",
		"tipo_imunizacao": "SUS",
		"via_administracao_padrao": "Intramuscular",
		"local_anatomico_padrao": "Vasto lateral direito",
		"obrigatoria_pni": 1,
		"pni_idade_meses_inicio": 0,
	},
	{
		"code": "imunocare-vacina-meningococica-b",
		"item_name": "Vacina Meningocócica B",
		"medication_name": "Meningocócica B",
		"codigo_rnds": "163",
		"tipo_imunizacao": "Particular",
		"via_administracao_padrao": "Intramuscular",
		"local_anatomico_padrao": "Vasto lateral esquerdo",
		"obrigatoria_pni": 0,
		"pni_idade_meses_inicio": 0,
	},
	{
		"code": "imunocare-vacina-influenza-tetravalente",
		"item_name": "Vacina Influenza Tetravalente",
		"medication_name": "Influenza Tetravalente",
		"codigo_rnds": "158",
		"tipo_imunizacao": "Ambas",
		"via_administracao_padrao": "Intramuscular",
		"local_anatomico_padrao": "Deltóide direito",
		"obrigatoria_pni": 1,
		"pni_idade_meses_inicio": 6,
	},
	{
		"code": "imunocare-vacina-hpv-nonavalente",
		"item_name": "Vacina HPV Nonavalente",
		"medication_name": "HPV Nonavalente",
		"codigo_rnds": "165",
		"tipo_imunizacao": "Particular",
		"via_administracao_padrao": "Intramuscular",
		"local_anatomico_padrao": "Deltóide esquerdo",
		"obrigatoria_pni": 0,
		"pni_idade_meses_inicio": 108,  # 9 anos
	},
]

# Calendários PNI biológicos (Therapy Plan Templates com is_pni=1) — SEM preço.
# Os Treatment Plan Templates (combos comerciais com `patient_age_from/to` para
# auto-suggest no Patient Encounter) virão na Fase 5 e apontarão para estes
# Therapy Plan Templates via `items` Dynamic Link.
#
# Campos `idade_meses` e `intervalo_dias` vão em custom fields do
# Therapy Plan Template Detail (criados na Fase 1).
CALENDARIOS = [
	{
		"template_name": "Calendário PNI 0-1 ano",
		"versao_pni": "PNI 2026",
		# Metadata pra Fase 5 (Treatment Plan Template): age_from=0, age_to=1
		"doses": [
			{"medication_name": "BCG", "dose": 1, "idade_meses": 0, "intervalo_dias": 0},
			{"medication_name": "Hepatite B", "dose": 1, "idade_meses": 0, "intervalo_dias": 0},
			{"medication_name": "Hepatite B", "dose": 2, "idade_meses": 2, "intervalo_dias": 30},
			{"medication_name": "Hepatite B", "dose": 3, "idade_meses": 6, "intervalo_dias": 120},
			{"medication_name": "Meningocócica B", "dose": 1, "idade_meses": 3, "intervalo_dias": 0},
			{"medication_name": "Meningocócica B", "dose": 2, "idade_meses": 5, "intervalo_dias": 60},
			{"medication_name": "Meningocócica B", "dose": 3, "idade_meses": 7, "intervalo_dias": 60},
		],
	},
	{
		"template_name": "Calendário Adolescente 9-14 anos",
		"versao_pni": "PNI 2026",
		# Metadata pra Fase 5: age_from=9, age_to=14
		"doses": [
			{"medication_name": "HPV Nonavalente", "dose": 1, "idade_meses": 108, "intervalo_dias": 0},
			{"medication_name": "HPV Nonavalente", "dose": 2, "idade_meses": 110, "intervalo_dias": 60},
			{"medication_name": "HPV Nonavalente", "dose": 3, "idade_meses": 114, "intervalo_dias": 120},
		],
	},
]
