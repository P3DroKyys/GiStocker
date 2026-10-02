"""Mesma base para agente de desenvolvimento e serviço instalado."""
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import config
from servico.nucleo import Nucleo
from servico.pipe import servir


def executar(raiz, parar=None, producao=False):
    from models.seguranca import TravaSessao
    raiz = Path(raiz)
    trava = TravaSessao(raiz/'.agente.lock')
    try:
        servir(Nucleo(raiz),raiz,parar or threading.Event(),producao)
    finally:
        trava.fechar()


def garantir_agente():
    from servico.cliente import Cliente
    cliente = Cliente(config.DIRETORIO_DADOS,config.INSTALADO)
    try:
        cliente.chamar('status')
        return cliente
    except Exception:
        if config.INSTALADO:
            raise RuntimeError('O serviço GiStocker está indisponível. Use a opção Reparar do instalador.') from None
    comando = [sys.executable]
    if not getattr(sys,'frozen',False):
        comando.append(str(config.DIRETORIO_BASE/'main.py'))
    comando.append('--agente')
    # Processo sem janela, independente da interface. Não recebe senha por argumentos.
    subprocess.Popen(comando,cwd=config.DIRETORIO_BASE,stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS)
    for _ in range(40):
        time.sleep(.25)
        try:
            cliente.chamar('status')
            return cliente
        except Exception:
            continue
    raise RuntimeError('O agente local não iniciou. Execute a preparação do ambiente e confira as permissões.')


def hospedar_servico():
    import servicemanager
    import win32service
    import win32serviceutil

    class ServicoGiStocker(win32serviceutil.ServiceFramework):
        _svc_name_ = 'GiStocker'
        _svc_display_name_ = 'GiStocker — estoque local'

        def __init__(self, args):
            super().__init__(args)
            self.parar = threading.Event()

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            self.parar.set()

        def SvcDoRun(self):
            executar(config.DIRETORIO_DADOS,self.parar,True)

    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(ServicoGiStocker)
    servicemanager.StartServiceCtrlDispatcher()
