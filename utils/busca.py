"""Busca local por termos, relevância e distância Damerau-Levenshtein.

O índice existe somente na memória da sessão. Não cria arquivos sem criptografia
nem depende de extensões SQL. Aproximação é fallback e nunca corrige GTINs.
"""
from collections import defaultdict
from dataclasses import dataclass
import re

from rapidfuzz.distance import DamerauLevenshtein

from utils.texto import normalizar_texto

PALAVRAS_LIGACAO = {'de', 'da', 'do', 'das', 'dos', 'e', 'com', 'para', 'em'}


def termos(texto):
    # Separa também 200ml -> 200, ml. % e _ são literais, nunca curingas SQL.
    return re.findall(r'[^\W\d_]+|[0-9]+|[%_]', normalizar_texto(texto))


@dataclass
class ResultadoPesquisa:
    produtos: list
    aproximada: bool = False
    aviso: str = ''


class IndiceProdutos:
    def __init__(self, produtos):
        self.produtos = {p.id: p for p in produtos}
        self.nomes = {p.id: ' '.join(termos(p.nome)) for p in self.produtos.values()}
        self.ordenados = sorted(self.produtos, key=lambda i: (normalizar_texto(self.produtos[i].nome), i))
        self.vocabulario = defaultdict(dict)
        self.codigos = defaultdict(set)
        for p in self.produtos.values():
            for campo, peso in ((p.nome, 100), (p.marca, 70), (p.categoria, 45)):
                for termo in set(termos(campo)):
                    self.vocabulario[termo][p.id] = max(peso, self.vocabulario[termo].get(p.id, 0))
            for codigo in p.codigos:
                self.codigos[codigo].add(p.id)

    def _por_termo(self, termo, aproximar=False):
        encontrados = {}
        for palavra, produtos in self.vocabulario.items():
            afinidade = 0
            if termo == palavra:
                afinidade = 100
            elif termo.isalpha() and palavra.isalpha():
                if palavra.startswith(termo):
                    afinidade = 85
                elif len(termo) >= 3 and termo in palavra:
                    afinidade = 65
                elif aproximar and 4 <= len(termo) <= 64:
                    limite = 1 if len(termo) < 8 else 2
                    if abs(len(termo) - len(palavra)) <= limite:
                        distancia = DamerauLevenshtein.distance(termo, palavra, score_cutoff=limite)
                        if distancia <= limite:
                            afinidade = 50 - 5 * distancia
            if afinidade:
                for pid, peso in produtos.items():
                    encontrados[pid] = max(encontrados.get(pid, 0), afinidade * peso)
        if termo.isascii() and termo.isdigit() and len(termo) >= 3:
            for codigo, produtos in self.codigos.items():
                if termo in codigo:
                    for pid in produtos:
                        encontrados[pid] = max(encontrados.get(pid, 0), 6000)
        return encontrados

    def pesquisar(self, consulta):
        consulta = normalizar_texto(consulta)
        if len(consulta) > 256:
            return ResultadoPesquisa([], aviso='Pesquisa muito longa. Use até 256 caracteres.')
        if not consulta:
            return ResultadoPesquisa([self.produtos[i] for i in self.ordenados])
        # Identificadores têm precedência e nunca passam por aproximação.
        if consulta in self.codigos:
            return ResultadoPesquisa([self.produtos[i] for i in sorted(self.codigos[consulta])])
        if re.fullmatch(r'#[0-9]+', consulta):
            produto = self.produtos.get(int(consulta[1:]))
            return ResultadoPesquisa([produto] if produto else [])
        palavras = list(dict.fromkeys(termos(consulta)))
        relevantes = [p for p in palavras if p not in PALAVRAS_LIGACAO]
        palavras = relevantes or palavras
        if not palavras:
            return ResultadoPesquisa([], aviso='Digite um nome, marca, categoria, código ou ID.')
        if len(palavras) > 16:
            return ResultadoPesquisa([], aviso='Refine a pesquisa para até 16 palavras.')

        for aproximada in (False, True):
            pontuacoes = [self._por_termo(p, aproximada) for p in palavras]
            candidatos = set(pontuacoes[0]).intersection(*(set(p) for p in pontuacoes[1:]))
            if candidatos:
                frase = ' '.join(termos(consulta))

                def ordem(pid):
                    pontos = sum(p[pid] for p in pontuacoes)
                    if self.nomes[pid] == frase:
                        pontos += 100000
                    elif self.nomes[pid].startswith(frase):
                        pontos += 5000
                    return (-pontos, normalizar_texto(self.produtos[pid].nome), pid)

                return ResultadoPesquisa([self.produtos[i] for i in sorted(candidatos, key=ordem)], aproximada)
        # Só depois de tentar trechos: 12 dígitos também podem ser o prefixo de um EAN-13.
        if consulta.isascii() and consulta.isdigit() and len(consulta) in (8, 12, 13, 14):
            return ResultadoPesquisa([], aviso='Código de barras não encontrado. Confira os dígitos.')
        return ResultadoPesquisa([])
