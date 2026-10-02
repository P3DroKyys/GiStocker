"""Cancela callbacks pendentes antes de destruir uma árvore de widgets."""
import tkinter as tk


def cancelar_tarefas(widget, *, todas=False):
    comandos = set()

    def coletar(item):
        comandos.update(getattr(item, "_tclCommands", None) or ())
        for filho in item.winfo_children():
            coletar(filho)

    if not todas:
        coletar(widget)
    for identificador in widget.tk.call("after", "info"):
        try:
            script = widget.tk.call("after", "info", identificador)[0]
            partes = str(script).split()
            if todas or (partes and partes[0] in comandos):
                # Deixar o destroy do proprietário liberar o comando Tcl. Usar
                # after_cancel no pai poderia removê-lo duas vezes no filho.
                widget.tk.call("after", "cancel", identificador)
        except tk.TclError:
            pass
