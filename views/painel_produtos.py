"""Consulta visual de todos os produtos, integrada à área administrativa."""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from utils.texto import formatar_data_hora, formatar_moeda, normalizar_texto
from views.componentes import COR_TEXTO_SUAVE, criar_tabela, limpar_tabela


COLUNAS = [
    ("id", "ID", 55, "center", False),
    ("nome", "Produto", 300, "w", False),
    ("marca", "Marca", 160, "w", False),
    ("categoria", "Categoria", 135, "w", False),
    ("estoque_atual", "Estoque (un.)", 105, "e", False),
    ("custo_medio", "Custo médio", 115, "e", False),
    ("preco_venda_base", "Preço base", 115, "e", False),
    ("codigos", "Códigos de barras", 240, "w", False),
    ("data_cadastro", "Cadastrado em", 145, "w", False),
]
TODAS_MARCAS = "Todas as marcas"
TODAS_CATEGORIAS = "Todas as categorias"


class PainelProdutos(ctk.CTkFrame):
    def __init__(self, master, controlador, ao_abrir: Callable[[int], None]):
        super().__init__(master, fg_color="transparent")
        self.controlador = controlador
        self.ao_abrir = ao_abrir
        self._produtos = []
        self._busca_agendada = None
        self._ordenacao = "nome"
        self._decrescente = False
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(self, text="Consulte os cadastros e abra um produto para ajustar estoque, custo ou códigos.",
                     anchor="w", text_color=COR_TEXTO_SUAVE
                     ).grid(row=0, column=0, sticky="ew", pady=(4, 10))

        busca = ctk.CTkFrame(self, fg_color="transparent")
        busca.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        busca.grid_columnconfigure(0, weight=1)
        self.var_busca = ctk.StringVar()
        self.entrada_busca = ctk.CTkEntry(
            busca, textvariable=self.var_busca, height=38,
            placeholder_text="Buscar por nome, marca, categoria, código ou ID")
        self.entrada_busca.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(busca, text="Atualizar", width=100, height=38, command=self.atualizar
                      ).grid(row=0, column=1)

        filtros = ctk.CTkFrame(self, fg_color="transparent")
        filtros.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.marca = ctk.CTkComboBox(filtros, values=[TODAS_MARCAS], state="readonly",
                                     width=210, command=lambda _: self._filtrar())
        self.marca.pack(side="left", padx=(0, 8))
        self.categoria = ctk.CTkComboBox(filtros, values=[TODAS_CATEGORIAS], state="readonly",
                                         width=195, command=lambda _: self._filtrar())
        self.categoria.pack(side="left", padx=(0, 8))
        ctk.CTkButton(filtros, text="Limpar filtros", width=110, command=self._limpar_filtros
                      ).pack(side="left")

        quadro, self.tabela = criar_tabela(self, COLUNAS, altura=15, rolagem_horizontal=True)
        quadro.grid(row=3, column=0, sticky="nsew")
        for campo, titulo, *_ in COLUNAS:
            self.tabela.heading(campo, text=titulo, command=lambda c=campo: self._ordenar(c))
        self.tabela.bind("<<TreeviewSelect>>", self._selecionar)
        self.tabela.bind("<Double-1>", self._duplo_clique)
        self.tabela.bind("<Return>", self._abrir)

        rodape = ctk.CTkFrame(self, fg_color="transparent")
        rodape.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self.contagem = ctk.CTkLabel(rodape, text="", anchor="w", text_color=COR_TEXTO_SUAVE)
        self.contagem.pack(side="left")
        self.botao_abrir = ctk.CTkButton(rodape, text="Abrir ajustes do produto", width=210,
                                         state="disabled", command=self._abrir)
        self.botao_abrir.pack(side="right")
        self.detalhes = ctk.CTkLabel(self, text="Selecione um produto. Clique nos títulos para ordenar.",
                                     anchor="w", justify="left", wraplength=720,
                                     text_color=COR_TEXTO_SUAVE)
        self.detalhes.grid(row=5, column=0, sticky="ew", pady=(6, 0))
        self.var_busca.trace_add("write", self._agendar_busca)

    def atualizar(self) -> None:
        # Listagem completa para os filtros locais do catálogo.
        self._produtos = self.controlador.listar_produtos()
        for combo, campo, todos in ((self.marca, "marca", TODAS_MARCAS),
                                     (self.categoria, "categoria", TODAS_CATEGORIAS)):
            atual = combo.get()
            valores = [todos] + sorted({getattr(p, campo) for p in self._produtos}, key=normalizar_texto)
            combo.configure(values=valores)
            combo.set(atual if atual in valores else todos)
        self._filtrar()

    def _agendar_busca(self, *_args) -> None:
        if self._busca_agendada is not None:
            self.after_cancel(self._busca_agendada)
        self._busca_agendada = self.after(250, self._filtrar)

    def _limpar_filtros(self) -> None:
        self.var_busca.set("")
        self.marca.set(TODAS_MARCAS)
        self.categoria.set(TODAS_CATEGORIAS)
        self._filtrar()

    def _ordenar(self, campo: str) -> None:
        self._decrescente = not self._decrescente if campo == self._ordenacao else False
        self._ordenacao = campo
        self._filtrar()

    def _filtrar(self) -> None:
        if self._busca_agendada is not None:
            self.after_cancel(self._busca_agendada)
            self._busca_agendada = None
        selecao = self.tabela.selection()
        palavras = normalizar_texto(self.var_busca.get()).split()
        produtos = []
        for produto in self._produtos:
            if self.marca.get() != TODAS_MARCAS and produto.marca != self.marca.get():
                continue
            if self.categoria.get() != TODAS_CATEGORIAS and produto.categoria != self.categoria.get():
                continue
            campos = [str(produto.id), produto.nome, produto.marca, produto.categoria, *produto.codigos]
            textos = [normalizar_texto(campo) for campo in campos]
            if all(any(palavra in texto for texto in textos) for palavra in palavras):
                produtos.append(produto)

        def chave(produto):
            valor = getattr(produto, self._ordenacao)
            if isinstance(valor, list):
                valor = " ".join(valor)
            return normalizar_texto(valor) if isinstance(valor, str) or valor is None else valor

        produtos.sort(key=chave, reverse=self._decrescente)
        limpar_tabela(self.tabela)
        for produto in produtos:
            self.tabela.insert("", "end", iid=str(produto.id), values=(
                produto.id, produto.nome, produto.marca, produto.categoria,
                produto.estoque_atual, formatar_moeda(produto.custo_medio),
                formatar_moeda(produto.preco_venda_base), ", ".join(produto.codigos) or "—",
                formatar_data_hora(produto.data_cadastro),
            ))
        for campo, titulo, *_ in COLUNAS:
            indicador = (" ▼" if self._decrescente else " ▲") if campo == self._ordenacao else ""
            self.tabela.heading(campo, text=titulo + indicador)
        if selecao and self.tabela.exists(selecao[0]):
            self.tabela.selection_set(selecao[0])
        quantidade = len(produtos)
        self.contagem.configure(text=f"{quantidade} de {len(self._produtos)} produtos cadastrados")
        self._selecionar()

    def _selecionar(self, _evento=None) -> None:
        selecao = self.tabela.selection()
        self.botao_abrir.configure(state="normal" if selecao else "disabled")
        produto = next((p for p in self._produtos if selecao and str(p.id) == selecao[0]), None)
        if produto:
            custo = f"{produto.custo_medio:.4f}".replace(".", ",")
            self.detalhes.configure(text=f"{produto.nome} • Custo médio: R$ {custo}\n"
                                        f"Códigos: {', '.join(produto.codigos) or 'nenhum vinculado'}")
        elif not self.tabela.get_children():
            self.detalhes.configure(text="Nenhum produto encontrado para os filtros informados."
                                    if self._produtos else "Ainda não há produtos cadastrados. Use a tela Cadastro para adicionar.")
        else:
            self.detalhes.configure(text="Selecione um produto. Clique nos títulos para ordenar.")

    def _duplo_clique(self, evento) -> None:
        item = self.tabela.identify_row(evento.y)
        if item and self.tabela.identify_region(evento.x, evento.y) == "cell":
            self.tabela.selection_set(item)
            self._abrir()

    def _abrir(self, _evento=None) -> None:
        selecao = self.tabela.selection()
        if selecao:
            self.ao_abrir(int(selecao[0]))

    def destroy(self):
        if getattr(self, '_busca_agendada', None):
            self.after_cancel(self._busca_agendada)
            self._busca_agendada = None
        super().destroy()
