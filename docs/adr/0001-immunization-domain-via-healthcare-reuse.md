# ADR-0001 — Modelagem do domínio de imunização via reuso do Frappe Healthcare

- **Status**: Accepted
- **Data**: 2026-05-22
- **Decisores**: Nathan Machado (Imunocare), Claude
- **Escopo**: Aplicação `imunocare_clinic_ext`

## Contexto

Imunocare precisa que o ERP cubra a gestão completa de uma clínica de vacinas e aplicação de medicamentos no Brasil. Os requisitos elicitados:

1. Carteira de vacinação do paciente (SUS + Particular) com calendário PNI brasileiro: aplicadas, pendentes, possíveis por data.
2. Gerenciamento de reações adversas a aplicações.
3. Conexão automática com RNDS (Rede Nacional de Dados em Saúde, DATASUS) — registro FHIR R4 das doses aplicadas.
4. Painel de retornos pendentes: pacientes com dose vencida/próxima, dias de atraso, status de pagamento.
5. Venda de combos/pacotes (ex.: Meningite B nos meses 3, 5 e 7; calendário 3-18 meses) com auto-agendamento de doses e atualização da carteira.
6. Disparos automáticos via WhatsApp para lembretes, confirmações e cobrança de retorno.

A primeira pergunta era se valeria a pena criar um app `imunocare_immunization` greenfield com 6-7 DocTypes próprios (`Vaccine`, `Vaccine Dose Schedule`, `Patient Immunization`, `Vaccine Package`, `Patient Vaccine Purchase`, `Adverse Reaction`, `RNDS Settings`).

Levantamento do upstream em 2026-05-22 (Frappe v15 + Healthcare 15.1.18) revelou que o domínio é largamente coberto por DocTypes existentes, e que a proposta greenfield criaria retrabalho massivo + dívida de manutenção (cada release do Healthcare poderia introduzir features sobrepostas).

## Decisão

Modelar o domínio de imunização **reusando ao máximo o Frappe Healthcare**, com apenas 2 DocTypes verdadeiramente novos e 18 custom fields distribuídos. Toda a customização vai no app `imunocare_clinic_ext`.

### Mapeamento conceito → upstream

| Conceito | Solução | Justificativa |
|---|---|---|
| **Vacina (catálogo)** | `Medication` + `Medication Linked Item` (já existe vínculo Medication↔Item) | Medication é um produto farmacêutico arbitrário; vacina cabe no conceito. Item dá estoque e venda nativos. |
| **Esquema de doses PNI** | `Therapy Plan Template` + `Therapy Plan Template Detail` (já tem `therapy_type`, `no_of_sessions`, `rate`) | Template de sessões temporais é exatamente "N doses ao longo do tempo". Custom field adiciona `intervalo_dias_min` e `idade_meses_ideal`. |
| **Combo/pacote comercial** | `Treatment Plan Template` (já tem `drugs` Table = Drug Prescription, `items` Dynamic Link, `patient_age_from/to`, `gender`) | Suporta combo medicamentoso com critérios de aplicabilidade. Botão nativo `get_applicable_treatment_plans` no Patient Encounter sugere combos automaticamente — zero código custom pra sugestão. |
| **Compra do paciente** | `Therapy Plan` (instância nativa de Therapy Plan Template) + Sales Invoice | Fluxo Healthcare já gera Therapy Plan ao aplicar Treatment Plan Template no Encounter. |
| **Aplicação individual** | `Patient Encounter.drug_prescription` (Table → `Drug Prescription`) | Já aceita múltiplas Drug Prescriptions por encontro — resolve "agendamento com múltiplas vacinas" nativamente. Cada drug_prescription = uma vacina aplicada. |
| **Dose futura agendada / retorno** | `Medication Request` (já tem `medication`, `patient`, `expected_date`, `status`, `billing_status`, `order_group=Encounter`) | FHIR-style request. `expected_date` é literalmente "quando aplicar". `billing_status` Select (Pending/Partly Invoiced/Invoiced) cobre o "pago/a pagar" sem custom field. |
| **Carteira de Vacinação (UI)** | `Patient History Settings` (adicionar Drug Prescription ao histórico) + custom Vue page renderizando calendário PNI | Sem novo DocType. Query sobre Drug Prescription filtrando `medication` com `is_vaccine=1`. |
| **Retornos pendentes (UI)** | Report builder query sobre `Medication Request WHERE expected_date <= TODAY AND status NOT IN (Completed, Cancelled)` | Sem novo DocType. Filtros nativos. |
| **Modalidade / endereço / pagamento** | Custom fields em `Patient Appointment` + derivação de `ref_sales_invoice.status` | 2 custom fields + derivação. |
| **Reação adversa** | **Novo DocType `Adverse Reaction`** linkando `drug_prescription` | Sem equivalente upstream. Semântica de reação precisa de filtros, gravidade, notificação ANVISA — flag em Patient Encounter ficaria fraca para relatórios. |
| **Integração RNDS** | **Novo Single DocType `RNDS Settings`** (CNES, certificado A1, ambiente, OAuth tokens) + hook FHIR R4 em `Drug Prescription.after_insert` + `resolve_cns(cpf)` via `GET /patient` | Sem equivalente upstream. RNDS é específico do Brasil. |
| **Identificação do paciente** | Custom fields `cpf` (primário, validado) + `cns` (read-only, derivado) em `Patient` | CPF é a chave; CNS resolvido via RNDS. Ver atualização "Identificação por CPF". |

### DocTypes verdadeiramente novos: 2

1. **`Adverse Reaction`** — link drug_prescription, sintomas (child), gravidade, data_inicio, ação tomada, notificada_anvisa.
2. **`RNDS Settings`** (Single) — CNES, certificado A1, ambiente, OAuth tokens cached.

### Custom fields: 18 distribuídos

- `Medication`: `is_vaccine`, `codigo_rnds`, `tipo_imunizacao`, `via_administracao_padrao`, `local_anatomico_padrao`, `obrigatoria_pni`, `pni_idade_meses_inicio` (7)
- `Therapy Plan Template`: `is_pni`, `versao_pni` (2)
- `Therapy Plan Template Detail`: `medication`, `dose_numero`, `intervalo_dias_min`, `idade_meses_ideal` (4)
- `Drug Prescription`: `dose_numero`, `lote`, `fabricante`, `validade_lote`, `local_anatomico_aplicado`, `via_administracao_aplicada`, `rnds_status`, `rnds_id`, `rnds_payload` (9)
- `Medication Request`: `dose_numero`, `therapy_plan` (2)
- `Patient Appointment`: `imun_modalidade`, `imun_application_address_display` (2)
- `Patient`: `cns` (1)

(Total real: 27 — alguns foram somados duplicados acima. Lista canônica vai no `custom_fields.py`.)

### Páginas/Views custom: 1

- **Carteira de Vacinação** — Vue page mostrando calendário PNI por idade do paciente, marcando aplicadas/pendentes/atrasadas. Query sobre `Drug Prescription` × `Medication.is_vaccine=1` + `Therapy Plan Template` (esquema esperado).

## Alternativas consideradas

### A. App `imunocare_immunization` greenfield (proposta inicial)

- **DocTypes**: `Vaccine`, `Vaccine Dose Schedule`, `Patient Immunization`, `Vaccine Package`, `Patient Vaccine Purchase`, `Adverse Reaction`, `RNDS Settings` (~7 novos).
- **Custo**: ~80% mais código custom. Toda integração com Sales Invoice, estoque, Item, Patient Encounter precisa ser remontada à mão. Cada feature de Healthcare upstream (ex.: novos relatórios sobre Drug Prescription) não se aplica aos nossos DocTypes paralelos.
- **Rejeitada** porque duplica semântica que já existe (`Medication` = produto farmacêutico, `Therapy Plan Template` = esquema temporal, `Treatment Plan Template` = combo comercial, `Drug Prescription` = aplicação registrada, `Medication Request` = dose planejada).

### B. Solução híbrida: Healthcare nativo + nossos DocTypes

- Manter `Vaccine` próprio (paralelo a `Medication`) sob argumento de "vacinas têm semântica diferente de remédios".
- **Custo**: mantém duplicação. Não há semântica suficientemente distinta — vacinas usam mesmos campos (dose, via, local, lote, fabricante, validade). Vinculação a Item é idêntica.
- **Rejeitada**: o argumento "vacinas são diferentes" não se sustenta no nível de modelagem.

### C. Reuso máximo (esta ADR)

- **Aceita**. Justificada acima.

## Consequências

### Positivas

- **80% menos código custom** que a proposta greenfield.
- **Integração automática** com fluxos nativos: estoque (via Item), faturamento (via Sales Invoice + Treatment Plan Template), histórico (via Patient History Settings), agendamento (via Patient Appointment), encontros (via Patient Encounter), prescrição (via Drug Prescription).
- **Atualizações upstream** trazem melhorias automáticas (ex.: features futuras do Healthcare em Drug Prescription/Medication Request).
- **Curva de aprendizado menor** para colaboradores familiarizados com Healthcare/ERPNext.
- **Botão nativo `get_applicable_treatment_plans`** no Patient Encounter sugere combos automaticamente — UX rica de graça.

### Negativas / Riscos

- **Semantic stretching**: `Therapy Plan Template` é nominalmente "plano de terapia" (fisioterapia, sessões), não "esquema vacinal". Pode confundir usuários em onboarding. Mitigação: rótulos custom no `imunocare_clinic_ext` renomeando exibições onde necessário.
- **Dependência de evolução upstream**: se Healthcare introduzir `Immunization` DocType próprio no futuro, precisaremos migrar. Mitigação: ADR registrada + monitoramento de releases.
- **Reação adversa fora do modelo Healthcare**: nosso `Adverse Reaction` não terá integração nativa com Patient History. Mitigação: adicionar `Adverse Reaction` ao `Patient History Settings`.

### Neutras

- **Multi-tenancy SaaS**: Patient é por Company (Healthcare suporta nativamente). Combo/Treatment Plan Template é por Company. RNDS Settings é Single — em SaaS multi-site, cada site tem sua RNDS Settings (cada clínica = site separado, decisão já documentada em `project_imunoerp`).

## Faseamento de execução

Conforme proposto e validado em 2026-05-22 (atualizado mesmo dia com Fase 7 dedicada à adequação WhatsApp):

1. **Fase 1** (~3 dias): Custom fields em `Medication` + `Therapy Plan Template` + `Therapy Plan Template Detail`. Seed PNI inicial. **Concluída.**
2. **Fase 2** (~5 dias): Custom fields em `Patient` (CNS) + `Drug Prescription` (lote, dose_numero, RNDS fields) + `Patient Appointment` (modalidade, endereço). Hook que popula endereço baseado em modalidade. Drug Prescription no Patient History Settings. Página "Carteira de Vacinação".
3. **Fase 3** (~2 dias): DocType `Adverse Reaction` (ESAVI) + integração com Patient History Settings. **Concluída.** DocType **submittable** (requisito do Patient Medical Record para entrar na timeline); série `ESAVI-.YYYY.-`; campos de gravidade/sintomas/desfecho/notificação ANVISA; alerta de notificação compulsória para reações Graves. **Pegadinha**: doctypes de app vão no diretório do MÓDULO (`<app>/<app>/<module>/doctype/`), não no pacote do app.
4. **Fase 4** (~7 dias): RNDS Settings + cliente FHIR R4 + auto-envio + retry scheduler + **`resolve_cns(cpf)`** via `GET /patient` (resolve e cacheia CNS a partir do CPF; botão "Buscar CNS" no Patient + hook opcional). Envio do `Immunization` usando **CPF** como identifier (CNS opcional).
5. **Fase 5** (~4 dias): Treatment Plan Templates como combos comerciais + fluxo de venda + auto-criação de Medication Requests para doses futuras.
6. **Fase 6** (~3 dias): Report "Retornos Pendentes" + dashboard.
7. **Fase 7 (NOVA)** (~1 dia): **Adequação schema + helpers WhatsApp**. Valida que todos os campos requeridos pelos 5 templates HSM aprovados estão acessíveis. Implementa helpers `format_vaccine_list`, `format_appointment_for_whatsapp`, `format_dose_reminder_for_whatsapp`. Configura `imunocare_clinic_address_short` em site_config. Smoke tests manuais de extração de variáveis.
8. **Fase 8** (~2 dias, era Fase 7): Hooks `Patient Appointment.after_insert/on_update` + schedulers daily/weekly disparando templates HSM aprovados.
9. **Fase 9** (contínuo, era Fase 8): UX polish.

Por que Fase 7 dedicada: os 5 templates HSM dependem de variáveis em múltiplos DocTypes (Patient Appointment para 1-4, Medication Request para 5). Adequação só faz sentido quando todos campos existem — concentrar em uma fase evita dupla passada.

Templates HSM já aprovados ([[project-whatsapp-templates]]). Pré-requisito mínimo de disparo (templates 1-4) destrancado em Fase 2; ciclo completo (template 5) destrancado em Fase 5; adequação final em Fase 7; produção em Fase 8.

## Atualização — Identificação por CPF (2026-05-22)

**Problema operacional:** a maioria dos pacientes não tem o cartão SUS (CNS) em mãos no momento da vacinação, gerando transtorno na recepção.

**Investigação (documentação oficial RNDS/DATASUS):**
1. O recurso FHIR `Immunization` do RNDS aceita o paciente identificado por **CPF OU CNS** — não exige o cartão. Identificador via `identifier.system` + `identifier.value`:
   - CPF: `https://rnds-fhir.saude.gov.br/NamingSystem/cpf`
   - CNS: `https://rnds-fhir.saude.gov.br/NamingSystem/cns`
2. A RNDS expõe o serviço **`GET /patient`** (componente EHR Services) que **retorna o CNS a partir do CPF**. A consulta só aceita CPF como chave (RG, nome da mãe etc. ficam para "regulação futura").
3. Pré-requisito comum a ambos: o documento (CPF/CNS) precisa estar no CADSUS — válido para a imensa maioria dos brasileiros.

**Decisão:**
- **CPF é o documento primário** de identificação do paciente (custom field `cpf` em `Patient`, `unique`, validado pelas regras da Receita Federal — dígitos verificadores; armazenado só com 11 dígitos para casar com o identifier FHIR).
- **CNS vira derivado** (custom field `cns` read-only, auto-preenchido). Resolvido via `resolve_cns(cpf)` (`GET /patient`) na Fase 4; nunca exigido na recepção.
- O envio de `Immunization` ao RNDS pode usar **CPF direto** como identifier — viável mesmo se o CNS nunca for resolvido.

**Consequência:** elimina o gargalo do cartão físico; recepção opera só com CPF. RNDS viável desde o primeiro registro.

**Implementado na Fase 2:** custom fields `cpf`/`cns`, validação em `patient_hooks.validate`, hook `Patient.validate` registrado. `resolve_cns` e envio FHIR ficam na Fase 4.

## Referências

- Frappe Healthcare DocTypes: https://github.com/frappe/healthcare (v15.1.18)
- PNI Brasil: https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/c/calendario-nacional-de-vacinacao
- RNDS API: https://rnds-guia.saude.gov.br/
- RNDS — Conheça os serviços (EHR Services / EHR Auth): https://rnds-guia.saude.gov.br/docs/publico-alvo/ti/conhecer/
- NamingSystem CPF (RNDS FHIR): https://rnds-fhir.saude.gov.br/NamingSystem-cpf.html
- Manual de Integração Barramento RNDS (DATASUS): https://datasus.saude.gov.br/wp-content/uploads/2020/04/SOA-RNDS_ManualIntegracaoBarramento_vSite.pdf
- FHIR R4 Immunization: https://www.hl7.org/fhir/immunization.html
