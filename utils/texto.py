"""
Funções utilitárias de texto, formatação e conversão numérica (padrão PT-BR).

Usadas tanto pela camada de modelo (busca sem acentos) quanto pelas telas
(formatação de moeda, datas e leitura de campos digitados com vírgula).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime

import config


# --------------------------------------------------------------------------- #
# Normalização e gatilho inteligente
# --------------------------------------------------------------------------- #
def normalizar_texto(texto) -> str:
    """Converte para minúsculas, remove acentos e espaços repetidos.

    É registrada no SQLite como a função SQL ``normalizar`` (ver models.py),
    o que permite buscar "colonia" e encontrar "Colônia".
    """
    if texto is None:
        return ""
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto.lower()).strip()


def _contem_termo(texto_normalizado: str, termo: str) -> bool:
    """Verifica se o termo aparece como palavra inteira dentro do texto.

    Usa lookarounds em vez de ``\\b`` para funcionar com termos que contêm
    hífen ou apóstrofo (ex.: "leave-in", "l'occitane").
    """
    padrao = r"(?<!\w)" + re.escape(normalizar_texto(termo)) + r"(?!\w)"
    return re.search(padrao, texto_normalizado) is not None


def sugerir_categoria(nome: str) -> str | None:
    """Retorna a categoria sugerida a partir das palavras-chave do nome."""
    texto = normalizar_texto(nome)
    if not texto:
        return None
    for termo, categoria in config.PALAVRAS_CHAVE_CATEGORIA:
        if _contem_termo(texto, termo):
            return categoria
    return None


def sugerir_marca(nome: str) -> str | None:
    """Retorna a marca sugerida a partir das linhas de produto conhecidas."""
    texto = normalizar_texto(nome)
    if not texto:
        return None
    for termo, marca in config.PALAVRAS_CHAVE_MARCA:
        if _contem_termo(texto, termo):
            return marca
    return None


# --------------------------------------------------------------------------- #
# Formatação para exibição
# --------------------------------------------------------------------------- #
def formatar_moeda(valor: float | None) -> str:
    """0 -> 'R$ 0,00'; 1234.5 -> 'R$ 1.234,50'."""
    valor = float(valor or 0.0)
    texto = f"{valor:,.2f}"                           # 1,234.50 (padrão en)
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def formatar_inteiro(valor: int | float | None) -> str:
    """1234 -> '1.234'."""
    return f"{int(valor or 0):,}".replace(",", ".")


def formatar_data_hora(valor, com_hora: bool = True) -> str:
    """Converte um timestamp ISO ('2026-09-18 14:33:21') para 'dd/mm/aaaa HH:MM'."""
    if not valor:
        return "—"
    if isinstance(valor, datetime):
        data = valor
    else:
        try:
            data = datetime.fromisoformat(str(valor))
        except ValueError:
            return str(valor)
    return data.strftime("%d/%m/%Y %H:%M" if com_hora else "%d/%m/%Y")


# --------------------------------------------------------------------------- #
# Conversão de valores digitados pelo usuário
# --------------------------------------------------------------------------- #
def converter_para_float(texto) -> float:
    """Aceita '12,50', 'R$ 1.234,56' ou '1234.56'. Lança ValueError em PT-BR."""
    if isinstance(texto, (int, float)):
        return float(texto)
    limpo = str(texto).strip().replace("R$", "").replace(" ", "")
    if not limpo:
        raise ValueError("Informe um valor numérico.")
    if "," in limpo and "." in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")   # 1.234,56 -> 1234.56
    elif "," in limpo:
        limpo = limpo.replace(",", ".")                    # 12,50 -> 12.50
    try:
        return float(limpo)
    except ValueError:
        raise ValueError(f"Valor numérico inválido: '{texto}'.") from None


def converter_para_int(texto) -> int:
    """Aceita '300' ou '1.000'. Lança ValueError em PT-BR."""
    limpo = str(texto).strip()
    if not limpo:
        raise ValueError("Informe um número inteiro.")
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+", limpo):        # separador de milhar
        limpo = limpo.replace(".", "")
    try:
        numero = int(limpo)
    except ValueError:
        raise ValueError(f"Número inteiro inválido: '{texto}'.") from None
    if abs(numero) > config.LIMITE_QUANTIDADE:
        raise ValueError("Quantidade excede o limite permitido.")
    return numero
