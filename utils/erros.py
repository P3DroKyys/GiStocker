"""Registro de falhas técnicas e mensagens sem expor detalhes internos na tela."""
from datetime import datetime
import sqlite3
from models.seguranca import ERROS_BANCO, ERROS_OPERACIONAIS, ErroSeguranca
import traceback
import config


def registrar_falha(falha):
    try:
        with (config.DIRETORIO_BASE / 'erros.log').open('a', encoding='utf-8') as arquivo:
            arquivo.write(f'\n[{datetime.now().isoformat()}]\n')
            # Não registrar mensagem, variáveis, SQL ou linhas-fonte: podem conter segredos.
            arquivo.write(type(falha).__name__ + '\n')
            for quadro in traceback.extract_tb(falha.__traceback__):
                arquivo.write(f'{__import__("pathlib").Path(quadro.filename).name}:{quadro.lineno} {quadro.name}\n')
    except OSError:
        # Um disco cheio não deve causar outra exceção ao tentar registrar a primeira.
        pass


def mensagem_falha(falha):
    if isinstance(falha, (*ERROS_BANCO, OSError, ErroSeguranca)):
        registrar_falha(falha)
        return ('Não foi possível acessar ou gravar os dados. Verifique o espaço em disco '
                'e a permissão da pasta. Confira o estoque e o histórico antes de repetir a operação.')
    return str(falha)
