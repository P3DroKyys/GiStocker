"""Planilha de produtos: modelo Excel (.xlsx) e importação de .xlsx ou CSV UTF-8.

GTIN sempre textual; quantidade é uma entrada aditiva.
"""
from contextlib import closing
import csv
import io
import warnings
import zipfile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

import config
from controllers.controllers import (ControladorEstoque, ErroNegocio, agora_texto,
                                     _validar_valor_monetario)
from models.models import LogMovimentacao
from multicanal.motor import Motor
from utils.gtin import validar_gtin
from utils.texto import converter_para_int, normalizar_texto

# (chave do CSV, título no Excel, obrigatória, largura, formato, orientação ao preencher)
COLUNAS = (
    ('codigo', 'Código de barras (GTIN)', True, 24, '@',
     'Digite os 8, 12, 13 ou 14 dígitos do código. A coluna já está como Texto para manter os zeros à esquerda.'),
    ('nome', 'Nome do produto', True, 44, '@', 'Nome como deve aparecer no sistema (até 500 caracteres).'),
    ('marca', 'Marca', True, 24, '@', 'Selecione na lista uma das marcas cadastradas no sistema.'),
    ('categoria', 'Categoria', True, 20, '@', 'Selecione na lista uma das categorias cadastradas no sistema.'),
    ('quantidade', 'Quantidade a adicionar', False, 16, '0',
     'Unidades a SOMAR ao estoque atual, não o saldo final. Vazio vale 0 e só atualiza o cadastro.'),
    ('preco_venda_base', 'Preço de venda (R$)', False, 18, '#,##0.00',
     'Opcional. Produto novo sem preço fica com R$ 0,00. Em produto existente, vazio mantém o preço atual.'),
    ('custo_unitario', 'Custo unitário (R$)', False, 18, '#,##0.00',
     'Opcional. Com quantidade, entra no custo médio. Com quantidade 0, substitui o custo atual. '
     'Produto novo sem custo fica com R$ 0,00.'),
)
CABECALHOS = tuple(c[0] for c in COLUNAS)
TITULOS = tuple(c[1] for c in COLUNAS)
_CABECALHOS_ACEITOS = ([normalizar_texto(t) for t in CABECALHOS], [normalizar_texto(t) for t in TITULOS])
LIMITE_LINHAS = 100_000
LIMITE_DESCOMPACTADO = 256 * 1024 * 1024
ABA_PRODUTOS, ABA_LISTAS = 'Produtos', 'Listas'
MARCAS = {normalizar_texto(m): m for m in config.MARCAS}
CATEGORIAS = {normalizar_texto(c): c for c in config.CATEGORIAS}

_COR_OBRIGATORIA, _COR_OPCIONAL, _COR_TITULO = '7A2E5A', 'E9D5E1', '4A1B37'

# O Excel regrava as listas suspensas como extensão x14; a leitura só precisa dos valores.
warnings.filterwarnings('ignore', message='Data Validation extension is not supported', module='openpyxl')


def modelo():
    livro = Workbook()
    produtos = livro.active
    produtos.title = ABA_PRODUTOS
    _preencher_produtos(produtos, _criar_listas(livro))
    _preencher_instrucoes(livro.create_sheet('Instruções'))
    livro.active = 0
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


def _criar_listas(livro):
    aba = livro.create_sheet(ABA_LISTAS)
    aba.sheet_state = 'hidden'
    intervalos = {}
    for coluna, (titulo, valores) in enumerate((('Marcas', config.MARCAS), ('Categorias', config.CATEGORIAS)), 1):
        letra = aba.cell(1, coluna, titulo).column_letter
        for linha, valor in enumerate(valores, 2):
            aba.cell(linha, coluna, valor)
        intervalos[titulo] = f"{ABA_LISTAS}!${letra}$2:${letra}${len(valores) + 1}"
    return intervalos


def _preencher_produtos(aba, listas):
    borda = Border(bottom=Side(style='medium', color=_COR_TITULO))
    ultima = LIMITE_LINHAS + 1
    regras = {
        'codigo': DataValidation(type='textLength', operator='between', formula1='8', formula2='14',
                                 error='O código deve ter 8, 12, 13 ou 14 dígitos.'),
        'marca': DataValidation(type='list', formula1=listas['Marcas'],
                                error='Escolha uma marca da lista. Para usar outra, cadastre-a no sistema.'),
        'categoria': DataValidation(type='list', formula1=listas['Categorias'],
                                    error='Escolha uma categoria da lista.'),
        'quantidade': DataValidation(type='whole', operator='greaterThanOrEqual', formula1='0',
                                     error='Use um número inteiro igual ou maior que zero.'),
        'preco_venda_base': DataValidation(type='decimal', operator='between', formula1='0',
                                           formula2=str(config.LIMITE_VALOR_UNITARIO),
                                           error='Informe um valor igual ou maior que zero.'),
        'custo_unitario': DataValidation(type='decimal', operator='between', formula1='0',
                                         formula2=str(config.LIMITE_VALOR_UNITARIO),
                                         error='Informe um valor igual ou maior que zero.'),
    }
    for indice, (chave, titulo, obrigatoria, largura, formato, ajuda) in enumerate(COLUNAS, 1):
        celula = aba.cell(1, indice, titulo + (' *' if obrigatoria else ''))
        celula.font = Font(bold=True, color='FFFFFF' if obrigatoria else _COR_TITULO)
        celula.fill = PatternFill('solid', fgColor=_COR_OBRIGATORIA if obrigatoria else _COR_OPCIONAL)
        celula.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        celula.border = borda
        dimensao = aba.column_dimensions[celula.column_letter]
        dimensao.width, dimensao.number_format = largura, formato
        regra = regras.get(chave) or DataValidation(type='textLength', operator='lessThanOrEqual', formula1='500',
                                                    error='Use no máximo 500 caracteres.')
        regra.allow_blank = True
        regra.showErrorMessage = regra.showInputMessage = True
        regra.errorTitle, regra.promptTitle, regra.prompt = 'Valor não permitido', titulo, ajuda
        regra.add(f'{celula.column_letter}2:{celula.column_letter}{ultima}')
        aba.add_data_validation(regra)
    aba.row_dimensions[1].height = 36
    aba.freeze_panes = 'A2'
    aba.sheet_properties.tabColor = _COR_OBRIGATORIA


def _preencher_instrucoes(aba):
    aba.sheet_properties.tabColor = _COR_OPCIONAL
    aba.column_dimensions['A'].width, aba.column_dimensions['B'].width, aba.column_dimensions['C'].width = 28, 14, 90
    aba['A1'] = 'Como preencher a planilha de produtos'
    aba['A1'].font = Font(bold=True, size=16, color=_COR_TITULO)
    passos = (
        '1. Preencha a aba Produtos: uma linha por produto, a partir da linha 2. Não altere a linha de títulos.',
        '2. Colunas com * são obrigatórias. Marca e Categoria são escolhidas na lista suspensa da célula.',
        '3. Salve no formato Excel (.xlsx) e importe em Configurações → Gestão de dados.',
        '4. Linhas com erro são ignoradas e listadas no relatório ao final; as demais são importadas.',
    )
    for linha, texto in enumerate(passos, 3):
        aba.cell(linha, 1, texto)
    inicio = len(passos) + 4
    for coluna, texto in enumerate(('Coluna', 'Obrigatória', 'Como preencher'), 1):
        celula = aba.cell(inicio, coluna, texto)
        celula.font, celula.fill = Font(bold=True, color='FFFFFF'), PatternFill('solid', fgColor=_COR_OBRIGATORIA)
    for linha, (_, titulo, obrigatoria, _, _, ajuda) in enumerate(COLUNAS, inicio + 1):
        aba.cell(linha, 1, titulo).font = Font(bold=True)
        aba.cell(linha, 2, 'Sim' if obrigatoria else 'Não')
        aba.cell(linha, 3, ajuda).alignment = Alignment(wrap_text=True, vertical='top')
    exemplo = inicio + len(COLUNAS) + 2
    aba.cell(exemplo, 1, 'Exemplo de linha preenchida').font = Font(bold=True)
    valores = ('7891234567895', 'Perfume Floral 100 ml', config.MARCAS[0], config.CATEGORIAS[0], 12, 129.9, 64.5)
    for coluna, (valor, (_, titulo, *_)) in enumerate(zip(valores, COLUNAS), 1):
        aba.cell(exemplo + 1, coluna, titulo).font = Font(italic=True)
        aba.cell(exemplo + 2, coluna, valor)


def ler(conteudo):
    origem = _linhas_xlsx(conteudo) if conteudo[:4] == b'PK\x03\x04' else _linhas_csv(conteudo)
    with closing(origem):
        _, cabecalho = next(origem, (0, []))
        if [normalizar_texto(v).rstrip(' *') for v in cabecalho] not in _CABECALHOS_ACEITOS:
            raise ValueError('Colunas incompatíveis. Baixe o modelo novamente e mantenha a linha de títulos: '
                             + '; '.join(TITULOS))
        linhas = []
        for numero, valores in origem:
            if not any(str(v).strip() for v in valores):
                continue
            linhas.append((numero, valores))
            if len(linhas) > LIMITE_LINHAS:
                raise ValueError('Importe no máximo 100.000 linhas por arquivo.')
    if not linhas:
        raise ValueError('A planilha contém apenas os títulos ou linhas vazias.')
    return linhas


def _linhas_csv(conteudo):
    try:
        texto = conteudo.decode('utf-8-sig')
    except UnicodeError:
        raise ValueError('Salve a planilha como Excel (.xlsx) ou CSV UTF-8.') from None
    if '\0' in texto:
        raise ValueError('O arquivo não é uma planilha Excel nem um CSV de texto válido.')
    primeira = texto.splitlines()[0] if texto else ''
    leitor = csv.reader(io.StringIO(texto, newline=''), delimiter=';' if ';' in primeira else ',', strict=True)
    try:
        for valores in leitor:
            yield leitor.line_num, valores
    except csv.Error:
        raise ValueError('CSV malformado. Confira as aspas e salve novamente como CSV UTF-8.') from None


def _linhas_xlsx(conteudo):
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
            if sum(item.file_size for item in pacote.infolist()) > LIMITE_DESCOMPACTADO:
                raise ValueError('A planilha descompactada excede 256 MB. Divida-a em arquivos menores.')
        livro = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except ValueError:
        raise
    except Exception:   # arquivo do usuário: qualquer falha de parsing é recusa de formato
        raise ValueError('Não foi possível abrir a planilha Excel. Salve-a novamente no formato .xlsx.') from None
    try:
        aba = livro[ABA_PRODUTOS] if ABA_PRODUTOS in livro.sheetnames else livro.worksheets[0]
        aba.reset_dimensions()   # a dimensão gravada no arquivo pode estar errada e truncar colunas
        for numero, linha in enumerate(aba.iter_rows(values_only=True), 1):
            valores = [_valor_celula(v) for v in linha]
            while len(valores) > len(COLUNAS) and valores[-1] == '':
                valores.pop()   # o Excel estende linhas com células vazias formatadas
            if numero == 1:
                valores = [v for v in valores if v != '']
            yield numero, valores + [''] * (len(COLUNAS) - len(valores))
    except ValueError:
        raise
    except Exception:
        raise ValueError('Não foi possível ler a planilha Excel. Salve-a novamente no formato .xlsx.') from None
    finally:
        livro.close()


def _valor_celula(valor):
    if valor is None:
        return ''
    if isinstance(valor, str):
        return valor.strip()
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return valor   # números seguem nativos: "12.345" em texto seria lido como milhar
    return str(valor)


def validar(valores):
    if len(valores) != len(CABECALHOS):
        raise ValueError('Quantidade de colunas diferente do modelo.')
    codigo, nome, marca, categoria, quantidade, preco, custo = [
        v.strip() if isinstance(v, str) else v for v in valores]
    codigo = validar_gtin(codigo)
    nome = str(nome)
    if not nome or len(nome) > 500:
        raise ValueError('Informe um nome com 1 a 500 caracteres.')
    # Grava sempre a grafia do cadastro; a planilha pode variar caixa e acentos.
    marca, categoria = MARCAS.get(normalizar_texto(marca)), CATEGORIAS.get(normalizar_texto(categoria))
    if marca is None or categoria is None:
        raise ValueError('Marca ou categoria não cadastrada no sistema.')
    try:
        quantidade = converter_para_int(quantidade) if quantidade != '' else 0   # "1.000" vale 1000
        if quantidade < 0:
            raise ValueError
    except ValueError:
        raise ValueError('Quantidade: use um inteiro não negativo, como 12 ou 1.000.') from None
    # Vazio vira None: produto novo começa em 0 no cadastro; existente mantém o valor atual.
    preco = _validar_valor_monetario(preco, 'Preço de venda') if preco != '' else None
    custo = _validar_valor_monetario(custo, 'Custo unitário') if custo != '' else None
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
                    observacao = f'Importação de planilha · lote {lote} · linha {numero}'
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
                                 'FISICO', 'IMPORTACAO_PLANILHA', lote, log_id)
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
