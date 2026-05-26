// Projeção de Estoque de Vacinas (Fase 11) — filtros, cores e largura total.
// Carregado em runtime pelo report view; não depende de build de assets.

frappe.query_reports["Projeção de Estoque de Vacinas"] = {
	filters: [
		{
			fieldname: "meses",
			label: __("Horizonte"),
			fieldtype: "Select",
			options: [
				{ value: "3", label: __("Próximos 3 meses") },
				{ value: "6", label: __("Próximos 6 meses") },
				{ value: "12", label: __("Próximos 12 meses") },
			],
			default: "3",
			reqd: 1,
		},
		{
			fieldname: "incluir_em_pedido",
			label: __("Considerar 'Em pedido' no saldo"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "somente_com_deficit",
			label: __("Só vacinas a repor ⚠"),
			fieldtype: "Check",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		const formatted = default_formatter(value, row, column, data);
		const fn = column.fieldname || "";

		// Saldo mensal projetado: vermelho/negrito quando o estoque "fura".
		if (fn.startsWith("saldo_") && data) {
			const v = data[fn];
			if (v != null && v < 0) {
				return `<span style="color:var(--red-600,#c0392b);font-weight:700">${formatted}</span>`;
			}
			if (v != null && v <= 5) {
				return `<span style="color:var(--orange-600,#d35400);font-weight:600">${formatted}</span>`;
			}
			return formatted;
		}

		// Repor: pílula de alerta quando > 0 (quanto comprar para não faltar).
		if (fn === "repor" && data) {
			if (data.repor > 0) {
				return `<span class="indicator-pill red" style="font-weight:700"
					title="${__("Doses a repor no horizonte")}">⚠ ${formatted}</span>`;
			}
			return `<span class="indicator-pill green">${formatted}</span>`;
		}

		// Estoque atual zerado: destaque.
		if (fn === "estoque" && data && data.estoque <= 0) {
			return `<span style="color:var(--red-600,#c0392b);font-weight:700">${formatted}</span>`;
		}

		return formatted;
	},

	onload(report) {
		report.page.add_inner_button(__("Comprar (Material Request)"), () => {
			frappe.new_doc("Material Request", { material_request_type: "Purchase" });
		});

		// Largura total (mesma classe do toggle nativo do Frappe). Removida ao
		// sair da rota do report para não vazar para outras páginas.
		if (!document.body.classList.contains("full-width")) {
			document.body.classList.add("full-width");
			report._imun_added_fullwidth = true;
		}
		frappe.router.on("change", function _imun_restore() {
			if ((frappe.get_route_str() || "").indexOf("Proje") === -1) {
				if (report._imun_added_fullwidth) {
					document.body.classList.remove("full-width");
				}
			}
		});
	},
};
