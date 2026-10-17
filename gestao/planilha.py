"""CSV UTF-8 para Excel. GTIN sempre textual; quantidade é uma entrada aditiva."""
import csv
import io

import config
from controllers.controllers import (ControladorEstoque, ErroNegocio, agora_texto,
                                     _validar_valor_monetario)
from models.models import LogMovimentacao
from multicanal.motor import Motor
from utils.gtin import validar_gtin
from utils.texto import converter_para_int, normalizar_texto

CABECALHOS = ('codigo', 'nome', 'marca', 'categoria', 'quantidade', 'preco_venda_base', 'custo_unitario')
LIMITE_LINHAS = 100_000
MARCAS = {normalizar_texto(m): m for m in config.MARCAS}
CATEGORIAS = {normalizar_texto(c): c for c in config.CATEGORIAS}


def modelo():
    return ('\ufeff' + ';'.join(CABECALHOS) + '\r\n').encode('utf-8')


def ler(conteudo):
    try:
        texto = conteudo.decode('utf-8-sig')
    except UnicodeError:
        raise ValueError('Salve a planilha como CSV UTF-8 no Excel.') from None
    if '\0' in texto:
        raise ValueError('O arquivo não é um CSV de texto válido.')
    primeira = texto.splitlines()[0] if texto else ''
    delimitador = ';' if ';' in primeira else ','
    try:
        leitor = csv.reader(io.StringIO(texto, newline=''), delimiter=delimitador, strict=True)
        if next(leitor, []) != list(CABECALHOS):
            raise ValueError('Colunas incompatíveis. Use o modelo: ' + '; '.join(CABECALHOS))
        linhas = []
        for valores in leitor:
            if not valores or not any(v.strip() for v in valores):
                continue
            linhas.append((leitor.line_num, valores))
            if len(linhas) > LIMITE_LINHAS:
                raise ValueError('Importe no máximo 100.000 linhas por arquivo.')
        if not linhas:
            raise ValueError('A planilha contém apenas os cabeçalhos ou linhas vazias.')
        return linhas
    except csv.Error:
        raise ValueError('CSV malformado. Confira as aspas e salve novamente como CSV UTF-8.') from None


def validar(valores):
    if len(valores) != len(CABECALHOS):
        raise ValueError('Quantidade de colunas diferente do modelo.')
    codigo, nome, marca, categoria, quantidade, preco, custo = [v.strip() for v in valores]
    codigo = validar_gtin(codigo)
    if not nome or len(nome) > 500:
        raise ValueError('Informe um nome com 1 a 500 caracteres.')
    # Grava sempre a grafia do cadastro; a planilha pode variar caixa e acentos.
    marca, categoria = MARCAS.get(normalizar_texto(marca)), CATEGORIAS.get(normalizar_texto(categoria))
    if marca is None or categoria is None:
        raise ValueError('Marca ou categoria não cadastrada no sistema.')
    try:
        quantidade = converter_para_int(quantidade)   # mesma regra das telas: "1.000" vale 1000
        if quantidade < 0:
            raise ValueError
    except ValueError:
        raise ValueError('Quantidade: use um inteiro não negativo, como 12 ou 1.000.') from None
    preco = _validar_valor_monetario(preco, 'Preço de venda') if preco else None
    custo = _validar_valor_monetario(custo, 'Custo unitário') if custo else None
    return codigo, nome, marca, categoria, quantidade, preco, custo


def importar(banco, conteudo, lote, recibo):
    linhas = ler(conteudo)
    c, motor = ControladorEstoque(banco), Motor(banco)
    resultado = {'novos': 0, 'atualizados': 0, 'erros': [], 'total': len(linhas)}
    codigos, produtos = set(), set()
    with banco.transacao():
        for indice, (numero, valores) in enumerate(linhas, 1):
            try:
                dados = validar(valores)
                codigo, nome, marca, categoria, quantidade, preco, custo = dados
                p = c.resolver_codigo_barras(codigo)
                if codigo in codigos or p and p.id in produtos:
                    raise ValueError('Produto repetido na planilha, inclusive por outro GTIN vinculado.')
                # Só erros esperados de linha são ignorados. Falha de disco/SQL aborta o lote inteiro.
                with banco.transacao():
                    observacao = f'Importação CSV · lote {lote} · linha {numero}'
                    anterior = p.estoque_atual if p else 0
                    novo = p is None
                    if novo:
                        p = c.cadastrar_produto(nome, marca, categoria, preco, custo, quantidade, [codigo])
                        log_id = banco.conexao.execute('SELECT max(id) FROM Logs_Movimentacao WHERE produto_id=?', (p.id,)).fetchone()[0]
                    else:
                        if quantidade:
                            movimento = c.registrar_entrada(p.id, quantidade, custo)
                            log_id = movimento.log_id
                            p = movimento.produto
                        else:
                            # Quantidade zero permite corrigir custo e preço sem simular entrada.
                            # Só a troca de custo vira Ajuste no histórico (e pode ser desfeita).
                            log_id = None
                            if custo is not None:
                                log_id = c.logs.inserir(LogMovimentacao(
                                    None, p.id, config.TIPO_AJUSTE, 0, custo, agora_texto(),
                                    p.estoque_atual, p.custo_medio, observacao=observacao))
                                p.custo_medio = round(custo, config.CASAS_DECIMAIS_CUSTO)
                                c.produtos.atualizar_estoque_custo(p.id, p.estoque_atual, p.custo_medio)
                        p.nome, p.marca, p.categoria = nome, marca, categoria
                        if preco is not None:
                            p.preco_venda_base = preco
                        c.produtos.atualizar_dados(p)
                    if log_id:
                        banco.conexao.execute('UPDATE Logs_Movimentacao SET observacao=? WHERE id=?', (observacao, log_id))
                    motor.evento(f'importacao:{lote}:{numero}', p.id, p.estoque_atual - anterior,
                                 'FISICO', 'IMPORTACAO_CSV', lote, log_id)
                codigos.add(codigo)
                produtos.add(p.id)
                resultado['novos' if novo else 'atualizados'] += 1
            except (ValueError, ErroNegocio) as erro:
                resultado['erros'].append({'linha': numero, 'motivo': str(erro)})
            if indice % 100 == 0 or indice == len(linhas):
                yield ('Importação de linhas', indice, len(linhas))
        motor.preparar()
        recibo(resultado)
    banco._indice_pesquisa = banco._versao_pesquisa = None
    return resultado
