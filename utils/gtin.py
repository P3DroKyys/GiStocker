"""Validação local de GTIN-8/12/13/14 com dígito verificador GS1.

Valida formato e matemática; não consulta a atribuição do código na GS1.
"""
import re


def validar_gtin(codigo: str) -> str:
    """Retorna o GTIN aparado, preservando comprimento e zeros à esquerda.

    Rejeita tipos não textuais em vez de convertê-los: zeros já perdidos por
    conversão numérica não podem ser recuperados. Lança ValueError em PT-BR.
    """
    if not isinstance(codigo, str):
        raise ValueError("O código GTIN deve ser informado como texto.")
    codigo = codigo.strip()
    if re.fullmatch(r"^[0-9]+$", codigo) is None:
        raise ValueError("O código GTIN deve conter somente números de 0 a 9, sem espaços internos ou símbolos.")
    if len(codigo) not in (8, 12, 13, 14):
        raise ValueError("Tamanho inválido: o código GTIN deve ter exatamente 8, 12, 13 ou 14 dígitos.")
    if len(set(codigo)) == 1:
        raise ValueError("Código GTIN/EAN inválido: sequência de dígitos repetidos.")

    # O preenchimento existe somente para o cálculo; não altera o valor salvo.
    completo = codigo.zfill(14)
    corpo, dv_informado = completo[:-1], int(completo[-1])
    soma = sum(int(digito) * (3 if indice % 2 == 0 else 1)
               for indice, digito in enumerate(corpo))
    # Quando a soma já é múltipla de 10, o DV correto é zero.
    dv_calculado = (10 - soma % 10) % 10
    if dv_calculado != dv_informado:
        raise ValueError("Código GTIN/EAN inválido")
    return codigo
