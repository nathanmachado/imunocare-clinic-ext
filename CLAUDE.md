# CLAUDE.md — imunocare_clinic_ext

## Propósito
Extensão do Frappe Healthcare para gestão de vacinas em clínicas brasileiras.
Implementa Calendário Nacional de Imunização (PNI/MS), cartão de vacinas por paciente,
controle de lotes FIFO, retornos automáticos e alertas por WhatsApp.

**Nunca modificar** o app `healthcare` (upstream).

## Dependências
- `healthcare` (Frappe Healthcare — upstream)
- `imunocare_core`
- `imunocare_crm_custom` (opcional — para lembretes WhatsApp)

## DocTypes Próprios (módulo: Imunocare Clinic Ext)
- `Protocolo de Imunizacao` — definição de vacina, doses e intervalos conforme PNI
- `Dose Protocolo` — child table: nº dose, faixa etária, intervalos
- `Aplicacao de Vacina` — registro da aplicação (submittable), debitada do lote
- `Retorno Programado` — follow-up gerado após aplicação

## Custom Fields nos DocTypes do Healthcare
- `Patient.cpf` — CPF do paciente
- `Patient.cartao_sus` — Cartão SUS
- `Batch.imu_fabricante` — fabricante da vacina
- `Batch.imu_registro_anvisa` — registro ANVISA
- `Batch.imu_qtd_inicial` — quantidade inicial de doses
- `Batch.imu_qtd_disponivel` — doses disponíveis (decrementado a cada Aplicacao)
- `Patient Appointment.tipo_servico` — Vacinação / Consulta / Retorno / Exame
- `Patient Appointment.protocolo_vacina` — Link para Protocolo de Imunizacao

## Regras de Negócio Críticas
- FIFO obrigatório: lote com menor `expiry_date` é selecionado primeiro
- Alerta vencimento: < 30 dias (ATENÇÃO), < 7 dias (CRÍTICO)
- Alerta estoque: ≤ 10% da quantidade inicial
- Lembretes retorno: 30d, 7d, 1d antes via WhatsApp + e-mail

## Fixtures
- `custom_field.json` — Custom Fields nos DocTypes upstream
- `protocolo_de_imunizacao.json` — 15 vacinas do PNI BR pré-carregadas

## Git Flow
Branch de trabalho: `agents/<id>/<issue>-<desc>` → PR → `test` → PR → `main`
Remoto: `https://github.com/nathanmachado/imunocare-clinic-ext`
