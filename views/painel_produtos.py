"""Consulta visual de todos os produtos, integrada à área administrativa."""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from utils.texto import formatar_data_hora, formatar_moeda, normalizar_texto
from views.componentes import COR_PERIGO, COR_TEXTO_SUAVE, criar_tabela, informar, limpar_tabela
from views.confirmacao_senha import confirmar_com_senha


MARCADO, DESMARCADO = "☑", "☐"
# Caixa de seleção: não ordena; o título marca/desmarca as linhas visíveis.
COLUNA_MARCA = ("marcado", DESMARCADO, 44, "center", False)
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
        self._marcados: set[int] = set()
        self._ancora: str | None = None     # último item clicado na caixa (Shift+Click)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(self, text="Abra um produto para editar dados, estoque, custo ou códigos. Marque as caixas para excluir "
                          "(Shift+Clique marca o intervalo).",
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
        # Exibido só com produtos marcados (ver _atualizar_marcacao).
        self.botao_excluir = ctk.CTkButton(filtros, text="Deletar produtos selecionados", width=230,
                                           fg_color=COR_PERIGO[0], hover_color=COR_PERIGO[1],
                                           command=self._excluir_marcados)

        quadro, self.tabela = criar_tabela(self, [COLUNA_MARCA, *COLUNAS], altura=15, rolagem_horizontal=True)
        quadro.grid(row=3, column=0, sticky="nsew")
        self.tabela.heading(COLUNA_MARCA[0], command=self._marcar_todos)
        for campo, titulo, *_ in COLUNAS:
            self.tabela.heading(campo, text=titulo, command=lambda c=campo: self._ordenar(c))
        self.tabela.bind("<Button-1>", self._clicar)
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
        # Só linhas visíveis permanecem marcadas: nada oculto pelo filtro é excluído.
        self._marcados &= {produto.id for produto in produtos}
        limpar_tabela(self.tabela)
        for produto in produtos:
            self.tabela.insert("", "end", iid=str(produto.id), values=(
                MARCADO if produto.id in self._marcados else DESMARCADO, produto.id, produto.nome, produto.marca, produto.categoria,
                produto.estoque_atual, formatar_moeda(produto.custo_medio),
                formatar_moeda(produto.preco_venda_base), ", ".join(produto.codigos) or "—",
                formatar_data_hora(produto.data_cadastro),
            ))
        for campo, titulo, *_ in COLUNAS:
            indicador = (" ▼" if self._decrescente else " ▲") if campo == self._ordenacao else ""
            self.tabela.heading(campo, text=titulo + indicador)
        if selecao and self.tabela.exists(selecao[0]):
            self.tabela.selection_set(selecao[0])
        if self._ancora is not None and not self.tabela.exists(self._ancora):
            self._ancora = None
        quantidade = len(produtos)
        self.contagem.configure(text=f"{quantidade} de {len(self._produtos)} produtos cadastrados")
        self._atualizar_marcacao()
        self._selecionar()

    # ------------------------------------------------------------------ #
    # Caixas de seleção e exclusão em lote
    # ------------------------------------------------------------------ #
    def _clicar(self, evento):
        """Clique na caixa marca/desmarca; com Shift, aplica o mesmo estado ao intervalo."""
        if (self.tabela.identify_region(evento.x, evento.y) != "cell"
                or self.tabela.identify_column(evento.x) != "#1"):
            return None
        item = self.tabela.identify_row(evento.y)
        if not item:
            return None
        self._alternar(item, intervalo=bool(evento.state & 0x0001))
        return "break"   # a caixa não altera a linha selecionada para ajustes

    def _alternar(self, item: str, intervalo: bool = False) -> None:
        marcar = int(item) not in self._marcados
        itens = [item]
        if intervalo and self._ancora is not None:
            linhas = list(self.tabela.get_children())
            inicio, fim = sorted((linhas.index(self._ancora), linhas.index(item)))
            itens = linhas[inicio:fim + 1]
        self._definir_marcacao(itens, marcar)
        self._ancora = item

    def _marcar_todos(self) -> None:
        linhas = list(self.tabela.get_children())
        self._definir_marcacao(linhas, not all(int(i) in self._marcados for i in linhas))
        self._ancora = None

    def _definir_marcacao(self, itens, marcar: bool) -> None:
        for item in itens:
            (self._marcados.add if marcar else self._marcados.discard)(int(item))
            self.tabela.set(item, COLUNA_MARCA[0], MARCADO if marcar else DESMARCADO)
        self._atualizar_marcacao()

    def _atualizar_marcacao(self) -> None:
        linhas = self.tabela.get_children()
        todos = bool(linhas) and all(int(i) in self._marcados for i in linhas)
        self.tabela.heading(COLUNA_MARCA[0], text=MARCADO if todos else DESMARCADO)
        if self._marcados:
            self.botao_excluir.configure(text=f"Deletar produtos selecionados ({len(self._marcados)})")
            self.botao_excluir.pack(side="left", padx=(8, 0))
        else:
            self.botao_excluir.pack_forget()

    def _excluir_marcados(self) -> None:
        ids = sorted(self._marcados)
        if not ids:
            return
        nomes = [p.nome for p in self._produtos if p.id in self._marcados]
        lista = "\n".join(f"• {nome}" for nome in nomes[:5])
        if len(nomes) > 5:
            lista += f"\n… e mais {len(nomes) - 5}"
        resultado = confirmar_com_senha(
            self, "Excluir produtos selecionados",
            f"{len(ids)} produto(s) serão excluídos definitivamente, com os códigos de barras e "
            f"o histórico de movimentações:\n{lista}\n\nA exclusão não pode ser desfeita e fica "
            "registrada em Relatórios › Alterações.",
            lambda senha: self.controlador.excluir_produtos(ids, senha=senha), "Excluir")
        if resultado is None:
            return
        informar("Produtos excluídos", f"{resultado['excluidos']} produto(s) e "
                                       f"{resultado['movimentacoes']} movimentação(ões) removidos.")
        if self.winfo_exists():
            self._marcados.clear()
            self.atualizar()

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
        if (item and self.tabela.identify_region(evento.x, evento.y) == "cell"
                and self.tabela.identify_column(evento.x) != "#1"):
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
