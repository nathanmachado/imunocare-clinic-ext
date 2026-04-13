"""Scheduler diário: alertas de vencimento de lotes e estoque mínimo."""

from __future__ import annotations
import frappe
from frappe.utils import add_days, today


def verificar_lotes() -> None:
    _alertar_vencimento()
    _alertar_estoque_minimo()


def _alertar_vencimento() -> None:
    limites = [(7, "CRÍTICO"), (30, "ATENÇÃO")]
    for dias, nivel in limites:
        lotes = frappe.get_all(
            "Batch",
            filters={
                "disabled": 0,
                "expiry_date": ["between", [today(), add_days(today(), dias)]],
                "imu_qtd_disponivel": [">", 0],
            },
            fields=["name", "item", "expiry_date", "imu_qtd_disponivel"],
        )
        for lote in lotes:
            frappe.log_error(
                title=f"[{nivel}] Lote próximo ao vencimento",
                message=(
                    f"Lote: {lote.name}\n"
                    f"Item: {lote.item}\n"
                    f"Validade: {lote.expiry_date}\n"
                    f"Doses disponíveis: {lote.imu_qtd_disponivel}"
                ),
            )
            _notificar_farmaceutico(
                f"[Imunocare {nivel}] Lote {lote.name} ({lote.item}) vence em {dias} dias "
                f"— {lote.imu_qtd_disponivel} doses restantes."
            )


def _alertar_estoque_minimo() -> None:
    lotes_criticos = frappe.db.sql(
        """
        SELECT b.name, b.item, b.imu_qtd_disponivel, b.imu_qtd_inicial
        FROM `tabBatch` b
        WHERE b.disabled = 0
          AND b.imu_qtd_inicial > 0
          AND b.imu_qtd_disponivel <= (b.imu_qtd_inicial * 0.10)
        """,
        as_dict=True,
    )
    for lote in lotes_criticos:
        _notificar_farmaceutico(
            f"[Imunocare ESTOQUE] Lote {lote.name} ({lote.item}) com apenas "
            f"{lote.imu_qtd_disponivel} doses (≤ 10% do inicial)."
        )


def _notificar_farmaceutico(mensagem: str) -> None:
    emails = frappe.get_all(
        "Has Role",
        filters={"role": "Healthcare Administrator"},
        fields=["parent"],
        pluck="parent",
    )
    if not emails:
        return
    usuarios = frappe.get_all(
        "User",
        filters={"name": ["in", emails], "enabled": 1},
        fields=["email"],
        pluck="email",
    )
    if usuarios:
        frappe.sendmail(
            recipients=usuarios,
            subject="[Imunocare] Alerta de Estoque/Vencimento",
            message=mensagem.replace("\n", "<br>"),
        )
