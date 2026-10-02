"""
Tela de cadastro de produtos (View_Cadastro).

Recursos:
  * comboboxes fixos de Marca e Categoria (listas em config.py);
  * gatilho inteligente: um ``trace`` no campo Nome sugere Categoria e Marca
    pelas palavras-chave (ex.: "shampoo" -> Cabelos, "hidratante" -> Corpo e Banho).
    A sugestão só é aplicada enquanto o usuário não escolheu manualmente;
  * seção para vincular um ou vários códigos de barras ao produto (1:N);
  * pode ser aberta já com um código pré-preenchido vindo da tela de operação.
"""
from __future__ import annotations

import sqlite3
from models.seguranca import ERROS_BANCO, ERROS_OPERACIONAIS, ErroSeguranca
from utils.erros import mensagem_falha

import customtkinter as ctk

import config
from controllers.controllers import ErroNegocio
from utils.texto import sugerir_categoria, sugerir_marca
from views.componentes import (
    COR_TEXTO_SUAVE, COR_TEXTO_SUCESSO, ListaCodigos, alertar, erro, informar,
)


class ViewCadastro(ctk.CTkFrame):
    def __init__(self, master, janela):
        super().__init__(master, fg_color="transparent")
        self.janela = janela
        self.controlador = janela.controlador_estoque
        self._marca_manual = False
        self._categoria_manual = False
        self._construir()

    # ------------------------------------------------------------------ #
    # Construção
    # ------------------------------------------------------------------ #
    def _construir(self) -> None:
        self.grid_columnconfigure(0, weight=3, uniform="col")
        self.grid_columnconfigure(1, weight=2, uniform="col")
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Cadastro de Produto", anchor="w",
                     font=ctk.CTkFont(size=24, weight="bold")
                     ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        # ---------------- Formulário (esquerda) ----------------
        formulario = ctk.CTkFrame(self, corner_radius=14)
        formulario.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        formulario.grid_columnconfigure(1, weight=1)

        self.var_nome = ctk.StringVar()
        self.var_nome.trace_add("write", self._ao_digitar_nome)
        self._rotulo(formulario, "Nome do produto *", 0)
        self.entrada_nome = ctk.CTkEntry(formulario, textvariable=self.var_nome, height=40,
                                         font=ctk.CTkFont(size=15))
        self.entrada_nome.grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=(16, 6))

        self._rotulo(formulario, "Marca *", 1)
        quadro_marca = ctk.CTkFrame(formulario, fg_color="transparent")
        quadro_marca.grid(row=1, column=1, sticky="ew", padx=(0, 16), pady=6)
        self.combo_marca = ctk.CTkComboBox(quadro_marca, values=config.MARCAS, state="readonly",
                                           width=260, height=38, command=self._ao_escolher_marca)
        self.combo_marca.set("")
        self.combo_marca.pack(side="left")
        self.dica_marca = ctk.CTkLabel(quadro_marca, text="", text_color=COR_TEXTO_SUCESSO)
        self.dica_marca.pack(side="left", padx=10)

        self._rotulo(formulario, "Categoria *", 2)
        quadro_categoria = ctk.CTkFrame(formulario, fg_color="transparent")
        quadro_categoria.grid(row=2, column=1, sticky="ew", padx=(0, 16), pady=6)
        self.combo_categoria = ctk.CTkComboBox(quadro_categoria, values=config.CATEGORIAS,
                                               state="readonly", width=260, height=38,
                                               command=self._ao_escolher_categoria)
        self.combo_categoria.set("")
        self.combo_categoria.pack(side="left")
        self.dica_categoria = ctk.CTkLabel(quadro_categoria, text="", text_color=COR_TEXTO_SUCESSO)
        self.dica_categoria.pack(side="left", padx=10)

        self._rotulo(formulario, "Preço de venda base (R$)", 3)
        self.entrada_preco = self._entrada_numerica(formulario, 3, "Opcional · ex.: 89,90")
        self._rotulo(formulario, "Custo inicial unitário (R$)", 4)
        self.entrada_custo = self._entrada_numerica(formulario, 4, "Opcional · ex.: 45,00")
        self._rotulo(formulario, "Quantidade inicial em estoque", 5)
        self.entrada_quantidade = self._entrada_numerica(formulario, 5, "0")

        ctk.CTkLabel(formulario, text="* obrigatório. Preços em branco ficam em R$ 0,00.\n"
                                     "A quantidade inicial gera uma Entrada no histórico.",
                     text_color=COR_TEXTO_SUAVE, anchor="w", justify="left", font=ctk.CTkFont(size=12)
                     ).grid(row=6, column=0, columnspan=2, sticky="w", padx=16, pady=(8, 0))

        botoes = ctk.CTkFrame(formulario, fg_color="transparent")
        botoes.grid(row=7, column=0, columnspan=2, sticky="ew", padx=16, pady=16)
        ctk.CTkButton(botoes, text="Salvar produto", height=44, width=200,
                      font=ctk.CTkFont(size=15, weight="bold"), command=self._salvar
                      ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(botoes, text="Limpar", height=44, width=120, fg_color="transparent",
                      border_width=1, text_color=("gray10", "#DCE4EE"), command=self._limpar
                      ).pack(side="left")

        # ---------------- Códigos de barras (direita) ----------------
        quadro_codigos = ctk.CTkFrame(self, corner_radius=14)
        quadro_codigos.grid(row=1, column=1, sticky="nsew")
        ctk.CTkLabel(quadro_codigos, text="Códigos de barras", anchor="w",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(fill="x", padx=16, pady=(16, 2))
        ctk.CTkLabel(quadro_codigos, anchor="w", justify="left", wraplength=360,
                     text_color=COR_TEXTO_SUAVE, font=ctk.CTkFont(size=12),
                     text="Escaneie ou digite cada código e pressione Enter. Vários códigos "
                          "(embalagens promocionais, kits) podem apontar para o mesmo estoque. "
                          "GTIN: 8, 12, 13 ou 14 dígitos, com verificador válido."
                     ).pack(fill="x", padx=16, pady=(0, 8))
        linha = ctk.CTkFrame(quadro_codigos, fg_color="transparent")
        linha.pack(fill="x", padx=16)
        self.entrada_codigo = ctk.CTkEntry(linha, height=40, font=ctk.CTkFont(size=15),
                                           placeholder_text="Código de barras (GTIN)")
        self.entrada_codigo.pack(side="left", fill="x", expand=True, padx=(0, 8))
        for tecla in ("<Return>", "<KP_Enter>"):
            self.entrada_codigo.bind(tecla, self._adicionar_codigo)
        ctk.CTkButton(linha, text="Adicionar", width=100, height=40,
                      command=self._adicionar_codigo).pack(side="left")
        self.lista_codigos = ListaCodigos(quadro_codigos, altura=220)
        self.lista_codigos.pack(fill="both", expand=True, padx=16, pady=16)

    @staticmethod
    def _rotulo(master, texto: str, linha: int) -> None:
        ctk.CTkLabel(master, text=texto, anchor="w").grid(
            row=linha, column=0, sticky="w", padx=16, pady=(16 if linha == 0 else 6, 6))

    @staticmethod
    def _entrada_numerica(master, linha: int, dica: str) -> ctk.CTkEntry:
        entrada = ctk.CTkEntry(master, width=200, height=38, placeholder_text=dica)
        entrada.grid(row=linha, column=1, sticky="w", padx=(0, 16), pady=6)
        return entrada

    # ------------------------------------------------------------------ #
    # Protocolo da janela principal
    # ------------------------------------------------------------------ #
    def ao_mostrar(self, codigo: str | None = None, **_dados) -> None:
        if codigo is not None:
            self.entrada_codigo.delete(0, "end")
            self.entrada_codigo.insert(0, codigo)
            if not self._adicionar_codigo():
                return
        self.entrada_nome.focus_set()

    # ------------------------------------------------------------------ #
    # Gatilho inteligente
    # ------------------------------------------------------------------ #
    def _ao_digitar_nome(self, *_args) -> None:
        nome = self.var_nome.get()
        if not self._categoria_manual:
            categoria = sugerir_categoria(nome)
            self.combo_categoria.set(categoria or "")
            self.dica_categoria.configure(text="✓ sugerida pelo nome" if categoria else "")
        if not self._marca_manual:
            marca = sugerir_marca(nome)
            self.combo_marca.set(marca or "")
            self.dica_marca.configure(text="✓ sugerida pelo nome" if marca else "")

    def _ao_escolher_marca(self, _valor: str) -> None:
        self._marca_manual = True
        self.dica_marca.configure(text="")

    def _ao_escolher_categoria(self, _valor: str) -> None:
        self._categoria_manual = True
        self.dica_categoria.configure(text="")

    # ------------------------------------------------------------------ #
    # Códigos
    # ------------------------------------------------------------------ #
    def _adicionar_codigo(self, _evento=None) -> bool:
        # CTkEntry é textual. Valida a entrada inteira, sem remover caracteres
        # internos ou truncar a leitura do scanner para fabricar um código válido.
        try:
            codigo = self.controlador.validar_codigo_barras(self.entrada_codigo.get())
        except (ErroNegocio, ErroSeguranca, *ERROS_BANCO, OSError) as falha:
            erro("Código de barras", mensagem_falha(falha))
            self.entrada_codigo.focus_set()
            return False
        existente = self.controlador.resolver_codigo_barras(codigo)
        if existente is not None:
            erro("Código já vinculado",
                 f"O código {codigo} já pertence ao produto '{existente.nome}' ({existente.marca}).")
            return False
        elif not self.lista_codigos.adicionar(codigo):
            alertar("Código repetido", f"O código {codigo} já está na lista.")
        self.entrada_codigo.delete(0, "end")
        self.entrada_codigo.focus_set()
        return True

    # ------------------------------------------------------------------ #
    # Salvar / limpar
    # ------------------------------------------------------------------ #
    def _salvar(self) -> None:
        # Não ignorar um GTIN digitado/colado sem clicar em Adicionar.
        if self.entrada_codigo.get() and not self._adicionar_codigo():
            return
        try:
            produto = self.controlador.cadastrar_produto(
                nome=self.var_nome.get(),
                marca=self.combo_marca.get(),
                categoria=self.combo_categoria.get(),
                preco_venda_base=self.entrada_preco.get(),
                custo_inicial=self.entrada_custo.get(),
                quantidade_inicial=self.entrada_quantidade.get() or "0",
                codigos=self.lista_codigos.obter(),
            )
        except (ErroNegocio, ErroSeguranca, *ERROS_BANCO, OSError) as falha:
            erro("Não foi possível salvar", mensagem_falha(falha))
            return
        codigos = ", ".join(produto.codigos) or "nenhum"
        informar("Produto cadastrado",
                 f"'{produto.nome}' cadastrado com ID {produto.id}.\n"
                 f"Estoque inicial: {produto.estoque_atual} un.\nCódigos vinculados: {codigos}")
        if self.winfo_exists():
            self._limpar()

    def _limpar(self) -> None:
        self._marca_manual = self._categoria_manual = False
        self.var_nome.set("")
        self.combo_marca.set("")
        self.combo_categoria.set("")
        self.dica_marca.configure(text="")
        self.dica_categoria.configure(text="")
        for entrada in (self.entrada_preco, self.entrada_custo, self.entrada_quantidade, self.entrada_codigo):
            entrada.delete(0, "end")
        self.lista_codigos.limpar()
        self.entrada_nome.focus_set()
