"""
Ponto de entrada da aplicação.

Exibe o acesso antes de abrir os dados. Após descriptografar o banco,
a janela instancia os controladores e as telas da sessão.

Execute a partir da pasta do projeto:  python main.py
"""
import os
import sys
import traceback
from datetime import datetime

import config  # importa só sys/pathlib: seguro carregar antes de tudo

# --------------------------------------------------------------------------- #
# Quando empacotado como .exe sem console (PyInstaller --windowed),
# sys.stdout e sys.stderr são None. Qualquer biblioteca que escreva neles
# (o customtkinter faz isso ao avisar sobre fontes) derrubaria o programa na
# importação. Por isso, ANTES de importar as bibliotecas gráficas, redirecionamos:
#   stdout/stderr -> descartados; falhas tratadas usam log sanitizado.
# --------------------------------------------------------------------------- #
if getattr(sys, "frozen", False):
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        # Bibliotecas podem imprimir argumentos sensíveis; o log da aplicação
        # registra apenas tipo/local da falha, sem conteúdo dos dados ou senha.
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

import customtkinter as ctk  # noqa: E402 - precisa vir após o redirecionamento acima

from models.seguranca import Cofre  # noqa: E402
from views.main_view import JanelaPrincipal  # noqa: E402


def main() -> None:
    if sys.platform == "win32":
        # Identidade própria na barra de tarefas, inclusive rodando pelo Python.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GiStocker.GestorEstoque")
    from servico.executar import garantir_agente
    cofre = garantir_agente()
    ctk.set_appearance_mode(cofre.obter_tema())
    ctk.set_default_color_theme(config.TEMA_COR)
    try:
        janela = JanelaPrincipal(cofre)
        janela.mainloop()
    finally:
        cofre.fechar()


def _registrar_falha(erro: BaseException) -> None:
    """Grava o erro em erros.log ao lado do programa e avisa o usuário.
    Necessário porque o .exe roda sem console e, sem isso, uma falha na
    inicialização passaria despercebida."""
    caminho_log = (config.DIRETORIO_DADOS if config.INSTALADO else config.DIRETORIO_BASE) / "erros.log"
    try:
        with open(caminho_log, "a", encoding="utf-8") as arquivo:
            arquivo.write(f"\n===== {datetime.now():%d/%m/%Y %H:%M:%S} =====\n")
            arquivo.write(type(erro).__name__ + "\n")
    except OSError:
        pass
    if any(arg in sys.argv for arg in ('--servico','--agente','--verificar-servico','--importar-portatil')):
        return  # nunca abrir diálogos na sessão 0 ou em helpers do instalador
    try:
        from views.dialogos import mostrar_dialogo
        mostrar_dialogo("Erro ao iniciar",
                        f"Não foi possível iniciar o programa. Verifique a instalação e as permissões.\n\nRegistro: {caminho_log}", 'erro')
    except Exception:  # noqa: BLE001 - último recurso, nada mais a fazer
        # Se o próprio toolkit/tema falhar, ainda precisamos comunicar a inicialização.
        try:
            from tkinter import messagebox
            messagebox.showerror("Erro ao iniciar", f"Não foi possível iniciar. Registro: {caminho_log}")
        except Exception:
            pass


if __name__ == "__main__":
    try:
        if '--verificar-servico' in sys.argv:
            from servico.cliente import Cliente
            Cliente(config.DIRETORIO_DADOS,True).chamar('status')
        elif '--importar-portatil' in sys.argv:
            from servico.importacao import importar_portatil
            importar_portatil(sys.argv[sys.argv.index('--importar-portatil')+1],config.DIRETORIO_DADOS)
        elif '--servico' in sys.argv:
            from servico.executar import hospedar_servico
            hospedar_servico()
        elif '--agente' in sys.argv:
            from servico.executar import executar
            executar(config.DIRETORIO_DADOS)
        else:
            main()
    except Exception as falha:  # noqa: BLE001
        _registrar_falha(falha)
        sys.exit(1)
