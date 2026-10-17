"""
Camada de Controle (C do MVC): regras de negócio do estoque.

  * ControladorEstoque ..... resolução de código de barras (1:N), entradas,
                             saídas, custo médio ponderado, cadastro, ajustes
                             administrativos e o "desfazer última ação".
  * ControladorRelatorios .. KPIs, séries dos gráficos, rankings e exportação CSV.

As telas (views) só falam com estes controladores; nunca com o SQLite direto.
Toda violação de regra levanta ``ErroNegocio`` com mensagem pronta para exibir.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from functools import wraps
import sqlite3
from models.seguranca import ERROS_BANCO, ERROS_OPERACIONAIS, ErroSeguranca
import math
import os
import shutil
import tempfile

import pandas as pd

import config
from models.models import (
    BancoDados,
    LogMovimentacao,
    Produto,
    RepositorioCodigosBarras,
    RepositorioLogs,
    RepositorioProdutos,
    RepositorioRelatorios,
)
from utils.texto import converter_para_float, converter_para_int
from utils.gtin import validar_gtin


class ErroNegocio(Exception):
    """Erro de validação ou de regra de negócio. A mensagem é exibida ao usuário."""


def _operacao_atomica(metodo):
    """Bloqueia escrita antes de ler/validar saldo; confirma saldo e log juntos."""
    @wraps(metodo)
    def executar(self, *args, **kwargs):
        try:
            with self.bd.transacao():
                return metodo(self, *args, **kwargs)
        except ERROS_OPERACIONAIS as erro:
            codigo = getattr(erro, "sqlite_errorcode", 0) or 0
            if codigo & 0xFF in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise ErroNegocio("O banco está ocupado por outra operação. Aguarde e tente novamente.") from None
            raise
    return executar


def agora_texto() -> str:
    """Timestamp local no formato gravado em Logs_Movimentacao.data_hora."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------- #
# Objetos de resultado devolvidos às telas
# --------------------------------------------------------------------------- #
@dataclass
class ResultadoMovimentacao:
    log_id: int
    tipo: str
    produto: Produto            # estado do produto APÓS a operação
    quantidade: int
    estoque_anterior: int
    custo_anterior: float

    @property
    def estoque_novo(self) -> int:
        return self.produto.estoque_atual

    @property
    def custo_novo(self) -> float:
        return self.produto.custo_medio


@dataclass
class ResultadoDesfazer:
    log: LogMovimentacao        # log alvo (já marcado como cancelado, após desfazer)
    produto: Produto            # estado do produto após a restauração


# --------------------------------------------------------------------------- #
# Validações reutilizáveis
# --------------------------------------------------------------------------- #
def _validar_quantidade_positiva(valor) -> int:
    try:
        quantidade = converter_para_int(valor)
    except ValueError as erro:
        raise ErroNegocio(str(erro)) from None
    if quantidade <= 0:
        raise ErroNegocio("A quantidade deve ser maior que zero.")
    return quantidade


def _validar_inteiro_nao_negativo(valor, nome_campo: str) -> int:
    try:
        numero = converter_para_int(valor)
    except ValueError:
        raise ErroNegocio(f"{nome_campo}: informe um número inteiro.") from None
    if numero < 0:
        raise ErroNegocio(f"{nome_campo} não pode ser negativo.")
    return numero


def _validar_valor_monetario(valor, nome_campo: str) -> float:
    try:
        numero = converter_para_float(valor)
    except (ValueError, OverflowError):
        raise ErroNegocio(f"{nome_campo}: informe um valor numérico (ex.: 12,50).") from None
    if not math.isfinite(numero):
        raise ErroNegocio(f"{nome_campo}: informe um valor numérico finito.")
    if numero < 0:
        raise ErroNegocio(f"{nome_campo} não pode ser negativo.")
    if numero > config.LIMITE_VALOR_UNITARIO:
        raise ErroNegocio(f"{nome_campo}: valor acima do limite permitido de R$ {config.LIMITE_VALOR_UNITARIO:,}.")
    return numero


# --------------------------------------------------------------------------- #
# Controlador principal de estoque
# --------------------------------------------------------------------------- #
class ControladorEstoque:
    def __init__(self, bd: BancoDados) -> None:
        self.bd = bd
        self.produtos = RepositorioProdutos(bd)
        self.codigos = RepositorioCodigosBarras(bd)
        self.logs = RepositorioLogs(bd)

    # ---------------------------------------------------------------- #
    # Custo médio ponderado
    # ---------------------------------------------------------------- #
    @staticmethod
    def calcular_custo_medio_ponderado(estoque_atual: int, custo_atual: float,
                                       quantidade_entrada: int, custo_entrada: float) -> float:
        """Custo médio ponderado (média móvel) após uma entrada.

            novo_custo = (estoque_atual * custo_atual + qtd * custo_entrada)
                         -----------------------------------------------------
                                      estoque_atual + qtd

        Se não há estoque anterior (zero ou negativo), o custo passa a ser o da
        própria entrada — não faz sentido ponderar com um saldo inexistente.
        """
        if quantidade_entrada <= 0:
            raise ErroNegocio("A quantidade da entrada deve ser maior que zero.")
        if estoque_atual <= 0:
            return round(float(custo_entrada), config.CASAS_DECIMAIS_CUSTO)
        valor_total = estoque_atual * custo_atual + quantidade_entrada * custo_entrada
        if not math.isfinite(valor_total):
            raise ErroNegocio("O valor total da entrada excede o limite numérico permitido.")
        return round(valor_total / (estoque_atual + quantidade_entrada), config.CASAS_DECIMAIS_CUSTO)

    # ---------------------------------------------------------------- #
    # Consultas de produto
    # ---------------------------------------------------------------- #
    def resolver_codigo_barras(self, codigo: str) -> Produto | None:
        """Resolução 1:N: qualquer código vinculado devolve o MESMO produto."""
        codigo = (codigo or "").strip()
        if not codigo:
            return None
        produto_id = self.codigos.buscar_produto_id(codigo)
        if produto_id is None:
            return None
        return self.produtos.buscar_por_id(produto_id)

    def obter_produto(self, produto_id: int) -> Produto:
        produto = self.produtos.buscar_por_id(produto_id)
        if produto is None:
            raise ErroNegocio(f"Produto #{produto_id} não encontrado.")
        return produto

    @staticmethod
    def _validar_pagina(limite, offset=0):
        if (limite is not None and (type(limite) is not int or not 1 <= limite <= 1000)
                or type(offset) is not int or offset < 0):
            raise ValueError('Página inválida. Informe de 1 a 1000 registros e posição não negativa.')

    def listar_produtos(self, limite=None, offset=0) -> list[Produto]:
        self._validar_pagina(limite, offset)
        return self.produtos.listar_todos(limite, offset)

    def buscar_produtos(self, termo: str, limite=None, offset=0) -> list[Produto]:
        self._validar_pagina(limite, offset)
        return self.produtos.buscar(termo, limite, offset)

    def pesquisar_produtos(self, termo: str, limite=None, offset=0):
        """Pesquisa por relevância, com sugestões quando não há resultado direto."""
        self._validar_pagina(limite, offset)
        resultado = self.produtos.pesquisar(termo)
        resultado.produtos = resultado.produtos[offset:offset + limite if limite is not None else None]
        return resultado

    def listar_codigos(self, produto_id: int) -> list[str]:
        return self.codigos.listar_por_produto(produto_id)

    def listar_logs(self, limite: int = 200, produto_id: int | None = None, antes_id=None) -> list[dict]:
        self._validar_pagina(limite)
        if limite is None or antes_id is not None and (type(antes_id) is not int or antes_id < 1):
            raise ValueError('Informe um limite e um cursor válido para o histórico.')
        return self.logs.listar(limite=limite, produto_id=produto_id, antes_id=antes_id)

    # ---------------------------------------------------------------- #
    # Cadastro e códigos de barras
    # ---------------------------------------------------------------- #
    @staticmethod
    def validar_codigo_barras(codigo: str) -> str:
        """Validação compartilhada pela interface e pelas operações de gravação."""
        try:
            return validar_gtin(codigo)
        except ValueError as erro:
            raise ErroNegocio(str(erro)) from None

    @classmethod
    def _limpar_codigos(cls, codigos) -> list[str]:
        """Valida todos os GTINs e remove duplicados, preservando a ordem."""
        if codigos is None:
            return []
        if isinstance(codigos, (str, bytes)):
            raise ErroNegocio("Informe os códigos GTIN em uma lista de textos.")
        try:
            iterador = iter(codigos)
        except TypeError:
            raise ErroNegocio("Informe os códigos GTIN em uma lista de textos.") from None
        vistos: list[str] = []
        for codigo in iterador:
            codigo = cls.validar_codigo_barras(codigo)
            if codigo not in vistos:
                vistos.append(codigo)
        return vistos

    def _garantir_codigo_livre(self, codigo: str) -> None:
        produto_id = self.codigos.buscar_produto_id(codigo)
        if produto_id is not None:
            dono = self.produtos.buscar_por_id(produto_id)
            nome = dono.nome if dono else f"#{produto_id}"
            raise ErroNegocio(f"O código {codigo} já está vinculado ao produto '{nome}'.")

    @_operacao_atomica
    def cadastrar_produto(self, nome: str, marca: str, categoria: str, preco_venda_base=None,
                          custo_inicial=None, quantidade_inicial=0, codigos=()) -> Produto:
        """Cria o produto, vincula os códigos e, se houver quantidade inicial,
        registra a Entrada correspondente — tudo em uma única transação."""
        nome = (nome or "").strip()
        if not nome:
            raise ErroNegocio("Informe o nome do produto.")
        if marca not in config.MARCAS:
            raise ErroNegocio("Selecione uma marca válida.")
        if categoria not in config.CATEGORIAS:
            raise ErroNegocio("Selecione uma categoria válida.")
        # Somente no cadastro: valores não informados começam em zero.
        # Entradas e ajustes mantêm sua semântica de preservar custo ao deixar em branco.
        if preco_venda_base is None or (isinstance(preco_venda_base, str) and not preco_venda_base.strip()):
            preco_venda_base = 0
        if custo_inicial is None or (isinstance(custo_inicial, str) and not custo_inicial.strip()):
            custo_inicial = 0
        preco = _validar_valor_monetario(preco_venda_base, "Preço base")
        custo = round(_validar_valor_monetario(custo_inicial, "Custo inicial"), config.CASAS_DECIMAIS_CUSTO)
        quantidade = _validar_inteiro_nao_negativo(quantidade_inicial, "Quantidade inicial")
        codigos_limpos = self._limpar_codigos(codigos)
        for codigo in codigos_limpos:
            self._garantir_codigo_livre(codigo)

        produto = Produto(id=None, nome=nome, marca=marca, categoria=categoria,
                          estoque_atual=quantidade, preco_venda_base=preco, custo_medio=custo,
                          codigos=codigos_limpos)
        produto.id = self.produtos.inserir(produto)
        for codigo in codigos_limpos:
            self.codigos.vincular(codigo, produto.id)
        if quantidade > 0:
            self.logs.inserir(LogMovimentacao(
                id=None, produto_id=produto.id, tipo=config.TIPO_ENTRADA,
                quantidade=quantidade, custo_no_momento=custo, data_hora=agora_texto(),
                estoque_anterior=0, custo_anterior=0.0, observacao="Cadastro inicial",
            ))
        return produto

    @_operacao_atomica
    def vincular_codigo_barras(self, codigo: str, produto_id: int) -> None:
        """Adiciona mais um código ao produto (ex.: embalagem promocional)."""
        codigo = self.validar_codigo_barras(codigo)
        self.obter_produto(produto_id)
        self._garantir_codigo_livre(codigo)
        self.codigos.vincular(codigo, produto_id)

    @_operacao_atomica
    def desvincular_codigo_barras(self, codigo: str, produto_id_esperado: int | None = None) -> None:
        dono = self.codigos.buscar_produto_id(codigo)
        if dono is None:
            raise ErroNegocio(f"O código {codigo} não está vinculado a nenhum produto.")
        if produto_id_esperado is not None and dono != produto_id_esperado:
            raise ErroNegocio("O código foi vinculado a outro produto. Selecione novamente o produto antes de remover.")
        self.codigos.desvincular(codigo)

    # ---------------------------------------------------------------- #
    # Movimentações
    # ---------------------------------------------------------------- #
    @_operacao_atomica
    def registrar_entrada(self, produto_id: int, quantidade, custo_unitario=None) -> ResultadoMovimentacao:
        """Entrada de mercadoria. Recalcula o custo médio ponderado.

        ``custo_unitario`` vazio/None mantém o custo médio atual (a entrada é
        ponderada com o próprio custo, logo o custo não muda).
        """
        quantidade = _validar_quantidade_positiva(quantidade)
        produto = self.obter_produto(produto_id)
        manter_custo = custo_unitario is None or str(custo_unitario).strip() == ""
        if manter_custo:
            custo_unitario = produto.custo_medio
        else:
            custo_unitario = _validar_valor_monetario(custo_unitario, "Custo unitário")

        estoque_anterior, custo_anterior = produto.estoque_atual, produto.custo_medio
        novo_estoque = estoque_anterior + quantidade
        if abs(novo_estoque) > config.LIMITE_QUANTIDADE:
            raise ErroNegocio("O estoque resultante excede o limite permitido.")
        novo_custo = custo_anterior if manter_custo else self.calcular_custo_medio_ponderado(
            estoque_anterior, custo_anterior, quantidade, custo_unitario
        )
        self.produtos.atualizar_estoque_custo(produto.id, novo_estoque, novo_custo)
        log_id = self.logs.inserir(LogMovimentacao(
            id=None, produto_id=produto.id, tipo=config.TIPO_ENTRADA,
            quantidade=quantidade, custo_no_momento=custo_unitario, data_hora=agora_texto(),
            estoque_anterior=estoque_anterior, custo_anterior=custo_anterior,
        ))
        produto.estoque_atual, produto.custo_medio = novo_estoque, novo_custo
        return ResultadoMovimentacao(log_id, config.TIPO_ENTRADA, produto, quantidade,
                                     estoque_anterior, custo_anterior)

    @_operacao_atomica
    def registrar_saida(self, produto_id: int, quantidade) -> ResultadoMovimentacao:
        """Saída (venda/baixa). O custo médio não muda; o log guarda o custo do momento."""
        quantidade = _validar_quantidade_positiva(quantidade)
        produto = self.obter_produto(produto_id)
        estoque_anterior, custo_anterior = produto.estoque_atual, produto.custo_medio
        novo_estoque = estoque_anterior - quantidade
        if abs(novo_estoque) > config.LIMITE_QUANTIDADE:
            raise ErroNegocio("O estoque resultante excede o limite permitido.")
        if novo_estoque < 0 and not config.PERMITIR_ESTOQUE_NEGATIVO:
            raise ErroNegocio(
                f"Estoque insuficiente: '{produto.nome}' possui {estoque_anterior} un. "
                f"e a saída é de {quantidade}. Corrija o estoque na área Admin se necessário."
            )
        self.produtos.atualizar_estoque_custo(produto.id, novo_estoque, custo_anterior)
        log_id = self.logs.inserir(LogMovimentacao(
            id=None, produto_id=produto.id, tipo=config.TIPO_SAIDA,
            quantidade=quantidade, custo_no_momento=custo_anterior, data_hora=agora_texto(),
            estoque_anterior=estoque_anterior, custo_anterior=custo_anterior,
        ))
        produto.estoque_atual = novo_estoque
        return ResultadoMovimentacao(log_id, config.TIPO_SAIDA, produto, quantidade,
                                     estoque_anterior, custo_anterior)

    @_operacao_atomica
    def ajustar_produto(self, produto_id: int, novo_estoque=None, novo_custo=None,
                        motivo: str = "", *, estoque_esperado: int | None = None,
                        custo_esperado: float | None = None) -> ResultadoMovimentacao:
        """Sobrescrita manual (área Admin). Sempre gera um log do tipo "Ajuste"
        cujo ``quantidade`` é o delta de estoque e ``custo_no_momento`` o novo custo."""
        produto = self.obter_produto(produto_id)
        if ((estoque_esperado is not None and produto.estoque_atual != estoque_esperado)
                or (custo_esperado is not None and produto.custo_medio != custo_esperado)):
            raise ErroNegocio("O produto foi movimentado após a seleção. Selecione-o novamente antes de ajustar.")
        if novo_estoque in (None, "") and novo_custo in (None, ""):
            raise ErroNegocio("Informe ao menos um valor para ajustar.")

        estoque_final = produto.estoque_atual
        if novo_estoque not in (None, ""):
            try:
                estoque_final = converter_para_int(novo_estoque)
            except ValueError as erro:
                raise ErroNegocio(f"Novo estoque: {erro}") from None
            if estoque_final < 0 and not config.PERMITIR_ESTOQUE_NEGATIVO:
                raise ErroNegocio("O estoque não pode ficar negativo.")
        custo_final = produto.custo_medio
        if novo_custo not in (None, ""):
            custo_final = round(_validar_valor_monetario(novo_custo, "Novo custo médio"),
                                config.CASAS_DECIMAIS_CUSTO)

        if estoque_final == produto.estoque_atual and abs(custo_final - produto.custo_medio) < 1e-9:
            raise ErroNegocio("Nenhuma alteração detectada: os valores são iguais aos atuais.")

        estoque_anterior, custo_anterior = produto.estoque_atual, produto.custo_medio
        if abs(estoque_final - estoque_anterior) > config.LIMITE_QUANTIDADE:
            raise ErroNegocio("A diferença do ajuste excede o limite permitido.")
        self.produtos.atualizar_estoque_custo(produto.id, estoque_final, custo_final)
        log_id = self.logs.inserir(LogMovimentacao(
            id=None, produto_id=produto.id, tipo=config.TIPO_AJUSTE,
            quantidade=estoque_final - estoque_anterior, custo_no_momento=custo_final,
            data_hora=agora_texto(), estoque_anterior=estoque_anterior,
            custo_anterior=custo_anterior,
            observacao=(motivo or "").strip() or "Ajuste manual (Admin)",
        ))
        produto.estoque_atual, produto.custo_medio = estoque_final, custo_final
        return ResultadoMovimentacao(log_id, config.TIPO_AJUSTE, produto,
                                     estoque_final - estoque_anterior, estoque_anterior, custo_anterior)

    # ---------------------------------------------------------------- #
    # Desfazer
    # ---------------------------------------------------------------- #
    def obter_ultima_acao(self) -> ResultadoDesfazer | None:
        """Mostra (sem desfazer) qual seria a ação revertida — usado na confirmação."""
        log = self.logs.ultimo_nao_cancelado()
        if log is None:
            return None
        produto = self.obter_produto(log.produto_id)
        return ResultadoDesfazer(log=log, produto=produto)

    @_operacao_atomica
    def desfazer_ultima_acao(self, log_id_esperado: int | None = None) -> ResultadoDesfazer:
        """Reverte o último log válido e o marca como cancelado.

        Como cada log guarda o instantâneo (estoque_anterior, custo_anterior)
        do produto antes da operação, a reversão é exata para qualquer tipo:
          * Entrada: estoque -= quantidade e o custo médio volta ao valor anterior
            (equivale a desfazer a ponderação);
          * Saída:   estoque += quantidade;
          * Ajuste:  estoque e custo voltam ao que eram.
        Como sempre se desfaz o log MAIS RECENTE, nenhuma movimentação posterior
        do mesmo produto é perdida.
        """
        log = self.logs.ultimo_nao_cancelado()
        if log is None:
            raise ErroNegocio("Não há nenhuma ação para desfazer.")
        if log_id_esperado is not None and log.id != log_id_esperado:
            raise ErroNegocio("O histórico mudou enquanto você confirmava. Confira novamente a última ação.")
        produto = self.obter_produto(log.produto_id)
        self.produtos.atualizar_estoque_custo(produto.id, log.estoque_anterior, log.custo_anterior)
        self.logs.marcar_cancelado(log.id)
        log.cancelado = True
        produto.estoque_atual, produto.custo_medio = log.estoque_anterior, log.custo_anterior
        return ResultadoDesfazer(log=log, produto=produto)


# --------------------------------------------------------------------------- #
# Controlador de relatórios / dashboard / exportação
# --------------------------------------------------------------------------- #
class ControladorRelatorios:
    COLUNAS_LOGS = [
        "id", "data_hora", "tipo", "produto_id", "produto_nome", "produto_marca",
        "produto_categoria", "quantidade", "custo_no_momento", "estoque_anterior",
        "estoque_posterior", "custo_anterior", "cancelado", "observacao",
    ]
    COLUNAS_ESTOQUE = [
        "id", "nome", "marca", "categoria", "codigos_barras", "estoque_atual",
        "custo_medio", "preco_venda_base", "valor_investido", "receita_potencial", "data_cadastro",
    ]

    def __init__(self, bd: BancoDados) -> None:
        self.bd = bd
        self.produtos = RepositorioProdutos(bd)
        self.logs = RepositorioLogs(bd)
        self.relatorios = RepositorioRelatorios(bd)

    def obter_kpis(self) -> dict:
        """total_itens, valor_investido (estoque x custo médio),
        receita_potencial (estoque x preço base) e total_produtos."""
        return self.relatorios.totais_estoque()

    @staticmethod
    def _validar_dias(dias) -> None:
        if type(dias) is not int or not 1 <= dias <= config.MAXIMO_DIAS_RELATORIO:
            raise ErroNegocio(f"Informe um período de 1 a {config.MAXIMO_DIAS_RELATORIO} dias.")

    def movimentacao_ultimos_dias(self, dias: int = config.DIAS_GRAFICO_MOVIMENTACAO):
        """Séries diárias para o gráfico de barras: (datas, entradas, saidas)."""
        self._validar_dias(dias)
        hoje = date.today()
        inicio = hoje - timedelta(days=dias - 1)
        entradas: dict[str, int] = {}
        saidas: dict[str, int] = {}
        for linha in self.relatorios.volume_por_dia(inicio.isoformat()):
            destino = entradas if linha["tipo"] == config.TIPO_ENTRADA else saidas
            destino[linha["dia"]] = int(linha["total"])
        datas = [inicio + timedelta(days=i) for i in range(dias)]
        return (datas,
                [entradas.get(d.isoformat(), 0) for d in datas],
                [saidas.get(d.isoformat(), 0) for d in datas])

    def _ranking_por_campo(self, campo: str, limite: int) -> list[tuple[str, int]]:
        linhas = [(l["chave"], int(l["total"])) for l in self.relatorios.saidas_por_campo(campo)]
        if len(linhas) > limite:
            principais = linhas[:limite - 1]
            outras = sum(t for _, t in linhas[limite - 1:])
            linhas = principais + [("Outras", outras)]
        return linhas

    def ranking_marcas(self, limite: int = 6) -> list[tuple[str, int]]:
        return self._ranking_por_campo("marca", limite)

    def ranking_categorias(self, limite: int = 5) -> list[tuple[str, int]]:
        return self._ranking_por_campo("categoria", limite)

    def curva_a(self, limite: int = config.TAMANHO_CURVA_A) -> list[dict]:
        """Top N produtos por unidades vendidas (soma das Saídas não canceladas)."""
        return [dict(l, total_saidas=int(l['total_saidas']))
                for l in self.relatorios.ranking_saidas_por_produto(limite)]

    def estoque_parado(self, dias: int = config.DIAS_ESTOQUE_PARADO_PADRAO) -> list[dict]:
        """Produtos com estoque e sem saída há ``dias`` dias."""
        self._validar_dias(dias)
        limite =(datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")
        return [dict(l) for l in self.relatorios.produtos_sem_saida_desde(limite)]

    def exportar_protegido(self, pasta=None):
        if not self.bd.criptografado:
            raise ErroNegocio("Desbloqueie um banco protegido antes de exportar.")
        return self.bd.criar_backup(pasta or config.DIRETORIO_EXPORTACOES)

    def exportar_csv(self, pasta: str | Path | None = None) -> tuple[Path, Path]:
        """Publica um par consistente em pasta exclusiva, só após concluir ambos."""
        if self.bd.criptografado:
            raise ErroNegocio("Nesta versão protegida, use Exportar cópia protegida. CSV expõe os dados sem senha.")
        pasta = Path(pasta) if pasta else config.DIRETORIO_EXPORTACOES
        pasta.mkdir(parents=True, exist_ok=True)
        with self.bd.leitura_consistente():
            estoque = self.produtos.listar_para_exportacao()
            logs = self.logs.listar()
        # Neutraliza somente textos; números negativos continuam números.
        def proteger(valor):
            if isinstance(valor, str) and (valor.lstrip().startswith(('=', '+', '-', '@'))
                                          or valor.startswith(('\t', '\r', '\n'))):
                return "'" + valor
            return valor
        df_estoque = pd.DataFrame([{k: proteger(v) for k, v in l.items()} for l in estoque], columns=self.COLUNAS_ESTOQUE)
        df_logs = pd.DataFrame([{k: proteger(v) for k, v in l.items()} for l in logs], columns=self.COLUNAS_LOGS)
        if not df_logs.empty:
            df_logs["cancelado"] = df_logs["cancelado"].map({True: "Sim", False: "Não"})
        opcoes = dict(index=False, sep=";", decimal=",", encoding="utf-8-sig")
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        temporaria = Path(tempfile.mkdtemp(prefix=f'.exportacao_{carimbo}_', dir=pasta)).resolve()
        definitiva = temporaria.with_name(temporaria.name[1:])
        nome_estoque, nome_logs = f'backup_estoque_{carimbo}.csv', f'backup_logs_{carimbo}.csv'
        try:
            df_estoque.to_csv(temporaria / nome_estoque, **opcoes)
            df_logs.to_csv(temporaria / nome_logs, **opcoes)
            # A pasta só ganha o nome final quando o par completo existe.
            os.rename(temporaria, definitiva)
        except BaseException:
            if temporaria.is_relative_to(pasta.resolve()) and temporaria.exists():
                shutil.rmtree(temporaria)
            raise
        return definitiva / nome_estoque, definitiva / nome_logs
