# ADR-0002 — Campanhas de vacinação corporativa (faturamento B2B)

- **Status**: Accepted
- **Data**: 2026-05-26
- **Decisores**: Nathan Machado (Imunocare), Claude
- **Escopo**: Aplicação `imunocare_clinic_ext` (Fase 12)

## Contexto

A clínica faz campanhas em empresas: o contratante envia uma lista de
colaboradores, vacina-se todo mundo e, ao final, fatura-se **o valor total das
doses aplicadas para a empresa** (não para cada colaborador). É um modelo B2B,
distinto do balcão B2C (onde o próprio paciente paga).

Requisitos: vincular colaborador → campanha → empresa para que no fechamento se
saiba (1) quantas doses por empresa, (2) quais colaboradores tomaram, (3) qual o
valor a faturar.

Levantamento do nativo (ERPNext/Healthcare 15) em 2026-05-26:
- **Customer / Sales Order / Sales Invoice / Price List / Item Price** cobrem
  todo o lado comercial (cliente PJ, orçamento, fatura, preço negociado).
- **Patient / Patient Appointment + child `imun_vaccines`** (já customizado) é a
  unidade de aplicação — preserva carteira de vacinação e RNDS por colaborador.
- Não existe no nativo nenhum conceito que amarre um **grupo de pacientes a um
  pagador terceiro (a empresa)**. O `Campaign` do CRM é só marketing (e-mails).
  O faturamento do Healthcare é por paciente, não consolidado para um PJ.

## Decisão

Modelar campanhas corporativas com **reuso máximo do nativo** (ver
[[feedback_reuse_first]]), criando apenas **2 DocTypes finos + 1 child de escopo
+ 1 custom field**:

- `Imunocare Vaccination Campaign` (parent): empresa (Customer), período, local,
  `price_list`, status, links para Sales Order/Sales Invoice e totais.
- `Imunocare Campaign Colaborador` (child roster): dados crus da empresa +
  `patient` casado/criado + status + appointment.
- `Imunocare Campaign Vaccine` (child escopo): vacina + doses por colaborador.
- Custom field `imun_campaign` em **Patient Appointment** — a "cola" que faz
  "doses por empresa" sair de um `GROUP BY`.

### Decisões de design (confirmadas com o cliente)

1. **Preço por empresa via Price List**: cada empresa pode ter sua tabela
   negociada (Item Price em Price List própria), com fallback numa lista
   `Empresarial` padrão. Sem preço paralelo — reusa Item Price nativo.
2. **Faturar só a dose**: 1 linha de Sales Invoice por vacina (qtd = doses
   aplicadas × preço da dose); o preço da dose embute a aplicação.
3. **Patient completo por colaborador**: cada colaborador vira um Patient
   (carteira + RNDS individuais). A importação exige o mínimo de campanha (CPF,
   nome, nascimento, sexo) e **dispensa celular/email/nome-do-meio** via
   `ignore_mandatory`, sem afetar as obrigatoriedades do balcão B2C.
4. **Sales Order na confirmação**: ao confirmar, gera um Sales Order (orçamento
   aprovável, qtd estimada = doses ofertadas × nº colaboradores); no fechamento,
   gera a Sales Invoice com o **realizado**, vinculada ao SO (`so_detail`).

### Fluxo

Rascunho → (importar lista) Lista Importada → (confirmar) Confirmada [Sales
Order] → Em Aplicação → Fechada → (faturar) Faturada [Sales Invoice].

A Sales Invoice é **`update_stock = 0`**: a baixa de estoque ocorre na aplicação
(hoje ainda não automatizada — dependência conhecida; ver [[project_fase11_projecao_estoque]]),
não no faturamento, para não contar a saída duas vezes.

## Consequências

- O lado comercial fica 100% nativo e integrado à contabilidade (SO/SI, billing
  status, contas a receber).
- Cada colaborador mantém carteira e elegibilidade ao RNDS.
- Patients criados em lote podem não ter celular/email — relatórios B2C que
  assumem esses campos devem tolerar vazio.
- Dependência aberta: automação da baixa de estoque por dose aplicada (Stock
  Entry/Delivery na conclusão do appointment).
- Tudo o que é UI (botões do form, relatórios) vive em Client Script/Script
  Report no banco — sem build de assets (ver [[feedback_frappe_docker_assets]]).
