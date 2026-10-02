"""
Configurações globais da aplicação de gestão de estoque.

Este módulo centraliza tudo o que pode precisar de ajuste sem mexer nas telas:
  * caminhos de arquivos (banco de dados, pasta de exportações);
  * parâmetros visuais (tema, tamanho da janela);
  * regras de negócio ajustáveis (estoque negativo, prazos);
  * listas fixas de marcas e categorias usadas nos comboboxes;
  * dicionários de palavras-chave do "gatilho inteligente" da tela de cadastro.
"""
import sys
import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Caminhos
# --------------------------------------------------------------------------- #
# Quando empacotado como .exe (PyInstaller), os dados ficam ao lado do executável;
# rodando pelo código-fonte, ficam na pasta do projeto.
if getattr(sys, "frozen", False):
    DIRETORIO_BASE = Path(sys.executable).resolve().parent
else:
    DIRETORIO_BASE = Path(__file__).resolve().parent
DIRETORIO_DADOS = DIRETORIO_BASE / "dados"
INSTALADO = getattr(sys, "frozen", False) and (DIRETORIO_BASE / "instalado.flag").is_file()
if INSTALADO:
    DIRETORIO_DADOS = Path(os.environ.get('PROGRAMDATA', r'C:\ProgramData')) / 'GiStocker'
DIRETORIO_EXPORTACOES = DIRETORIO_BASE / "exportacoes"
CAMINHO_BANCO = DIRETORIO_DADOS / "estoque.db"
CAMINHO_PREFERENCIAS = DIRETORIO_DADOS / "configuracoes.db"
# Recursos empacotados ficam em _internal; dados continuam junto do executável.
DIRETORIO_RECURSOS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets"
CAMINHO_LOGO = DIRETORIO_RECURSOS / "gistocker.png"
CAMINHO_ICONE = DIRETORIO_RECURSOS / "icone_gistocker.ico"

# --------------------------------------------------------------------------- #
# Aparência da janela
# --------------------------------------------------------------------------- #
NOME_APP = "GiStocker · Gestão de estoque"
VERSAO_APP = "2.0.0-preview.1"
MINIMO_CARACTERES_SENHA = 6
MINUTOS_BLOQUEIO_INATIVIDADE = 90
APARENCIA_PADRAO = "dark"        # "light", "dark" ou "system"
TEMA_COR = str(DIRETORIO_RECURSOS / "tema.json")
LARGURA_JANELA = 1280
ALTURA_JANELA = 800
LARGURA_MINIMA = 1024
ALTURA_MINIMA = 680

# --------------------------------------------------------------------------- #
# Regras de negócio
# --------------------------------------------------------------------------- #
PERMITIR_ESTOQUE_NEGATIVO = False      # False = bloqueia saídas maiores que o estoque
DIAS_ESTOQUE_PARADO_PADRAO = 30        # "Estoque Parado": sem saída há X dias
DIAS_GRAFICO_MOVIMENTACAO = 30         # janela do gráfico Entradas x Saídas
TAMANHO_CURVA_A = 5                    # quantidade de itens exibidos na Curva A
QTD_MOVIMENTACOES_RECENTES = 8         # lista lateral da tela de operação
CASAS_DECIMAIS_CUSTO = 4               # precisão interna do custo médio ponderado
LIMITE_QUANTIDADE = 2**63 - 1          # limite de INTEGER no SQLite
LIMITE_VALOR_UNITARIO = 1_000_000_000_000  # teto de segurança, em reais

# Tipos de movimentação gravados em Logs_Movimentacao.tipo
TIPO_ENTRADA = "Entrada"
TIPO_SAIDA = "Saída"
TIPO_AJUSTE = "Ajuste"
TIPOS_MOVIMENTACAO = (TIPO_ENTRADA, TIPO_SAIDA, TIPO_AJUSTE)

# --------------------------------------------------------------------------- #
# Listas fixas usadas nos comboboxes da tela de cadastro
# --------------------------------------------------------------------------- #
MARCAS = [
    "O Boticário",
    "Eudora",
    "Quem Disse Berenice",
    "OUi",
    "Au Migos",
    "Natura",
    "Avon",
    "Skelt",
    "Creamy",
    "Locitanne",
    "Pink Cheeks",
    "Ciclo",
    "Importados",
    "Boca Rosa",
    "Francine Ehkle",
    "By Pam",
    "Karen Bachini",
]

CATEGORIAS = [
    "Perfumaria",
    "Cabelos",
    "Skincare",
    "Corpo e Banho",
    "Maquiagem",
]

# --------------------------------------------------------------------------- #
# Gatilho inteligente: palavras-chave -> categoria
#
# A ORDEM IMPORTA: a primeira palavra encontrada no nome do produto vence.
# Por isso termos mais específicos (ex.: "máscara capilar", "hidratante facial")
# vêm antes dos genéricos ("máscara", "hidratante"). A comparação ignora
# acentos e maiúsculas e só casa palavras inteiras.
# --------------------------------------------------------------------------- #
PALAVRAS_CHAVE_CATEGORIA = [
    ("tônico capilar", "Cabelos"),
    # --- Skincare (específicos primeiro, pois "hidratante facial" é Skincare) ---
    ("protetor solar", "Skincare"),
    ("hidratante facial", "Skincare"),
    ("máscara facial", "Skincare"),
    ("esfoliante facial", "Skincare"),
    ("gel de limpeza", "Skincare"),
    ("água micelar", "Skincare"),
    ("ácido hialurônico", "Skincare"),
    ("vitamina c", "Skincare"),
    ("niacinamida", "Skincare"),
    ("sérum", "Skincare"),
    ("serum", "Skincare"),
    ("facial", "Skincare"),
    ("rosto", "Skincare"),
    ("anti-idade", "Skincare"),
    ("antiidade", "Skincare"),
    ("antissinais", "Skincare"),
    ("tônico", "Skincare"),
    ("demaquilante", "Skincare"),
    ("olheiras", "Skincare"),
    ("acne", "Skincare"),
    ("skincare", "Skincare"),
    # --- Perfumaria ---
    ("deo colônia", "Perfumaria"),
    ("deo parfum", "Perfumaria"),
    ("eau de parfum", "Perfumaria"),
    ("eau de toilette", "Perfumaria"),
    ("desodorante colônia", "Perfumaria"),
    ("body splash", "Perfumaria"),
    ("colônia", "Perfumaria"),
    ("perfume", "Perfumaria"),
    ("parfum", "Perfumaria"),
    ("fragrância", "Perfumaria"),
    ("edp", "Perfumaria"),
    ("edt", "Perfumaria"),
    # --- Cabelos ---
    ("máscara capilar", "Cabelos"),
    ("máscara de hidratação", "Cabelos"),
    ("creme para pentear", "Cabelos"),
    ("óleo capilar", "Cabelos"),
    ("shampoo", "Cabelos"),
    ("xampu", "Cabelos"),
    ("condicionador", "Cabelos"),
    ("leave-in", "Cabelos"),
    ("leave in", "Cabelos"),
    ("capilar", "Cabelos"),
    ("cabelo", "Cabelos"),
    ("cabelos", "Cabelos"),
    ("finalizador", "Cabelos"),
    ("modelador", "Cabelos"),
    ("reconstrução", "Cabelos"),
    ("antiqueda", "Cabelos"),
    # --- Maquiagem ---
    ("máscara para cílios", "Maquiagem"),
    ("máscara de cílios", "Maquiagem"),
    ("base líquida", "Maquiagem"),
    ("pó compacto", "Maquiagem"),
    ("pó solto", "Maquiagem"),
    ("fixador de maquiagem", "Maquiagem"),
    ("batom", "Maquiagem"),
    ("base", "Maquiagem"),
    ("corretivo", "Maquiagem"),
    ("rímel", "Maquiagem"),
    ("blush", "Maquiagem"),
    ("sombra", "Maquiagem"),
    ("delineador", "Maquiagem"),
    ("iluminador", "Maquiagem"),
    ("primer", "Maquiagem"),
    ("lápis", "Maquiagem"),
    ("gloss", "Maquiagem"),
    ("paleta", "Maquiagem"),
    ("bronzer", "Maquiagem"),
    ("contorno", "Maquiagem"),
    ("maquiagem", "Maquiagem"),
    # --- Corpo e Banho (genéricos por último) ---
    ("óleo corporal", "Corpo e Banho"),
    ("creme para mãos", "Corpo e Banho"),
    ("creme para pés", "Corpo e Banho"),
    ("esfoliante corporal", "Corpo e Banho"),
    ("hidratante", "Corpo e Banho"),
    ("loção", "Corpo e Banho"),
    ("sabonete", "Corpo e Banho"),
    ("body", "Corpo e Banho"),
    ("banho", "Corpo e Banho"),
    ("esfoliante", "Corpo e Banho"),
    ("desodorante", "Corpo e Banho"),
    ("corporal", "Corpo e Banho"),
    ("creme", "Corpo e Banho"),
]

# --------------------------------------------------------------------------- #
# Gatilho inteligente: palavras-chave -> marca (linhas de produto conhecidas)
# --------------------------------------------------------------------------- #
PALAVRAS_CHAVE_MARCA = [
    ("boticário", "O Boticário"),
    ("boticario", "O Boticário"),
    ("lily", "O Boticário"),
    ("malbec", "O Boticário"),
    ("egeo", "O Boticário"),
    ("floratta", "O Boticário"),
    ("cuide-se bem", "O Boticário"),
    ("nativa spa", "O Boticário"),
    ("botik", "O Boticário"),
    ("make b", "O Boticário"),
    ("arbo", "O Boticário"),
    ("zaad", "O Boticário"),
    ("glamour", "O Boticário"),
    ("quasar", "O Boticário"),
    ("portinari", "O Boticário"),
    ("uomini", "O Boticário"),
    ("elysée", "O Boticário"),
    ("coffee", "O Boticário"),
    ("eudora", "Eudora"),
    ("niina secrets", "Eudora"),
    ("siàge", "Eudora"),
    ("siage", "Eudora"),
    ("soul", "Eudora"),
    ("instance", "Eudora"),
    ("natura", "Natura"),
    ("ekos", "Natura"),
    ("tododia", "Natura"),
    ("kaiak", "Natura"),
    ("humor", "Natura"),
    ("luna", "Natura"),
    ("essencial", "Natura"),
    ("chronos", "Natura"),
    ("lumina", "Natura"),
    ("mamãe e bebê", "Natura"),
    ("avon", "Avon"),
    ("renew", "Avon"),
    ("far away", "Avon"),
    ("color trend", "Avon"),
    ("quem disse", "Quem Disse Berenice"),
    ("berenice", "Quem Disse Berenice"),
    ("qdb", "Quem Disse Berenice"),
    ("oui", "OUi"),
    ("au migos", "Au Migos"),
    ("aumigos", "Au Migos"),
    ("skelt", "Skelt"),
    ("creamy", "Creamy"),
    ("l'occitane", "Locitanne"),
    ("loccitane", "Locitanne"),
    ("locitanne", "Locitanne"),
    ("occitane", "Locitanne"),
    ("pink cheeks", "Pink Cheeks"),
    ("ciclo", "Ciclo"),
    ("boca rosa", "Boca Rosa"),
    ("francine", "Francine Ehkle"),
    ("by pam", "By Pam"),
    ("karen bachini", "Karen Bachini"),
]
