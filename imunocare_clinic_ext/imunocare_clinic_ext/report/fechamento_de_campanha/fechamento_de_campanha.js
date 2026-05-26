// Fechamento de Campanha (Fase 12) — filtros e largura total. Runtime, sem build.
frappe.query_reports["Fechamento de Campanha"] = {
	filters: [
		{
			fieldname: "campaign",
			label: __("Campanha"),
			fieldtype: "Link",
			options: "Imunocare Vaccination Campaign",
		},
		{
			fieldname: "empresa",
			label: __("Empresa"),
			fieldtype: "Link",
			options: "Customer",
		},
	],

	onload(report) {
		if (!document.body.classList.contains("full-width")) {
			document.body.classList.add("full-width");
			report._imun_added_fullwidth = true;
		}
		frappe.router.on("change", function _imun_restore() {
			if ((frappe.get_route_str() || "").indexOf("Fechamento") === -1) {
				if (report._imun_added_fullwidth) {
					document.body.classList.remove("full-width");
				}
			}
		});
	},
};
