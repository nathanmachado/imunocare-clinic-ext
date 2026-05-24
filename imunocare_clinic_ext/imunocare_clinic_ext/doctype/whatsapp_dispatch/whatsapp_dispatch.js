// Copyright (c) 2026, Imunocare
frappe.ui.form.on("WhatsApp Dispatch", {
	refresh(frm) {
		if (frm.doc.status === "Pendente" && !frm.is_new()) {
			frm.add_custom_button(__("Autorizar e Enviar"), () => {
				frappe.confirm(
					__("Enviar esta mensagem para {0} ({1})?", [frm.doc.patient_name, frm.doc.to]),
					() => {
						frm.call("autorizar_e_enviar").then(() => frm.reload_doc());
					}
				);
			}).addClass("btn-primary");

			frm.add_custom_button(__("Cancelar disparo"), () => {
				frm.call("cancelar").then(() => frm.reload_doc());
			});
		}
	},
});
