"""Controller de Aplicacao de Vacina — gerencia estoque via Batch (FIFO) e agenda retorno."""

from __future__ import annotations
import frappe
from frappe.model.document import Document
from frappe.utils import add_days, now_datetime


class AplicacaoDeVacina(Document):
    def before_submit(self) -> None:
        if not self.lote:
            self.lote = self._get_lote_fifo()
        self._debitar_estoque()
        self._calcular_retorno()

    def on_cancel(self) -> None:
        self._estornar_estoque()

    # ------------------------------------------------------------------
    def _get_lote_fifo(self) -> str:
        """Seleciona o lote com validade mais próxima (FIFO) para o item."""
        if not self.item_vacina:
            frappe.throw("Informe o Item da vacina para seleção automática do lote.")
        lotes = frappe.get_all(
            "Batch",
            filters={
                "item": self.item_vacina,
                "disabled": 0,
                "expiry_date": [">=", frappe.utils.today()],
            },
            fields=["name", "expiry_date"],
            order_by="expiry_date asc",
            limit=1,
        )
        if not lotes:
            frappe.throw(f"Nenhum lote válido disponível para {self.item_vacina}.")
        return lotes[0].name

    def _debitar_estoque(self) -> None:
        if not (self.lote and self.item_vacina):
            return
        batch = frappe.get_doc("Batch", self.lote)
        atual = batch.get("imu_qtd_disponivel") or 0
        if atual <= 0:
            frappe.throw(f"Lote {self.lote} sem doses disponíveis.")
        batch.db_set("imu_qtd_disponivel", atual - 1)

    def _estornar_estoque(self) -> None:
        if not (self.lote and self.item_vacina):
            return
        batch = frappe.get_doc("Batch", self.lote)
        atual = batch.get("imu_qtd_disponivel") or 0
        batch.db_set("imu_qtd_disponivel", atual + 1)

    def _calcular_retorno(self) -> None:
        """Calcula data de retorno recomendada com base no protocolo."""
        if self.data_retorno_recomendada or not self.protocolo:
            return
        protocolo = frappe.get_doc("Protocolo de Imunizacao", self.protocolo)
        dose_atual = _numero_dose_int(self.numero_dose)
        proxima = next(
            (d for d in protocolo.doses if d.numero_dose == dose_atual + 1), None
        )
        if proxima and proxima.intervalo_recomendado_dias:
            base = self.data_aplicacao or now_datetime()
            self.data_retorno_recomendada = add_days(base, proxima.intervalo_recomendado_dias)


def _numero_dose_int(label: str | None) -> int:
    try:
        return int(str(label or "0").strip()[0])
    except (ValueError, IndexError):
        return 0
