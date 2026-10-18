"""
Busca, histórico e exportação (View_Relatorios).

  * busca inteligente de produtos ("refil lily" encontra "Refil Hidratante Lily");
  * histórico em duas abas: Movimentações (Logs_Movimentacao: entradas, saídas
    e ajustes de estoque; cancelados aparecem esmaecidos) e Alterações
    (Logs_Alteracao: edições de cadastro antes → depois, exclusões e códigos);
    selecionar um produto filtra as duas abas;
  * exportação de cópia protegida do banco.
"""
from __future__ import annotations

import os
import sys
from typing import Callable

import customtkinter as ctk

from utils.texto import formatar_data_hora, formatar_moeda
from views.componentes import (
    COR_TEXTO_SUAVE, confirmar, criar_tabela, erro, limpar_tabela, paleta_atual,
)

COLUNAS_PRODUTOS = [
    ("id", "ID", 50, "center", False),
    ("nome", "Produto", 260, "w", True),
    ("marca", "Marca", 140, "w", False),
    ("categoria", "Categoria", 120, "w", False),
    ("estoque", "Estoque", 80, "e", False),
    ("custo", "Custo médio", 110, "e", False),
    ("preco", "Preço base", 110, "e", False),
    ("codigos", "Códigos de barras", 220, "w", True),
]
COLUNAS_LOGS = [
    ("id", "#", 50, "center", False),
    ("data", "Data/Hora", 125, "w", False),
    ("tipo", "Tipo", 75, "center", False),
    ("produto", "Produto", 240, "w", True),
    ("marca", "Marca", 120, "w", False),
    ("quantidade", "Qtd", 60, "e", False),
    ("custo", "Custo no momento", 150, "e", False),
    ("antes", "Estoque antes", 125, "e", False),
    ("depois", "Estoque depois", 130, "e", False),
    ("situacao", "Situação", 90, "center", False),
    ("observacao", "Observação", 180, "w", True),
    ("origem", "Origem", 110, "w", False),
    ("referencia", "Referência", 120, "w", False),
]
COLUNAS_ALTERACOES = [
    ("id", "#", 50, "center", False),
    ("data", "Data/Hora", 125, "w", False),
    ("acao", "Ação", 80, "center", False),
    ("produto_id", "ID", 55, "center", False),
    ("produto", "Produto", 230, "w", True),
    ("campo", "Campo", 120, "w", False),
    ("descricao", "Detalhe (antes → depois)", 420, "w", True),
]
ABA_MOVIMENTACOES = "Movimentações de estoque"
ABA_ALTERACOES = "Alterações de cadastro"
ATRASO_BUSCA_MS = 250
TAMANHO_PAGINA = 200


class HistoricoPaginado:
    """Tabela do histórico (id decrescente) com "Carregar mais" por cursor."""

    def __init__(self, master, colunas, descricao: str,
                 consultar: Callable[[int | None], list[dict]],
                 linha: Callable[[dict], tuple[tuple, tuple]]):
        self.consultar, self.linha = consultar, linha
        self._ultimo_id = None
        master.grid_columnconfigure(0, weight=1)
        master.grid_rowconfigure(0, weight=1)
        quadro, self.tabela = criar_tabela(master, colunas, altura=12, rolagem_horizontal=True)
        quadro.grid(row=0, column=0, sticky="nsew")
        rodape = ctk.CTkFrame(master, fg_color="transparent")
        rodape.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ctk.CTkLabel(rodape, text=descricao, anchor="w", text_color=COR_TEXTO_SUAVE).pack(side="left")
        self.botao_mais = ctk.CTkButton(rodape, text="Carregar mais", width=120, height=30,
                                        command=lambda: self.carregar(mais=True))
        self.botao_mais.pack(side="right")

    def carregar(self, mais=False) -> None:
        registros = self.consultar(self._ultimo_id if mais else None)
        if not mais:
            limpar_tabela(self.tabela)
        self._ultimo_id = registros[-1]["id"] if registros else None
        self.botao_mais.configure(state="normal" if len(registros) == TAMANHO_PAGINA else "disabled")
        for registro in registros:
            valores, etiquetas = self.linha(registro)
            self.tabela.insert("", "end", tags=etiquetas, values=valores)


class ViewRelatorios(ctk.CTkFrame):
    def __init__(self, master, janela):
        super().__init__(master, fg_color="transparent")
        self.janela = janela
        self.controlador = janela.controlador_estoque
        self.relatorios = janela.controlador_relatorios
        self._busca_agendada = None
        self.produto_filtro: int | None = None
        self._construir()

    # ------------------------------------------------------------------ #
    def _construir(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=2)
        self.grid_rowconfigure(4, weight=3)

        cabecalho = ctk.CTkFrame(self, fg_color="transparent")
        cabecalho.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(cabecalho, text="Relatórios", font=ctk.CTkFont(size=24, weight="bold")
                     ).pack(side="left")
        ctk.CTkButton(cabecalho, text="Exportar cópia protegida (estoque + logs)", width=230, height=36,
                      command=self._exportar).pack(side="right")

        # Busca
        linha_busca = ctk.CTkFrame(self, fg_color="transparent")
        linha_busca.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self.var_busca = ctk.StringVar()
        self.var_busca.trace_add("write", self._agendar_busca)
        self.entrada_busca = ctk.CTkEntry(linha_busca, textvariable=self.var_busca, height=40,
                                          font=ctk.CTkFont(size=15))
        self.entrada_busca.pack(side="left", fill="x", expand=True)
        self.rotulo_resultado = ctk.CTkLabel(linha_busca, text="", text_color=COR_TEXTO_SUAVE)
        self.rotulo_resultado.pack(side="left", padx=12)

        quadro_produtos, self.tabela_produtos = criar_tabela(self, COLUNAS_PRODUTOS, altura=7, rolagem_horizontal=True)
        quadro_produtos.grid(row=2, column=0, sticky="nsew")
        self.tabela_produtos.bind("<<TreeviewSelect>>", self._ao_selecionar_produto)

        # Histórico: movimentações de estoque e alterações de cadastro ficam separadas.
        linha_logs = ctk.CTkFrame(self, fg_color="transparent")
        linha_logs.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        ctk.CTkLabel(linha_logs, text="Histórico",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        self.rotulo_filtro = ctk.CTkLabel(linha_logs, text="", text_color=COR_TEXTO_SUAVE)
        self.rotulo_filtro.pack(side="left", padx=12)
        ctk.CTkButton(linha_logs, text="Mostrar todos", width=120, height=30,
                      fg_color="transparent", border_width=1, text_color=("gray10", "#DCE4EE"),
                      command=self._limpar_filtro).pack(side="right")

        abas = ctk.CTkTabview(self)
        abas.grid(row=4, column=0, sticky="nsew")
        self.movimentacoes = HistoricoPaginado(
            abas.add(ABA_MOVIMENTACOES), COLUNAS_LOGS,
            "Entradas, saídas e ajustes de estoque. Ajustes podem ser desfeitos na tela Operação.",
            lambda antes_id: self.controlador.listar_logs(limite=TAMANHO_PAGINA, produto_id=self.produto_filtro,
                                                          antes_id=antes_id),
            self._linha_movimentacao)
        self.alteracoes = HistoricoPaginado(
            abas.add(ABA_ALTERACOES), COLUNAS_ALTERACOES,
            "Edições de cadastro (antes → depois), exclusões e códigos de barras feitos no Admin.",
            lambda antes_id: self.controlador.listar_alteracoes(limite=TAMANHO_PAGINA,
                                                                produto_id=self.produto_filtro,
                                                                antes_id=antes_id),
            self._linha_alteracao)
        self.ao_mudar_tema()

    # ------------------------------------------------------------------ #
    # Protocolo da janela principal
    # ------------------------------------------------------------------ #
    def ao_mostrar(self, **_dados) -> None:
        self._buscar()
        self._carregar_historicos()
        self.entrada_busca.focus_set()

    def ao_mudar_tema(self) -> None:
        self.movimentacoes.tabela.tag_configure("cancelado", foreground=paleta_atual()["texto_suave"])

    # ------------------------------------------------------------------ #
    # Busca de produtos
    # ------------------------------------------------------------------ #
    def _agendar_busca(self, *_args) -> None:
        """Debounce: espera o usuário parar de digitar antes de consultar."""
        if self._busca_agendada is not None:
            self.after_cancel(self._busca_agendada)
        self._busca_agendada = self.after(ATRASO_BUSCA_MS, self._buscar)

    def _buscar(self) -> None:
        self._busca_agendada = None
        termo = self.var_busca.get()
        produtos = self.controlador.buscar_produtos(termo)
        limpar_tabela(self.tabela_produtos)
        for produto in produtos:
            self.tabela_produtos.insert("", "end", iid=str(produto.id), values=(
                produto.id, produto.nome, produto.marca, produto.categoria,
                produto.estoque_atual, formatar_moeda(produto.custo_medio),
                formatar_moeda(produto.preco_venda_base), ", ".join(produto.codigos),
            ))
        self.rotulo_resultado.configure(
            text=f"{len(produtos)} produto(s)" + (f" para \"{termo.strip()}\"" if termo.strip() else ""))

    def _ao_selecionar_produto(self, _evento=None) -> None:
        selecao = self.tabela_produtos.selection()
        if not selecao:
            return
        self.produto_filtro = int(selecao[0])
        nome = self.tabela_produtos.item(selecao[0], "values")[1]
        self.rotulo_filtro.configure(text=f"filtrando: {nome}")
        self._carregar_historicos()

    def _limpar_filtro(self) -> None:
        self.produto_filtro = None
        self.rotulo_filtro.configure(text="")
        self.tabela_produtos.selection_remove(self.tabela_produtos.selection())
        self._carregar_historicos()

    # ------------------------------------------------------------------ #
    # Histórico
    # ------------------------------------------------------------------ #
    def _carregar_historicos(self) -> None:
        self.movimentacoes.carregar()
        self.alteracoes.carregar()

    @staticmethod
    def _linha_movimentacao(log: dict) -> tuple[tuple, tuple]:
        return (
            log["id"], formatar_data_hora(log["data_hora"]), log["tipo"],
            log["produto_nome"], log["produto_marca"], log["quantidade"],
            formatar_moeda(log["custo_no_momento"]), log["estoque_anterior"],
            log["estoque_posterior"], "Cancelado" if log["cancelado"] else "Válido",
            log["observacao"] or "",
            {'FISICO':'Físico','SHOPEE':'Shopee','TIKTOK':'TikTok Shop'}.get(log.get('origem','FISICO'),'Físico'),
            ('•••'+str(log.get('referencia'))[-6:]) if log.get('referencia') else '',
        ), ("cancelado",) if log["cancelado"] else ()

    @staticmethod
    def _linha_alteracao(registro: dict) -> tuple[tuple, tuple]:
        return (
            registro["id"], formatar_data_hora(registro["data_hora"]), registro["acao"],
            registro["produto_id"], registro["produto_nome"], registro["campo"], registro["descricao"],
        ), ()

    # ------------------------------------------------------------------ #
    # Exportação
    # ------------------------------------------------------------------ #
    def _exportar(self) -> None:
        try:
            caminho = self.relatorios.exportar_protegido()
        except Exception as falha:
            from utils.erros import mensagem_falha
            erro("Exportação", mensagem_falha(falha))
            return
        abrir = confirmar("Cópia protegida criada",
                          f"Arquivo: {caminho.name}\n\nPasta: {caminho.parent}\n\n"
                          "Cópia criptografada (.gsbackup) com estoque e histórico. Ela abre com a "
                          "senha vigente na data em que foi criada.\n"
                          "Para recuperar, não substitua dados/estoque.db: restaure em uma pasta nova "
                          "seguindo \"Recuperação portátil\" no GUIA_MULTICANAL.md.\n\n"
                          "Deseja abrir a pasta?")
        if abrir and sys.platform.startswith("win"):
            os.startfile(caminho.parent)

    def destroy(self):
        if getattr(self, '_busca_agendada', None):
            self.after_cancel(self._busca_agendada)
            self._busca_agendada = None
        super().destroy()
