"""Envio de Registro de Imunobiológico Administrado (RIA) ao RNDS — Fase 4c.

Monta o Bundle FHIR R4 (document) com Composition + Immunization conforme o
perfil RIA do RNDS e envia via POST /Bundle. Grava o status na Drug Prescription
(child de Patient Encounter).

IMPORTANTE: o perfil RIA usa vários ValueSets/CodeSystems do SIPNI
(imunobiológico, estratégia de vacinação, grupo de atendimento, CBO). Os
códigos auxiliares (estratégia, grupo, tipo de documento) têm defaults
configuráveis e precisam ser confirmados contra o RNDS de homologação com os
valores reais do estabelecimento. O código do imunobiológico vem de
``Medication.codigo_rnds``.
"""

from __future__ import annotations

import uuid

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

# CodeSystems / Systems oficiais do RNDS (FHIR R4).
SYS_IMUNOBIOLOGICO = "http://www.saude.gov.br/fhir/r4/CodeSystem/BRImunobiologico"
SYS_ESTRATEGIA = "http://www.saude.gov.br/fhir/r4/CodeSystem/BREstrategiaVacinacao"
SYS_GRUPO_ATENDIMENTO = "http://www.saude.gov.br/fhir/r4/CodeSystem/BRGrupoAtendimento"
SYS_VIA = "http://www.saude.gov.br/fhir/r4/CodeSystem/BRViaAdministracao"
SYS_CBO = "http://www.saude.gov.br/fhir/r4/CodeSystem/BRCBO"
SYS_CNS = "http://www.saude.gov.br/fhir/r4/StructureDefinition/BRIndividuo-1.0"
SYS_CPF = "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf"
SYS_CNES = "http://www.saude.gov.br/fhir/r4/NamingSystem/cnes"
EXT_ESTRATEGIA = "http://www.saude.gov.br/fhir/r4/StructureDefinition/BRRegistroImunobiologicoAdministradoEstrategia-1.0"
EXT_GRUPO = "http://www.saude.gov.br/fhir/r4/StructureDefinition/BRRegistroImunobiologicoAdministradoGrupoAtendimento-1.0"

# Defaults configuráveis (ajustar conforme o estabelecimento / campanha).
DEFAULT_ESTRATEGIA = "2"  # Rotina (confirmar na tabela BREstrategiaVacinacao)
TIPO_DOCUMENTO_RIA = "RIA"


def build_immunization_bundle(data: dict) -> dict:
	"""Monta o Bundle FHIR (document) do RIA a partir de ``data``.

	``data`` esperado::

	    {
	        "patient_id_system": <SYS_CNS|SYS_CPF>, "patient_id_value": "...",
	        "cnes": "...", "imunobiologico": "<codigo_rnds>",
	        "occurrence": "<iso datetime>", "lote": "...", "fabricante": "...",
	        "dose_numero": 1, "via": "<codigo|None>",
	        "profissional_cns": "<cns|None>", "cbo": "<codigo|None>",
	        "estrategia": "<codigo>", "grupo_atendimento": "<codigo|None>",
	    }
	"""
	imm_uuid = f"urn:uuid:{uuid.uuid4()}"
	comp_uuid = f"urn:uuid:{uuid.uuid4()}"

	immunization = {
		"resourceType": "Immunization",
		"status": "completed",
		"vaccineCode": {"coding": [{"system": SYS_IMUNOBIOLOGICO, "code": str(data["imunobiologico"])}]},
		"patient": {"identifier": {"system": data["patient_id_system"], "value": data["patient_id_value"]}},
		"occurrenceDateTime": data["occurrence"],
		"lotNumber": data.get("lote") or "",
		"location": {"identifier": {"system": SYS_CNES, "value": data["cnes"]}},
		"protocolApplied": [{"doseNumberString": str(data.get("dose_numero") or 1)}],
		"extension": [
			{"url": EXT_ESTRATEGIA, "valueCodeableConcept": {"coding": [
				{"system": SYS_ESTRATEGIA, "code": str(data.get("estrategia") or DEFAULT_ESTRATEGIA)}
			]}},
		],
	}
	if data.get("fabricante"):
		immunization["manufacturer"] = {"display": data["fabricante"]}
	if data.get("via"):
		immunization["route"] = {"coding": [{"system": SYS_VIA, "code": str(data["via"])}]}
	if data.get("profissional_cns"):
		performer = {"actor": {"identifier": {"system": SYS_CNS, "value": data["profissional_cns"]}}}
		if data.get("cbo"):
			performer["function"] = {"coding": [{"system": SYS_CBO, "code": str(data["cbo"])}]}
		immunization["performer"] = [performer]
	if data.get("grupo_atendimento"):
		immunization["extension"].append(
			{"url": EXT_GRUPO, "valueCodeableConcept": {"coding": [
				{"system": SYS_GRUPO_ATENDIMENTO, "code": str(data["grupo_atendimento"])}
			]}}
		)

	composition = {
		"resourceType": "Composition",
		"status": "final",
		"type": {"coding": [{"system": "http://www.saude.gov.br/fhir/r4/CodeSystem/BRTipoDocumento", "code": TIPO_DOCUMENTO_RIA}]},
		"subject": {"identifier": {"system": data["patient_id_system"], "value": data["patient_id_value"]}},
		"date": data["occurrence"],
		"author": [{"identifier": {"system": SYS_CNES, "value": data["cnes"]}}],
		"title": "Registro de Imunobiológico Administrado",
		"section": [{"entry": [{"reference": imm_uuid}]}],
	}

	return {
		"resourceType": "Bundle",
		"type": "document",
		"entry": [
			{"fullUrl": comp_uuid, "resource": composition},
			{"fullUrl": imm_uuid, "resource": immunization},
		],
	}


def _patient_identifier(patient: str) -> tuple[str, str] | None:
	"""(system, value) do paciente: prefere CNS, cai para CPF."""
	cns = frappe.db.get_value("Patient", patient, "cns")
	if cns:
		return SYS_CNS, cns
	cpf = frappe.db.get_value("Patient", patient, "cpf")
	if cpf:
		return SYS_CPF, cpf
	return None


def enviar_imunizacao(encounter: str, dp_name: str) -> str:
	"""Monta e envia o RIA de uma Drug Prescription. Retorna o rnds_status final.

	Grava ``rnds_status`` / ``rnds_id`` / ``rnds_payload`` na linha da
	Drug Prescription. Não levanta: erros viram status 'Erro' (retry depois).
	"""
	from imunocare_clinic_ext.rnds_client import ehr_post

	enc = frappe.get_doc("Patient Encounter", encounter)
	dp = next((d for d in enc.drug_prescription if d.name == dp_name), None)
	if not dp or not dp.medication:
		return "Não aplicável"

	def _set(status, rnds_id=None, payload=None):
		dp.db_set("rnds_status", status, update_modified=False)
		if rnds_id is not None:
			dp.db_set("rnds_id", rnds_id, update_modified=False)
		if payload is not None:
			dp.db_set("rnds_payload", payload[:14000], update_modified=False)
		return status

	pid = _patient_identifier(enc.patient)
	if not pid:
		return _set("Erro", payload="Paciente sem CNS nem CPF.")

	med = frappe.get_doc("Medication", dp.medication)
	if not med.get("codigo_rnds"):
		return _set("Erro", payload=f"Medication {dp.medication} sem codigo_rnds (BRImunobiologico).")

	settings = frappe.get_single("RNDS Settings")
	prof_cns = frappe.db.get_value("Healthcare Practitioner", enc.practitioner, "cns") if enc.get("practitioner") else None

	data = {
		"patient_id_system": pid[0], "patient_id_value": pid[1],
		"cnes": settings.cnes,
		"imunobiologico": med.codigo_rnds,
		"occurrence": get_datetime(f"{enc.encounter_date} {enc.get('encounter_time') or '00:00:00'}").isoformat(),
		"lote": dp.get("lote"), "fabricante": dp.get("fabricante"),
		"dose_numero": dp.get("dose_numero"), "via": _via_code(dp.get("via_administracao_aplicada")),
		"profissional_cns": prof_cns,
	}

	try:
		bundle = build_immunization_bundle(data)
		resp = ehr_post("Bundle", bundle)
		if resp.status_code in (200, 201):
			rnds_id = (resp.json() or {}).get("id") if _is_json(resp) else None
			return _set("Enviado", rnds_id=rnds_id or "", payload=resp.text[:2000])
		return _set("Erro", payload=f"HTTP {resp.status_code}: {resp.text[:1500]}")
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "RNDS: falha ao enviar imunização")
		return _set("Erro", payload=str(e)[:2000])


def _via_code(via_label: str | None) -> str | None:
	"""Placeholder de mapeamento via de administração → código BRViaAdministracao.

	Os códigos reais devem ser mapeados conforme a tabela do RNDS. Por ora,
	retorna None (campo opcional) para não enviar código inválido."""
	return None


def _is_json(resp) -> bool:
	try:
		resp.json()
		return True
	except Exception:
		return False
