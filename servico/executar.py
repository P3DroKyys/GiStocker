"""Mesma base para agente de desenvolvimento e serviço instalado."""
import os
import hashlib
from pathlib import Path
import subprocess
import sys
import threading
import time

import config
from servico.nucleo import Nucleo
from servico.pipe import servir
from models.seguranca import ErroSeguranca, TravaSessao


def revisao_codigo():
    resumo = hashlib.sha256()
    raiz = Path(__file__).resolve().parents[1]
    arquivos = [Path(sys.executable)] if getattr(sys, 'frozen', False) else sorted(
        [raiz/'main.py', raiz/'config.py'] + [p for pasta in ('servico','models','controllers','multicanal','gestao','utils','views')
                                          for p in (raiz/pasta).glob('*.py')])
    for arquivo in arquivos:
        resumo.update(arquivo.name.encode('utf-8'))
        with arquivo.open('rb') as entrada:
            for bloco in iter(lambda: entrada.read(1024 * 1024), b''):
                resumo.update(bloco)
    return resumo.hexdigest()


def executar(raiz, parar=None, producao=False):
    from models.seguranca import TravaSessao
    raiz = Path(raiz)
    trava = TravaSessao(raiz/'.agente.lock')
    try:
        servir(Nucleo(raiz,producao),raiz,parar or threading.Event(),producao)
    finally:
        trava.fechar()


def garantir_agente(raiz=None, producao=None):
    from servico.cliente import Cliente
    raiz = Path(raiz) if raiz is not None else config.DIRETORIO_DADOS
    producao = config.INSTALADO if producao is None else producao
    cliente = Cliente(raiz,producao)
    revisao = revisao_codigo()
    try:
        status = cliente.chamar('status')
    except ErroSeguranca:
        if producao:
            raise RuntimeError('O serviço GiStocker está indisponível. Use a opção Reparar do instalador.') from None
    else:
        if status.get('versao') == config.VERSAO_APP and status.get('revisao') == revisao:
            return cliente
        if producao:
            raise RuntimeError('A versão do serviço difere da interface. Use a opção Reparar do instalador.')
        try:
            autorizado = cliente.chamar('encerrar_agente')
        except (ErroSeguranca, ValueError):
            raise RuntimeError('O agente antigo não oferece encerramento cooperativo. Encerre a versão anterior antes de atualizar.') from None
        if not autorizado:
            raise RuntimeError('Feche as outras interfaces e encerre a simulação antes de atualizar o agente.')
        for _ in range(40):
            try:
                trava = TravaSessao(raiz/'.agente.lock')
            except ErroSeguranca:
                time.sleep(.1)
            else:
                trava.fechar()
                break
        else:
            raise RuntimeError('O agente anterior ainda está encerrando. Aguarde antes de atualizar.')
    comando = [sys.executable]
    if not getattr(sys,'frozen',False):
        comando.append(str(config.DIRETORIO_BASE/'main.py'))
    comando.extend(('--agente', '--raiz', str(raiz)))
    # Processo sem janela, independente da interface. Não recebe senha por argumentos.
    subprocess.Popen(comando,cwd=config.DIRETORIO_BASE,stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS)
    for _ in range(40):
        time.sleep(.25)
        try:
            status = cliente.chamar('status')
            if status.get('versao') == config.VERSAO_APP and status.get('revisao') == revisao:
                return cliente
        except ErroSeguranca:
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
