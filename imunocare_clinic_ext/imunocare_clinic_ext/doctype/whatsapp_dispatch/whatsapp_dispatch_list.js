// Copyright (c) 2026, Imunocare
frappe.listview_settings["WhatsApp Dispatch"] = {
	get_indicator(doc) {
		const map = {
			Pendente: "orange",
			Enviado: "green",
			Cancelado: "gray",
			Erro: "red",
		};
		return [__(doc.status), map[doc.status] || "gray", "status,=," + doc.status];
	},

	onload(listview) {
		listview.page.add_actionItem(__("Autorizar e Enviar selecionados"), () => {
			const names = listview.get_checked_items(true);
			if (!names.length) {
				frappe.msgprint(__("Selecione ao menos um disparo."));
				return;
			}
			frappe.confirm(
				__("Autorizar e enviar {0} disparo(s) selecionado(s)?", [names.length]),
				() => {
					frappe
						.call({
							method: "imunocare_clinic_ext.imunocare_clinic_ext.doctype.whatsapp_dispatch.whatsapp_dispatch.autorizar_em_massa",
							args: { names: JSON.stringify(names) },
							freeze: true,
							freeze_message: __("Enviando..."),
						})
						.then((r) => {
							const res = r.message || {};
							frappe.show_alert({
								message: __("Enviados: {0} · Erros: {1}", [res.enviados || 0, res.erros || 0]),
								indicator: res.erros ? "orange" : "green",
							});
							listview.refresh();
						});
				}
			);
		});
	},
};
