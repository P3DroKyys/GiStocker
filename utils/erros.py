"""Registro de falhas técnicas e mensagens sem expor detalhes internos na tela."""
from datetime import datetime
from pathlib import Path
import sqlite3
from models.seguranca import ERROS_BANCO, ERROS_OPERACIONAIS, ErroSeguranca, ErroSessao
import traceback
import config
from controllers.controllers import ErroNegocio

# Falhas que as telas exibem com mensagem_falha; ValueError chega do agente como recusa.
ERROS_EXIBIVEIS = (ErroNegocio, ValueError, ErroSeguranca, *ERROS_BANCO, OSError)


def registrar_falha(falha, pasta=None):
    """Interface usa config.DIRETORIO_LOGS; o agente informa ``<raiz>/logs``."""
    try:
        destino = Path(pasta) if pasta is not None else config.DIRETORIO_LOGS
        destino.mkdir(parents=True, exist_ok=True)
        with (destino / 'erros.log').open('a', encoding='utf-8') as arquivo:
            arquivo.write(f'\n[{datetime.now().isoformat()}]\n')
            # Não registrar mensagem, variáveis, SQL ou linhas-fonte: podem conter segredos.
            arquivo.write(type(falha).__name__ + '\n')
            for quadro in traceback.extract_tb(falha.__traceback__):
                arquivo.write(f'{Path(quadro.filename).name}:{quadro.lineno} {quadro.name}\n')
    except OSError:
        # Um disco cheio não deve causar outra exceção ao tentar registrar a primeira.
        pass


def mensagem_falha(falha):
    if isinstance(falha, ErroSessao):
        return 'Sessão expirada ou bloqueada. Desbloqueie o software novamente.'
    if isinstance(falha, (*ERROS_BANCO, OSError)):
        registrar_falha(falha)
        return ('Não foi possível acessar ou gravar os dados. Verifique o espaço em disco '
                'e a permissão da pasta. Confira o estoque e o histórico antes de repetir a operação.')
    # ErroNegocio, ValueError e ErroSeguranca do serviço já trazem texto para o usuário.
    return str(falha)
