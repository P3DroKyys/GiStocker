"""Named Pipe local, DACL explícita, identidade Windows e mensagens limitadas."""
import hashlib
import os
from pathlib import Path
import struct
import time

import pywintypes
import win32api
import win32con
import win32file
import win32pipe
import win32security

from servico.protocolo import LIMITE, ler, serializar

ERROS_TRANSPORTE = (OSError, pywintypes.error)


def nome_pipe(raiz, producao=False):
    if producao:
        return r'\\.\pipe\GiStocker.v2'
    resumo = hashlib.sha256(str(Path(raiz).resolve()).casefold().encode()).hexdigest()[:20]
    return r'\\.\pipe\GiStocker.dev.' + resumo


def sid_atual():
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32con.TOKEN_QUERY)
    try:
        return win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token,win32security.TokenUser)[0])
    finally:
        token.Close()


def atributos(producao=False, raiz=None):
    # 0x12019b exclui FILE_CREATE_PIPE_INSTANCE (0x4) para o operador.
    operador = win32security.ConvertSidToStringSid(win32security.LookupAccountName(None,'GiStocker Operadores')[0]) if producao else sid_atual()
    dono = sid_atual()
    sddl = f'D:P(A;;GA;;;SY)(A;;GA;;;{dono})(A;;0x12019b;;;{operador})'
    if producao:
        import json
        sddl += '(A;;0x12019b;;;BA)'
        arquivo = Path(raiz)/'operadores.json'
        if arquivo.stat().st_size>8192:
            raise ValueError('Configuração de operadores inválida.')
        operadores = json.loads(arquivo.read_text(encoding='utf-8-sig'))
        if not isinstance(operadores, list) or not all(isinstance(sid, str) for sid in operadores):
            raise ValueError('Configuração de operadores inválida: informe uma lista de SIDs.')
        for sid in operadores:
            # Canonicalizar evita injeção de fragmentos SDDL.
            try:
                canonico=win32security.ConvertSidToStringSid(win32security.ConvertStringSidToSid(sid))
            except pywintypes.error:
                raise ValueError('Configuração de operadores inválida: SID inválido.') from None
            sddl += f'(A;;0x12019b;;;{canonico})'
    sd = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(sddl,win32security.SDDL_REVISION_1)
    sa = pywintypes.SECURITY_ATTRIBUTES()
    sa.SECURITY_DESCRIPTOR = sd
    return sa


def _ler_exato(handle, n, prazo):
    partes = bytearray()
    while len(partes)<n:
        if time.monotonic()>prazo:
            raise TimeoutError('Tempo de comunicação excedido.')
        try:
            _, bloco = win32file.ReadFile(handle,min(65536,n-len(partes)))
            if bloco:
                partes.extend(bloco)
            else:
                time.sleep(.01)
        except pywintypes.error as erro:
            if erro.winerror==232:  # PIPE_NOWAIT sem dados ainda
                time.sleep(.01)
            else:
                raise
    return bytes(partes)


def receber(handle, segundos):
    prazo = time.monotonic()+segundos
    tamanho = struct.unpack('!I',_ler_exato(handle,4,prazo))[0]
    if not 0<tamanho<=LIMITE:
        raise ValueError('Tamanho inválido.')
    return ler(_ler_exato(handle,tamanho,prazo))


def enviar(handle, objeto, segundos=10):
    dados = serializar(objeto)
    dados = struct.pack('!I',len(dados))+dados
    pos = 0
    prazo = time.monotonic()+segundos
    while pos<len(dados):
        if time.monotonic()>prazo:
            raise TimeoutError('Tempo de escrita excedido.')
        _, gravados = win32file.WriteFile(handle,dados[pos:pos+32768])
        pos += gravados
        if not gravados:
            time.sleep(.01)


def identidade_cliente(handle):
    win32security.ImpersonateNamedPipeClient(handle)
    try:
        token = win32security.OpenThreadToken(win32api.GetCurrentThread(),win32con.TOKEN_QUERY,True)
        try:
            return win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token,win32security.TokenUser)[0])
        finally:
            token.Close()
    finally:
        win32security.RevertToSelf()


def servir(nucleo, raiz, parar, producao=False):
    nome = nome_pipe(raiz,producao)
    handle = win32pipe.CreateNamedPipe(nome,win32pipe.PIPE_ACCESS_DUPLEX|0x00080000,
        win32pipe.PIPE_TYPE_BYTE|win32pipe.PIPE_READMODE_BYTE|win32pipe.PIPE_NOWAIT|win32pipe.PIPE_REJECT_REMOTE_CLIENTS,
        1,65536,65536,1000,atributos(producao,raiz))
    proxima_manutencao = 0
    falhas_manutencao = 0
    try:
        while not parar.is_set():
            if not producao and nucleo.deve_encerrar():
                break
            try:
                win32pipe.ConnectNamedPipe(handle,None)
            except pywintypes.error as erro:
                if erro.winerror==232:
                    win32pipe.DisconnectNamedPipe(handle)
                    continue
                if erro.winerror==536:
                    if time.monotonic() >= proxima_manutencao:
                        try:
                            nucleo.manutencao()
                        except Exception as falha:
                            from utils.erros import registrar_falha
                            registrar_falha(falha, pasta=Path(raiz)/'logs')
                            falhas_manutencao += 1
                            nucleo.falha_manutencao = 'A manutenção do agente falhou. Nova tentativa agendada; consulte o registro de erros.'
                            proxima_manutencao = time.monotonic() + min(30, 2 ** min(falhas_manutencao, 5))
                        else:
                            falhas_manutencao = 0
                            nucleo.falha_manutencao = None
                            proxima_manutencao = time.monotonic() + 1
                    parar.wait(.02)
                    continue
                if erro.winerror!=535:
                    raise
            try:
                pedido = receber(handle,3)
                identidade = identidade_cliente(handle)
                resposta = nucleo.executar(pedido,identidade)
                try:
                    enviar(handle,resposta)
                except ValueError:
                    # Serialização ocorre antes de escrever qualquer byte no pipe.
                    enviar(handle,dict(v=resposta['v'],id=resposta['id'],ok=False,erro='ValueError',
                                       mensagem='Resposta extensa demais ou incompatível. Refine o filtro ou carregue outra página.'))
                # Espera o cliente consumir antes de DisconnectNamedPipe descartar buffers.
                limite = time.monotonic()+3
                while time.monotonic()<limite:
                    try:
                        _, ack = win32file.ReadFile(handle,1)
                        if ack==b'!':
                            break
                    except pywintypes.error as erro:
                        if erro.winerror!=232:
                            break
                    parar.wait(.01)
            except (OSError,ValueError,pywintypes.error):
                pass  # não registrar payload, senha, token nem dados pessoais
            finally:
                win32pipe.DisconnectNamedPipe(handle)
    finally:
        handle.Close()
        nucleo.fechar()


def chamar(nome, pedido, producao=False):
    win32pipe.WaitNamedPipe(nome,5000)
    h = win32file.CreateFile(nome,win32con.GENERIC_READ|0x0102,0,None,
                            win32con.OPEN_EXISTING,0x00110000,None)  # SQOS: identification
    try:
        if producao:
            import win32serviceutil
            import win32service
            scm = win32service.OpenSCManager(None,None,win32service.SC_MANAGER_CONNECT)
            try:
                svc = win32service.OpenService(scm,'GiStocker',win32service.SERVICE_QUERY_STATUS)
                try:
                    pid = win32service.QueryServiceStatusEx(svc)['ProcessId']
                    if not pid or win32pipe.GetNamedPipeServerProcessId(h)!=pid:
                        raise PermissionError('O servidor local não é o serviço instalado.')
                finally:
                    win32service.CloseServiceHandle(svc)
            finally:
                win32service.CloseServiceHandle(scm)
        win32pipe.SetNamedPipeHandleState(h,win32pipe.PIPE_READMODE_BYTE|win32pipe.PIPE_NOWAIT,None,None)
        enviar(h,pedido)
        resultado = receber(h,120)
        win32file.WriteFile(h,b'!')
        return resultado
    finally:
        h.Close()
