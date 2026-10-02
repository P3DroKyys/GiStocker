"""JSON com tipos fechados. Nunca pickle, eval, SQL ou nomes de classe arbitrários."""
from dataclasses import fields, is_dataclass
from datetime import date, datetime
import json
from pathlib import Path

from controllers.controllers import ResultadoMovimentacao, ResultadoDesfazer
from models.models import Produto, LogMovimentacao
from utils.busca import ResultadoPesquisa

TIPOS = {c.__name__:c for c in (Produto,LogMovimentacao,ResultadoMovimentacao,ResultadoDesfazer,ResultadoPesquisa)}
LIMITE = 8 * 1024 * 1024
VERSAO = 1


def codificar(obj):
    if is_dataclass(obj):
        return {'$tipo':type(obj).__name__,'valor':{f.name:codificar(getattr(obj,f.name)) for f in fields(obj)}}
    if isinstance(obj,(date,datetime,Path)):
        return {'$tipo':type(obj).__name__ if not isinstance(obj,Path) else 'Path','valor':str(obj)}
    if isinstance(obj,(list,tuple)):
        return [codificar(v) for v in obj]
    if isinstance(obj,dict):
        return {k:codificar(v) for k,v in obj.items()}
    return obj


def decodificar(obj):
    if isinstance(obj,list):
        return [decodificar(v) for v in obj]
    if isinstance(obj,dict):
        if set(obj)=={'$tipo','valor'}:
            tipo,v = obj['$tipo'],obj['valor']
            if tipo in TIPOS:
                return TIPOS[tipo](**decodificar(v))
            if tipo=='Path':
                return Path(v)
            if tipo in ('date','datetime'):
                return (date if tipo=='date' else datetime).fromisoformat(v)
            raise ValueError('Tipo de resposta não suportado.')
        return {k:decodificar(v) for k,v in obj.items()}
    return obj


def serializar(obj):
    resultado = json.dumps(obj,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode('utf-8')
    if len(resultado)>LIMITE:
        raise ValueError('Resposta extensa demais. Refine o filtro.')
    return resultado


def ler(dados):
    if len(dados)>LIMITE:
        raise ValueError('Mensagem extensa demais.')
    def pares(itens):
        d = {}
        for k,v in itens:
            if k in d:
                raise ValueError('Campo duplicado.')
            d[k] = v
        return d
    try:
        return json.loads(dados,object_pairs_hook=pares,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Número inválido.')))
    except RecursionError:
        raise ValueError('Estrutura da mensagem excede o limite.') from None
