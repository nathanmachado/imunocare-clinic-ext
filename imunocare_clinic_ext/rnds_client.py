"""Cliente RNDS (Fase 4) — autenticação mTLS e chamadas FHIR R4.

O certificado A1 só é usado no ``POST /token`` (Two-way SSL). O access_token
resultante (~15-30 min) é reusado nas demais chamadas e cacheado em Redis.

O .pfx é carregado em memória (bytes) e passado direto ao handshake mTLS via
requests-pkcs12 — nunca é escrito em disco.
"""

from __future__ import annotations

import re

import requests
from requests_pkcs12 import get as pkcs12_get

import frappe
from frappe import _

# NamingSystems oficiais do RNDS (FHIR R4).
CPF_SYSTEM = "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf"
CNS_SYSTEM = "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cns"

# Token cacheado por menos que a validade real (margem de segurança).
_TOKEN_CACHE_KEY = "rnds_access_token"
_TOKEN_TTL_SECONDS = 25 * 60


def _settings():
	return frappe.get_single("RNDS Settings")


def get_access_token(force_refresh: bool = False) -> str:
	"""Retorna um access_token RNDS válido (cacheado em Redis).

	Faz ``POST /token`` com mTLS usando o certificado A1 (em memória) quando
	não há token em cache ou ``force_refresh`` é True.
	"""
	cache = frappe.cache()
	if not force_refresh:
		cached = cache.get_value(_TOKEN_CACHE_KEY)
		if cached:
			return cached.decode() if isinstance(cached, bytes) else cached

	settings = _settings()
	if not settings.url_token:
		frappe.throw(_("URL de autenticação do RNDS não configurada."))

	pfx_bytes = settings.get_certificate_bytes()
	senha = settings.get_password("senha_certificado")

	try:
		# RNDS EHR Auth: o token é obtido via GET (mTLS), não POST.
		resp = pkcs12_get(
			settings.url_token,
			pkcs12_data=pfx_bytes,
			pkcs12_password=senha,
			timeout=30,
		)
		resp.raise_for_status()
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "RNDS: falha na autenticação mTLS")
		frappe.throw(_("Falha ao autenticar no RNDS: {0}").format(str(e)))
	finally:
		# Não retém o material do certificado além do necessário.
		pfx_bytes = None  # noqa: F841

	token = _extract_token(resp)
	cache.set_value(_TOKEN_CACHE_KEY, token, expires_in_sec=_TOKEN_TTL_SECONDS)
	return token


def _extract_token(resp) -> str:
	"""Extrai o access_token da resposta (header ou JSON, conforme o RNDS)."""
	# O RNDS retorna o token no header X-Authorization-Server (Bearer ...).
	header = resp.headers.get("X-Authorization-Server") or resp.headers.get("Authorization")
	if header:
		return header.replace("Bearer ", "").strip()
	try:
		data = resp.json()
		return data.get("access_token") or data.get("token") or ""
	except Exception:
		return resp.text.strip()


def _ehr_auth_headers(settings, extra: dict | None = None) -> dict:
	"""Headers de autenticação do EHR Services.

	O RNDS exige DOIS headers nas chamadas FHIR:
	- ``X-Authorization-Server``: Bearer com o access_token (do certificado).
	- ``Authorization``: CNS do profissional solicitante (vinculado ao CNES).
	"""
	headers = {"X-Authorization-Server": f"Bearer {get_access_token()}"}
	cns = settings.get("cns_solicitante")
	if not cns and settings.get("profissional_responsavel"):
		cns = frappe.db.get_value("Healthcare Practitioner", settings.profissional_responsavel, "cns")
	if cns:
		headers["Authorization"] = cns
	if extra:
		headers.update(extra)
	return headers


def ehr_get(path: str, params: dict | None = None) -> requests.Response:
	"""GET autenticado no EHR Services (FHIR). ``path`` relativo a url_ehr."""
	settings = _settings()
	url = f"{settings.url_ehr.rstrip('/')}/{path.lstrip('/')}"
	return requests.get(
		url,
		headers=_ehr_auth_headers(settings, {"Accept": "application/fhir+json"}),
		params=params or {},
		timeout=30,
	)


def ehr_post(path: str, payload: dict) -> requests.Response:
	"""POST autenticado no EHR Services (FHIR). ``path`` relativo a url_ehr."""
	settings = _settings()
	url = f"{settings.url_ehr.rstrip('/')}/{path.lstrip('/')}"
	return requests.post(
		url,
		headers=_ehr_auth_headers(settings, {"Content-Type": "application/fhir+json"}),
		json=payload,
		timeout=30,
	)


# --- 4b: resolução de CNS por CPF ---


def resolve_cns(cpf: str) -> str | None:
	"""Resolve o CNS de um cidadão a partir do CPF, via GET /Patient (RNDS).

	Retorna a primeira ocorrência de CNS no recurso Patient, ou None se não
	encontrado. O CPF é normalizado para 11 dígitos.
	"""
	cpf = re.sub(r"\D", "", cpf or "")
	if len(cpf) != 11:
		return None

	resp = ehr_get("Patient", params={"identifier": f"{CPF_SYSTEM}|{cpf}"})
	# O RNDS retorna 404 quando o paciente não existe na base (CADSUS) — trata
	# como "não encontrado", não como erro de integração.
	if resp.status_code == 404:
		return None
	resp.raise_for_status()
	bundle = resp.json()

	for entry in bundle.get("entry", []):
		resource = entry.get("resource", {})
		if resource.get("resourceType") != "Patient":
			continue
		for ident in resource.get("identifier", []):
			if ident.get("system") == CNS_SYSTEM and ident.get("value"):
				return re.sub(r"\D", "", ident["value"])
	return None


def resolve_cns_profissional(cpf: str) -> str | None:
	"""Resolve o CNS de um profissional pelo CPF, via GET /Practitioner (RNDS)."""
	cpf = re.sub(r"\D", "", cpf or "")
	if len(cpf) != 11:
		return None

	resp = ehr_get("Practitioner", params={"identifier": f"{CPF_SYSTEM}|{cpf}"})
	if resp.status_code == 404:
		return None
	resp.raise_for_status()
	bundle = resp.json()

	for entry in bundle.get("entry", []):
		resource = entry.get("resource", {})
		if resource.get("resourceType") != "Practitioner":
			continue
		for ident in resource.get("identifier", []):
			if ident.get("system") == CNS_SYSTEM and ident.get("value"):
				return re.sub(r"\D", "", ident["value"])
	return None


@frappe.whitelist()
def buscar_cns_do_paciente(patient: str) -> dict:
	"""Resolve e salva o CNS de um Patient a partir do seu CPF (RNDS)."""
	cpf = frappe.db.get_value("Patient", patient, "cpf")
	if not cpf:
		frappe.throw(_("O paciente não possui CPF cadastrado."))

	cns = resolve_cns(cpf)
	if not cns:
		return {"found": False, "message": _("CNS não encontrado no RNDS para este CPF.")}

	frappe.db.set_value("Patient", patient, "cns", cns)
	return {"found": True, "cns": cns, "message": _("CNS encontrado e salvo: {0}").format(cns)}
