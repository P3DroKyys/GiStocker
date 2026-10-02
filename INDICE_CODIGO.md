# Índice do código próprio

Gerado por AST em 30/09/2026 após leitura integral. Complementa `CONTEXTO_CODIGO.md`.

Cobertura: 17 arquivos Python, 3164 linhas, 22 classes e 196 funções/métodos.

Cada seção registra todas as classes e funções/métodos declarados, inclusive funções locais. Linhas e hashes identificam a versão analisada. SHA-256 considera os bytes completos do arquivo.

## auditoria/verificar.py

203 linhas · SHA-256 `ec875005cdcd537dd79e92ca0f90ff7083c38acf5602fb594b588c857a394695`

Imports diretos:

```python
import ast
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import config
from controllers.controllers import ControladorEstoque, ControladorRelatorios, ErroNegocio
from models.models import BancoDados
from utils.texto import converter_para_float, converter_para_int, sugerir_categoria
```

| Linha | Declaração | Descrição no fonte |
|---|---|---|
| 23 | classe: `Auditoria` | — |
| 24 | função/método: `Auditoria.setUp(self)` | — |
| 30 | função/método: `Auditoria.produto(self, **kwargs)` | — |
| 38 | função/método: `Auditoria.test_sintaxe_fontes(self)` | — |
| 46 | função/método: `Auditoria.test_cadastro_multiplos_codigos(self)` | — |
| 53 | função/método: `Auditoria.test_codigo_duplicado_nao_cria_produto(self)` | — |
| 59 | função/método: `Auditoria.test_custo_medio_e_entrada_sem_custo(self)` | — |
| 65 | função/método: `Auditoria.test_saida_e_bloqueio_sem_estoque(self)` | — |
| 73 | função/método: `Auditoria.test_validacoes_comuns(self)` | — |
| 83 | função/método: `Auditoria.test_desfazer_entrada_saida_ajuste(self)` | — |
| 93 | função/método: `Auditoria.test_rollback_estoque_se_log_falhar(self)` | — |
| 101 | função/método: `Auditoria.test_busca_sem_acento_e_ordem(self)` | — |
| 106 | função/método: `Auditoria.test_vincular_desvincular(self)` | — |
| 113 | função/método: `Auditoria.test_kpis_rankings_cancelamento(self)` | — |
| 126 | função/método: `Auditoria.test_estoque_parado(self)` | — |
| 133 | função/método: `Auditoria.test_exportacao_vazia_e_preenchida(self)` | — |
| 146 | função/método: `Auditoria.test_defeito_infinito_deveria_ser_rejeitado(self)` | — |
| 151 | função/método: `Auditoria.test_defeito_nan_deveria_gerar_erro_negocio(self)` | — |
| 156 | função/método: `Auditoria.test_defeito_tonico_capilar(self)` | — |
| 160 | função/método: `Auditoria.test_defeito_exportacoes_no_mesmo_minuto(self)` | — |
| 170 | função/método: `Auditoria.test_defeito_admin_arredonda_custo_ao_ajustar_quantidade(self)` | — |
| 178 | função/método: `Auditoria.test_defeito_duas_instancias_perdem_movimentacao(self)` | — |
| 188 | função/método: `Auditoria.test_defeito_duas_instancias_perdem_movimentacao.intercalar()` | — |

## config.py

247 linhas · SHA-256 `71fae8649c8ca125c6935ed37fa7dc19e01c2ed1f3d10a888d374c0556cfc950`

Imports diretos:

```python
import sys
from pathlib import Path
```

Sem classes/funções: constantes de configuração ou documentação do pacote.

## controllers/__init__.py

1 linhas · SHA-256 `f8166641c652b86c951a0f74f1f766e4bfd978d769f2e39ecfee1bc7c4b03a0f`

Sem classes/funções: constantes de configuração ou documentação do pacote.

## controllers/controllers.py

440 linhas · SHA-256 `34fba1023fc399dde8939f25d1afa1a5dc1c06810e95df22e7b3e06fb5171287`

Imports diretos:

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import pandas as pd
import config
from models.models import BancoDados, LogMovimentacao, Produto, RepositorioCodigosBarras, RepositorioLogs, RepositorioProdutos, RepositorioRelatorios
from utils.texto import converter_para_float, converter_para_int
```

| Linha | Declaração | Descrição no fonte |
|---|---|---|
| 33 | classe: `ErroNegocio` | Erro de validação ou de regra de negócio. A mensagem é exibida ao usuário. |
| 37 | função/método: `agora_texto() -> str` | Timestamp local no formato gravado em Logs_Movimentacao.data_hora. |
| 46 | classe: `ResultadoMovimentacao` | — |
| 55 | função/método: `ResultadoMovimentacao.estoque_novo(self) -> int` | — |
| 59 | função/método: `ResultadoMovimentacao.custo_novo(self) -> float` | — |
| 64 | classe: `ResultadoDesfazer` | — |
| 72 | função/método: `_validar_quantidade_positiva(valor) -> int` | — |
| 82 | função/método: `_validar_inteiro_nao_negativo(valor, nome_campo: str) -> int` | — |
| 92 | função/método: `_validar_valor_monetario(valor, nome_campo: str) -> float` | — |
| 105 | classe: `ControladorEstoque` | — |
| 106 | função/método: `ControladorEstoque.__init__(self, bd: BancoDados) -> None` | — |
| 116 | função/método: `ControladorEstoque.calcular_custo_medio_ponderado(estoque_atual: int, custo_atual: float, quantidade_entrada: int, custo_entrada: float) -> float` | Custo médio ponderado (média móvel) após uma entrada. |
| 137 | função/método: `ControladorEstoque.resolver_codigo_barras(self, codigo: str) -> Produto \| None` | Resolução 1:N: qualquer código vinculado devolve o MESMO produto. |
| 147 | função/método: `ControladorEstoque.obter_produto(self, produto_id: int) -> Produto` | — |
| 153 | função/método: `ControladorEstoque.listar_produtos(self) -> list[Produto]` | — |
| 156 | função/método: `ControladorEstoque.buscar_produtos(self, termo: str) -> list[Produto]` | — |
| 159 | função/método: `ControladorEstoque.listar_codigos(self, produto_id: int) -> list[str]` | — |
| 162 | função/método: `ControladorEstoque.listar_logs(self, limite: int \| None=None, produto_id: int \| None=None) -> list[dict]` | — |
| 169 | função/método: `ControladorEstoque._limpar_codigos(codigos) -> list[str]` | Remove espaços, vazios e duplicados preservando a ordem. |
| 178 | função/método: `ControladorEstoque._garantir_codigo_livre(self, codigo: str) -> None` | — |
| 185 | função/método: `ControladorEstoque.cadastrar_produto(self, nome: str, marca: str, categoria: str, preco_venda_base, custo_inicial, quantidade_inicial=0, codigos=()) -> Produto` | Cria o produto, vincula os códigos e, se houver quantidade inicial, |
| 218 | função/método: `ControladorEstoque.vincular_codigo_barras(self, codigo: str, produto_id: int) -> None` | Adiciona mais um código ao produto (ex.: embalagem promocional). |
| 227 | função/método: `ControladorEstoque.desvincular_codigo_barras(self, codigo: str) -> None` | — |
| 235 | função/método: `ControladorEstoque.registrar_entrada(self, produto_id: int, quantidade, custo_unitario=None) -> ResultadoMovimentacao` | Entrada de mercadoria. Recalcula o custo médio ponderado. |
| 264 | função/método: `ControladorEstoque.registrar_saida(self, produto_id: int, quantidade) -> ResultadoMovimentacao` | Saída (venda/baixa). O custo médio não muda; o log guarda o custo do momento. |
| 286 | função/método: `ControladorEstoque.ajustar_produto(self, produto_id: int, novo_estoque=None, novo_custo=None, motivo: str='') -> ResultadoMovimentacao` | Sobrescrita manual (área Admin). Sempre gera um log do tipo "Ajuste" |
| 327 | função/método: `ControladorEstoque.obter_ultima_acao(self) -> ResultadoDesfazer \| None` | Mostra (sem desfazer) qual seria a ação revertida — usado na confirmação. |
| 335 | função/método: `ControladorEstoque.desfazer_ultima_acao(self) -> ResultadoDesfazer` | Reverte o último log válido e o marca como cancelado. |
| 362 | classe: `ControladorRelatorios` | — |
| 373 | função/método: `ControladorRelatorios.__init__(self, bd: BancoDados) -> None` | — |
| 379 | função/método: `ControladorRelatorios.obter_kpis(self) -> dict` | total_itens, valor_investido (estoque x custo médio), |
| 384 | função/método: `ControladorRelatorios.movimentacao_ultimos_dias(self, dias: int=config.DIAS_GRAFICO_MOVIMENTACAO)` | Séries diárias para o gráfico de barras: (datas, entradas, saidas). |
| 398 | função/método: `ControladorRelatorios._ranking_por_campo(self, campo: str, limite: int) -> list[tuple[str, int]]` | — |
| 406 | função/método: `ControladorRelatorios.ranking_marcas(self, limite: int=6) -> list[tuple[str, int]]` | — |
| 409 | função/método: `ControladorRelatorios.ranking_categorias(self, limite: int=5) -> list[tuple[str, int]]` | — |
| 412 | função/método: `ControladorRelatorios.curva_a(self, limite: int=config.TAMANHO_CURVA_A) -> list[dict]` | Top N produtos por unidades vendidas (soma das Saídas não canceladas). |
| 416 | função/método: `ControladorRelatorios.estoque_parado(self, dias: int=config.DIAS_ESTOQUE_PARADO_PADRAO) -> list[dict]` | Produtos com estoque e sem saída há ``dias`` dias. |
| 421 | função/método: `ControladorRelatorios.exportar_csv(self, pasta: str \| Path \| None=None) -> tuple[Path, Path]` | Exporta estoque e logs para CSV (padrão Excel PT-BR: ';' e vírgula decimal). |

## main.py

75 linhas · SHA-256 `cf77b669e7ef3a6a42b262d5822b76d6877215e525d8d7c7bbd2b55c411a8c7d`

Imports diretos:

```python
import os
import sys
import traceback
from datetime import datetime
import config
import customtkinter as ctk
from controllers.controllers import ControladorEstoque, ControladorRelatorios
from models.models import BancoDados
from views.main_view import JanelaPrincipal
```

| Linha | Declaração | Descrição no fonte |
|---|---|---|
| 39 | função/método: `main() -> None` | — |
| 51 | função/método: `_registrar_falha(erro: BaseException) -> None` | Grava o erro em erros.log ao lado do programa e avisa o usuário. |

## models/__init__.py

1 linhas · SHA-256 `dc06f855147fa4e8c06163c547da136b9cb0215673b6d34382f55583a143714e`

Sem classes/funções: constantes de configuração ou documentação do pacote.

## models/models.py

478 linhas · SHA-256 `708c1178904b91b420c1a19556b2244b51d150d9fb82a045235b0105731d5413`

Imports diretos:

```python
from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator
import config
from utils.texto import normalizar_texto
```

| Linha | Declaração | Descrição no fonte |
|---|---|---|
| 76 | classe: `Produto` | — |
| 88 | função/método: `Produto.valor_investido(self) -> float` | — |
| 92 | função/método: `Produto.receita_potencial(self) -> float` | — |
| 97 | classe: `CodigoBarras` | — |
| 103 | classe: `LogMovimentacao` | — |
| 116 | função/método: `LogMovimentacao.estoque_posterior(self) -> int` | Estoque resultante após esta movimentação. |
| 126 | classe: `BancoDados` | Gerencia a conexão SQLite, a criação do esquema e as transações. |
| 129 | função/método: `BancoDados.__init__(self, caminho: str \| Path=config.CAMINHO_BANCO) -> None` | — |
| 147 | função/método: `BancoDados.criar_tabelas(self) -> None` | — |
| 151 | função/método: `BancoDados.transacao(self) -> Iterator[sqlite3.Connection]` | Agrupa várias gravações em uma única transação atômica. |
| 177 | função/método: `BancoDados.executar(self, sql: str, parametros: tuple \| list=()) -> sqlite3.Cursor` | — |
| 180 | função/método: `BancoDados.buscar_um(self, sql: str, parametros: tuple \| list=()) -> sqlite3.Row \| None` | — |
| 183 | função/método: `BancoDados.buscar_todos(self, sql: str, parametros: tuple \| list=()) -> list[sqlite3.Row]` | — |
| 186 | função/método: `BancoDados.fechar(self) -> None` | — |
| 193 | função/método: `_para_produto(linha: sqlite3.Row) -> Produto` | — |
| 209 | função/método: `_para_log(linha: sqlite3.Row) -> LogMovimentacao` | — |
| 237 | classe: `RepositorioProdutos` | — |
| 238 | função/método: `RepositorioProdutos.__init__(self, bd: BancoDados) -> None` | — |
| 241 | função/método: `RepositorioProdutos.inserir(self, produto: Produto) -> int` | — |
| 251 | função/método: `RepositorioProdutos.buscar_por_id(self, produto_id: int) -> Produto \| None` | — |
| 255 | função/método: `RepositorioProdutos.atualizar_estoque_custo(self, produto_id: int, estoque_atual: int, custo_medio: float) -> None` | — |
| 261 | função/método: `RepositorioProdutos.atualizar_dados(self, produto: Produto) -> None` | Atualiza nome/marca/categoria/preço (extensão futura: tela de edição). |
| 268 | função/método: `RepositorioProdutos.listar_todos(self) -> list[Produto]` | — |
| 272 | função/método: `RepositorioProdutos.buscar(self, termo: str, limite: int=500) -> list[Produto]` | Busca inteligente por "split-string LIKE". |
| 298 | função/método: `RepositorioProdutos.listar_para_exportacao(self) -> list[dict]` | Linhas prontas para virar DataFrame (estoque atual + valores calculados). |
| 317 | classe: `RepositorioCodigosBarras` | — |
| 318 | função/método: `RepositorioCodigosBarras.__init__(self, bd: BancoDados) -> None` | — |
| 321 | função/método: `RepositorioCodigosBarras.vincular(self, codigo: str, produto_id: int) -> None` | — |
| 326 | função/método: `RepositorioCodigosBarras.desvincular(self, codigo: str) -> None` | — |
| 329 | função/método: `RepositorioCodigosBarras.buscar_produto_id(self, codigo: str) -> int \| None` | Resolve um código de barras para o id do produto (ou None). |
| 334 | função/método: `RepositorioCodigosBarras.listar_por_produto(self, produto_id: int) -> list[str]` | — |
| 344 | classe: `RepositorioLogs` | — |
| 345 | função/método: `RepositorioLogs.__init__(self, bd: BancoDados) -> None` | — |
| 348 | função/método: `RepositorioLogs.inserir(self, log: LogMovimentacao) -> int` | — |
| 359 | função/método: `RepositorioLogs.buscar_por_id(self, log_id: int) -> LogMovimentacao \| None` | — |
| 363 | função/método: `RepositorioLogs.ultimo_nao_cancelado(self) -> LogMovimentacao \| None` | Último registro ainda válido (é o alvo do botão "Desfazer"). |
| 370 | função/método: `RepositorioLogs.marcar_cancelado(self, log_id: int) -> None` | — |
| 373 | função/método: `RepositorioLogs.listar(self, limite: int \| None=None, produto_id: int \| None=None, incluir_cancelados: bool=True) -> list[dict]` | Histórico (mais recente primeiro) já com nome/marca/categoria do produto. |
| 409 | classe: `RepositorioRelatorios` | — |
| 412 | função/método: `RepositorioRelatorios.__init__(self, bd: BancoDados) -> None` | — |
| 415 | função/método: `RepositorioRelatorios.totais_estoque(self) -> dict` | — |
| 425 | função/método: `RepositorioRelatorios.volume_por_dia(self, data_inicial: str) -> list[sqlite3.Row]` | Soma de Entradas e Saídas por dia (Ajustes não entram). |
| 435 | função/método: `RepositorioRelatorios.saidas_por_campo(self, campo: str) -> list[sqlite3.Row]` | Total de unidades vendidas agrupadas por 'marca' ou 'categoria'. |
| 449 | função/método: `RepositorioRelatorios.ranking_saidas_por_produto(self, limite: int) -> list[sqlite3.Row]` | — |
| 462 | função/método: `RepositorioRelatorios.produtos_sem_saida_desde(self, data_limite: str) -> list[sqlite3.Row]` | Produtos com estoque cuja última saída (ou, se nunca vendeu, a primeira |

## utils/__init__.py

1 linhas · SHA-256 `2e7ceff15a8006c2da4517b328e2ce7f16588365cb447a4458bc08a331e62de9`

Sem classes/funções: constantes de configuração ou documentação do pacote.

## utils/texto.py

126 linhas · SHA-256 `db28afcb96c9a0bfd56789952faffb506a3a6401a13b13bbd6729ac8a4315b58`

Imports diretos:

```python
from __future__ import annotations
import re
import unicodedata
from datetime import datetime
import config
```

| Linha | Declaração | Descrição no fonte |
|---|---|---|
| 19 | função/método: `normalizar_texto(texto) -> str` | Converte para minúsculas, remove acentos e espaços repetidos. |
| 32 | função/método: `_contem_termo(texto_normalizado: str, termo: str) -> bool` | Verifica se o termo aparece como palavra inteira dentro do texto. |
| 42 | função/método: `sugerir_categoria(nome: str) -> str \| None` | Retorna a categoria sugerida a partir das palavras-chave do nome. |
| 53 | função/método: `sugerir_marca(nome: str) -> str \| None` | Retorna a marca sugerida a partir das linhas de produto conhecidas. |
| 67 | função/método: `formatar_moeda(valor: float \| None) -> str` | 0 -> 'R$ 0,00'; 1234.5 -> 'R$ 1.234,50'. |
| 75 | função/método: `formatar_inteiro(valor: int \| float \| None) -> str` | 1234 -> '1.234'. |
| 80 | função/método: `formatar_data_hora(valor, com_hora: bool=True) -> str` | Converte um timestamp ISO ('2026-09-18 14:33:21') para 'dd/mm/aaaa HH:MM'. |
| 97 | função/método: `converter_para_float(texto) -> float` | Aceita '12,50', 'R$ 1.234,56' ou '1234.56'. Lança ValueError em PT-BR. |
| 114 | função/método: `converter_para_int(texto) -> int` | Aceita '300' ou '1.000'. Lança ValueError em PT-BR. |

## views/__init__.py

1 linhas · SHA-256 `1c63b61e15f576fb8d577a8b8bf7ffd753170383a626e17e3e91f1e8ed9c7138`

Sem classes/funções: constantes de configuração ou documentação do pacote.

## views/componentes.py

248 linhas · SHA-256 `ea8ac26e5a6aedc1b7ad8968ebd5a4d58729bd0132fa630b3ece44deeb71bcd5`

Imports diretos:

```python
from __future__ import annotations
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable
import customtkinter as ctk
```

| Linha | Declaração | Descrição no fonte |
|---|---|---|
| 59 | função/método: `modo_atual() -> str` | 'light' ou 'dark' conforme o modo de aparência ativo. |
| 64 | função/método: `paleta_atual() -> dict` | — |
| 68 | função/método: `cor_para_hex(widget: tk.Misc, cor: str) -> str` | Converte nomes de cor do Tk (ex.: 'gray90') para '#rrggbb' (matplotlib exige hex). |
| 76 | função/método: `_resolver_cor_modo(cor) -> str` | — |
| 82 | função/método: `cor_fundo_efetiva(widget: tk.Misc) -> str` | Cor de fundo real de um widget customtkinter (sobe a hierarquia se for |
| 101 | função/método: `aplicar_estilo_treeview() -> None` | Configura o estilo global das Treeviews para o modo claro/escuro ativo. |
| 124 | função/método: `criar_tabela(master, colunas: list[tuple], altura: int=12) -> tuple[ctk.CTkFrame, ttk.Treeview]` | Cria uma Treeview com barra de rolagem. |
| 146 | função/método: `limpar_tabela(tabela: ttk.Treeview) -> None` | — |
| 153 | classe: `CartaoKPI` | — |
| 154 | função/método: `CartaoKPI.__init__(self, master, titulo: str, **kwargs)` | — |
| 162 | função/método: `CartaoKPI.definir(self, valor: str) -> None` | — |
| 169 | classe: `ListaCodigos` | Mostra códigos vinculados como linhas com botão ✕. |
| 176 | função/método: `ListaCodigos.__init__(self, master, ao_remover: Callable[[str], bool] \| None=None, altura: int=150, **kwargs)` | — |
| 186 | função/método: `ListaCodigos.obter(self) -> list[str]` | — |
| 189 | função/método: `ListaCodigos.adicionar(self, codigo: str) -> bool` | — |
| 197 | função/método: `ListaCodigos.remover(self, codigo: str) -> None` | — |
| 202 | função/método: `ListaCodigos.definir(self, codigos: list[str]) -> None` | — |
| 206 | função/método: `ListaCodigos.limpar(self) -> None` | — |
| 210 | função/método: `ListaCodigos._tentar_remover(self, codigo: str) -> None` | — |
| 215 | função/método: `ListaCodigos._redesenhar(self) -> None` | — |
| 235 | função/método: `informar(titulo: str, mensagem: str) -> None` | — |
| 239 | função/método: `alertar(titulo: str, mensagem: str) -> None` | — |
| 243 | função/método: `erro(titulo: str, mensagem: str) -> None` | — |
| 247 | função/método: `confirmar(titulo: str, mensagem: str) -> bool` | — |

## views/main_view.py

143 linhas · SHA-256 `5fce7202dd53712c66485e3a278985e13002da12d790ddb94418e14e5b2c6984`

Imports diretos:

```python
from __future__ import annotations
from typing import Callable
import customtkinter as ctk
import config
from views.componentes import COR_TEXTO_SUAVE, aplicar_estilo_treeview
from views.view_admin import ViewAdmin
from views.view_cadastro import ViewCadastro
from views.view_dashboard import ViewDashboard
from views.view_operacao import ViewOperacao
from views.view_relatorios import ViewRelatorios
```

| Linha | Declaração | Descrição no fonte |
|---|---|---|
| 36 | classe: `JanelaPrincipal` | — |
| 37 | função/método: `JanelaPrincipal.__init__(self, controlador_estoque, controlador_relatorios, ao_fechar: Callable[[], None] \| None=None)` | — |
| 71 | função/método: `JanelaPrincipal._construir_barra_lateral(self) -> None` | — |
| 102 | função/método: `JanelaPrincipal._destacar_botao(self, chave_ativa: str) -> None` | — |
| 111 | função/método: `JanelaPrincipal.mostrar_view(self, chave: str, **dados) -> None` | Exibe a tela ``chave``; ``dados`` são repassados a ``ao_mostrar``. |
| 128 | função/método: `JanelaPrincipal.alternar_tema(self) -> None` | — |
| 134 | função/método: `JanelaPrincipal._notificar_mudanca_tema(self) -> None` | — |
| 140 | função/método: `JanelaPrincipal._fechar(self) -> None` | — |

## views/view_admin.py

267 linhas · SHA-256 `14ef4e8e5d9c563827fdd2a4ffb95e9ff7345b4f24f4d247d7d89aeeee4a6618`

Imports diretos:

```python
from __future__ import annotations
import customtkinter as ctk
import config
from controllers.controllers import ErroNegocio
from utils.texto import formatar_moeda
from views.componentes import COR_PERIGO, COR_TEXTO_ERRO, COR_TEXTO_SUAVE, ListaCodigos, confirmar, criar_tabela, erro, informar, limpar_tabela
```

| Linha | Declaração | Descrição no fonte |
|---|---|---|
| 29 | classe: `ViewAdmin` | — |
| 30 | função/método: `ViewAdmin.__init__(self, master, janela)` | — |
| 42 | função/método: `ViewAdmin._construir_bloqueio(self) -> None` | — |
| 60 | função/método: `ViewAdmin._desbloquear(self, _evento=None) -> None` | — |
| 70 | função/método: `ViewAdmin._bloquear(self) -> None` | — |
| 75 | função/método: `ViewAdmin._mostrar_quadro_correto(self) -> None` | — |
| 88 | função/método: `ViewAdmin._construir_admin(self) -> None` | — |
| 168 | função/método: `ViewAdmin.ao_mostrar(self, **_dados) -> None` | — |
| 174 | função/método: `ViewAdmin._buscar(self, _evento=None) -> None` | — |
| 185 | função/método: `ViewAdmin._ao_selecionar(self, _evento=None) -> None` | — |
| 190 | função/método: `ViewAdmin._carregar_produto(self, produto_id: int) -> None` | — |
| 208 | função/método: `ViewAdmin._limpar_produto(self) -> None` | — |
| 220 | função/método: `ViewAdmin._aplicar_ajuste(self) -> None` | — |
| 244 | função/método: `ViewAdmin._vincular_codigo(self, _evento=None) -> None` | — |
| 258 | função/método: `ViewAdmin._desvincular_codigo(self, codigo: str) -> bool` | Callback da ListaCodigos: remove do banco antes de tirar da lista. |

## views/view_cadastro.py

212 linhas · SHA-256 `48cdd86ab5e56fd2344ac0ad5abc379b07160b372473bba8c0c3bec91a745276`

Imports diretos:

```python
from __future__ import annotations
import customtkinter as ctk
import config
from controllers.controllers import ErroNegocio
from utils.texto import sugerir_categoria, sugerir_marca
from views.componentes import COR_TEXTO_SUAVE, COR_TEXTO_SUCESSO, ListaCodigos, alertar, erro, informar
```

| Linha | Declaração | Descrição no fonte |
|---|---|---|
| 24 | classe: `ViewCadastro` | — |
| 25 | função/método: `ViewCadastro.__init__(self, master, janela)` | — |
| 36 | função/método: `ViewCadastro._construir(self) -> None` | — |
| 121 | função/método: `ViewCadastro._rotulo(master, texto: str, linha: int) -> None` | — |
| 126 | função/método: `ViewCadastro._entrada_numerica(master, linha: int, dica: str) -> ctk.CTkEntry` | — |
| 134 | função/método: `ViewCadastro.ao_mostrar(self, codigo: str \| None=None, **_dados) -> None` | — |
| 142 | função/método: `ViewCadastro._ao_digitar_nome(self, *_args) -> None` | — |
| 155 | função/método: `ViewCadastro._ao_escolher_marca(self, _valor: str) -> None` | — |
| 159 | função/método: `ViewCadastro._ao_escolher_categoria(self, _valor: str) -> None` | — |
| 166 | função/método: `ViewCadastro._adicionar_codigo(self, _evento=None) -> None` | — |
| 182 | função/método: `ViewCadastro._salvar(self) -> None` | — |
| 202 | função/método: `ViewCadastro._limpar(self) -> None` | — |

## views/view_dashboard.py

218 linhas · SHA-256 `0fff9ed26435a6d168a671316665128df3db9352a4a339b34f4efa8aa9df5b4e`

Imports diretos:

```python
from __future__ import annotations
import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
import config
from utils.texto import converter_para_int, formatar_data_hora, formatar_inteiro, formatar_moeda
from views.componentes import COR_TEXTO_SUAVE, CartaoKPI, cor_fundo_efetiva, erro, paleta_atual
```

| Linha | Declaração | Descrição no fonte |
|---|---|---|
| 25 | classe: `ViewDashboard` | — |
| 26 | função/método: `ViewDashboard.__init__(self, master, janela)` | — |
| 36 | função/método: `ViewDashboard._construir(self) -> None` | — |
| 73 | função/método: `ViewDashboard._criar_grafico(self, nome: str, linha: int, coluna: int, altura: int, colspan: int=1) -> None` | — |
| 82 | função/método: `ViewDashboard._criar_caixa_texto(self, titulo: str, linha: int, coluna: int) -> ctk.CTkTextbox` | — |
| 95 | função/método: `ViewDashboard.ao_mostrar(self, **_dados) -> None` | — |
| 98 | função/método: `ViewDashboard.ao_mudar_tema(self) -> None` | — |
| 104 | função/método: `ViewDashboard.atualizar(self) -> None` | — |
| 129 | função/método: `ViewDashboard._preparar_eixo(self, nome: str, titulo: str)` | Limpa a figura, aplica o fundo do tema e devolve (eixo, paleta, canvas). |
| 141 | função/método: `ViewDashboard._desenhar_barras(self) -> None` | — |
| 168 | função/método: `ViewDashboard._desenhar_rosquinha(self, nome: str, titulo: str, dados: list[tuple[str, int]]) -> None` | — |
| 195 | função/método: `ViewDashboard._preencher_caixa(caixa: ctk.CTkTextbox, linhas: list[str], vazio: str) -> None` | — |
| 201 | função/método: `ViewDashboard._preencher_curva_a(self) -> None` | — |
| 209 | função/método: `ViewDashboard._preencher_estoque_parado(self, dias: int) -> None` | — |

## views/view_operacao.py

325 linhas · SHA-256 `ea2a1d796a0ef501f3804d285f3fb1121a129eec3e43a5a5bd6cc1bc58e5b2b9`

Imports diretos:

```python
from __future__ import annotations
import tkinter as tk
import customtkinter as ctk
import config
from controllers.controllers import ErroNegocio
from utils.texto import formatar_data_hora, formatar_inteiro, formatar_moeda
from views.componentes import COR_PERIGO, COR_TEXTO_ERRO, COR_TEXTO_INFO, COR_TEXTO_SUAVE, COR_TEXTO_SUCESSO, alertar, confirmar, erro
```

| Linha | Declaração | Descrição no fonte |
|---|---|---|
| 31 | função/método: `descrever_log(log, nome_produto: str) -> str` | Texto curto de um log para confirmações e mensagens. |
| 40 | classe: `ViewOperacao` | — |
| 41 | função/método: `ViewOperacao.__init__(self, master, janela)` | — |
| 53 | função/método: `ViewOperacao._construir(self) -> None` | — |
| 161 | função/método: `ViewOperacao.ao_mostrar(self, **_dados) -> None` | — |
| 168 | função/método: `ViewOperacao._foco_em_campo_da_tela(self, widget) -> bool` | — |
| 173 | função/método: `ViewOperacao._verificar_autofoco(self) -> None` | A cada 400 ms devolve o foco ao campo de código, exceto quando o |
| 186 | função/método: `ViewOperacao._focar_codigo(self, limpar: bool=True) -> None` | — |
| 194 | função/método: `ViewOperacao._ao_mudar_tipo(self, valor: str) -> None` | — |
| 201 | função/método: `ViewOperacao._ao_ler_codigo(self, _evento=None) -> None` | — |
| 228 | função/método: `ViewOperacao._confirmar(self, _evento=None) -> None` | — |
| 258 | função/método: `ViewOperacao._desfazer(self) -> None` | — |
| 284 | função/método: `ViewOperacao._limpar(self, _evento=None) -> None` | — |
| 292 | função/método: `ViewOperacao._exibir_produto(self, produto) -> None` | — |
| 299 | função/método: `ViewOperacao._limpar_produto(self) -> None` | — |
| 308 | função/método: `ViewOperacao._definir_status(self, texto: str, tipo: str='info') -> None` | — |
| 311 | função/método: `ViewOperacao._atualizar_recentes(self) -> None` | — |

## views/view_relatorios.py

178 linhas · SHA-256 `b53b35ea956888b67ddabadc32b12a08587bac4f0bed8d1942dee304716b14df`

Imports diretos:

```python
from __future__ import annotations
import os
import sys
import customtkinter as ctk
from utils.texto import formatar_data_hora, formatar_moeda
from views.componentes import COR_TEXTO_SUAVE, confirmar, criar_tabela, erro, limpar_tabela, paleta_atual
```

| Linha | Declaração | Descrição no fonte |
|---|---|---|
| 47 | classe: `ViewRelatorios` | — |
| 48 | função/método: `ViewRelatorios.__init__(self, master, janela)` | — |
| 58 | função/método: `ViewRelatorios._construir(self) -> None` | — |
| 103 | função/método: `ViewRelatorios.ao_mostrar(self, **_dados) -> None` | — |
| 108 | função/método: `ViewRelatorios.ao_mudar_tema(self) -> None` | — |
| 114 | função/método: `ViewRelatorios._agendar_busca(self, *_args) -> None` | Debounce: espera o usuário parar de digitar antes de consultar. |
| 120 | função/método: `ViewRelatorios._buscar(self) -> None` | — |
| 134 | função/método: `ViewRelatorios._ao_selecionar_produto(self, _evento=None) -> None` | — |
| 143 | função/método: `ViewRelatorios._limpar_filtro(self) -> None` | — |
| 152 | função/método: `ViewRelatorios._carregar_logs(self) -> None` | — |
| 168 | função/método: `ViewRelatorios._exportar(self) -> None` | — |

