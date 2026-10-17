"""Arquivos do usuário. Sem SQL executável e sem acesso ao banco pela interface."""
import json
import os
from pathlib import Path
from uuid import uuid4

LIMITE_ARQUIVO = 64 * 1024 * 1024
BLOCO = 128 * 1024


def json_bytes(valor):
    return json.dumps(valor, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


def ler_json(conteudo):
    def pares(itens):
        resultado = {}
        for chave, valor in itens:
            if chave in resultado:
                raise ValueError('O backup contém campos duplicados.')
            resultado[chave] = valor
        return resultado

    def constante(_):
        raise ValueError('O backup contém números inválidos.')

    try:
        return json.loads(conteudo.decode('utf-8-sig'), object_pairs_hook=pares, parse_constant=constante)
    except (UnicodeError, RecursionError, json.JSONDecodeError):
        raise ValueError('Arquivo JSON inválido ou incompleto.') from None


def ler_arquivo(caminho, progresso):
    partes = bytearray()
    with Path(caminho).open('rb') as arquivo:
        total = os.fstat(arquivo.fileno()).st_size
        if not 0 < total <= LIMITE_ARQUIVO:
            raise ValueError('O arquivo deve ter conteúdo e no máximo 64 MB.')
        while bloco := arquivo.read(BLOCO):
            partes.extend(bloco)
            if len(partes) > LIMITE_ARQUIVO:
                raise ValueError('O arquivo excede 64 MB.')
            progresso('Leitura do arquivo', len(partes), max(total, len(partes)))
    return bytes(partes)


class SaidaAtomica:
    """Só publica o arquivo completo; falhas preservam um destino já existente."""
    def __init__(self, destino):
        self.destino = Path(destino)
        self.parcial = self.destino.with_name('.gistocker-' + uuid4().hex + '.parcial')
        self.arquivo = None

    def __enter__(self):
        self.arquivo = self.parcial.open('xb')
        return self.arquivo

    def __exit__(self, tipo, valor, tb):
        try:
            if tipo is None:
                self.arquivo.flush()
                os.fsync(self.arquivo.fileno())
            self.arquivo.close()
            if tipo is None:
                os.replace(self.parcial, self.destino)
        finally:
            if self.arquivo and not self.arquivo.closed:
                self.arquivo.close()
            self.parcial.unlink(missing_ok=True)
