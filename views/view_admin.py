"""
Área administrativa (View_Admin), disponível após o acesso ao software.

Permite:
  * consultar todos os produtos em uma tabela filtrável e excluir em lote
    os marcados (com senha);
  * editar nome, marca, categoria, preço, estoque e custo médio de um produto
    (com senha). Estoque/custo geram o log "Ajuste"; todo campo alterado fica
    em Logs_Alteracao com o valor antes → depois;
  * vincular/desvincular códigos de barras de um produto já cadastrado.
"""
from __future__ import annotations

from utils.erros import ERROS_EXIBIVEIS, mensagem_falha

import customtkinter as ctk

import config
from controllers.controllers import ErroNegocio
from utils.texto import formatar_moeda
from views.confirmacao_senha import confirmar_com_senha
from views.painel_produtos import PainelProdutos
from views.componentes import (
    COR_TEXTO_SUAVE, ListaCodigos, confirmar, criar_tabela, erro,
    informar, limpar_tabela,
)

COLUNAS_BUSCA = [
    ("id", "ID", 50, "center", False),
    ("nome", "Produto", 220, "w", True),
    ("marca", "Marca", 120, "w", False),
    ("estoque", "Estoque", 70, "e", False),
]


class ViewAdmin(ctk.CTkFrame):
    def __init__(self, master, janela):
        super().__init__(master, fg_color="transparent")
        self.janela = janela
        self.controlador = janela.controlador_estoque
        self.produto_atual = None
        self._busca_agendada = None
        self._resultados_busca = []
        self._busca_aproximada = False
        self._construir_admin()
        self._trace_busca = self.var_busca.trace_add('write', self._agendar_busca)

    # ------------------------------------------------------------------ #
    # Área administrativa
    # ------------------------------------------------------------------ #
    def _construir_admin(self) -> None:
        self.quadro_admin = ctk.CTkFrame(self, fg_color="transparent")
        self.quadro_admin.pack(fill="both", expand=True)
        self.quadro_admin.grid_columnconfigure(0, weight=1)
        self.quadro_admin.grid_rowconfigure(1, weight=1)

        cabecalho = ctk.CTkFrame(self.quadro_admin, fg_color="transparent")
        cabecalho.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(cabecalho, text="Administração", font=ctk.CTkFont(size=24, weight="bold")
                     ).pack(side="left")

        self.abas = ctk.CTkTabview(self.quadro_admin, command=self._ao_trocar_aba)
        self.abas.grid(row=1, column=0, sticky="nsew")
        catalogo = self.abas.add("Produtos cadastrados")
        ajustes = self.abas.add("Ajustes e códigos")
        self.painel_produtos = PainelProdutos(catalogo, self.controlador, self._abrir_produto_catalogo)
        self.painel_produtos.pack(fill="both", expand=True)
        ajustes.grid_columnconfigure(0, weight=2, uniform="col")
        ajustes.grid_columnconfigure(1, weight=3, uniform="col")
        ajustes.grid_rowconfigure(1, weight=1)

        # ---- Esquerda: localizar produto ----
        busca = ctk.CTkFrame(ajustes, corner_radius=14)
        busca.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        busca.grid_columnconfigure(0, weight=1)
        busca.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(busca, text="Localizar produto", anchor="w",
                     font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 4))
        linha = ctk.CTkFrame(busca, fg_color="transparent")
        linha.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        self.var_busca = ctk.StringVar()
        self.entrada_busca = ctk.CTkEntry(linha, height=38, textvariable=self.var_busca,
                                          placeholder_text="Nome, marca, categoria, código ou #ID")
        self.entrada_busca.pack(fill="x", expand=True)
        for tecla in ("<Return>", "<KP_Enter>"):
            self.entrada_busca.bind(tecla, self._buscar)
        quadro_tabela, self.tabela_busca = criar_tabela(busca, COLUNAS_BUSCA, altura=10)
        quadro_tabela.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self.tabela_busca.bind("<<TreeviewSelect>>", self._ao_selecionar)
        rodape = ctk.CTkFrame(busca, fg_color='transparent')
        rodape.grid(row=3, column=0, sticky='ew', padx=14, pady=(0, 12))
        rodape.grid_columnconfigure(0, weight=1)
        self.status_busca = ctk.CTkLabel(rodape, text='Digite para filtrar os produtos.',
                                        anchor='w', justify='left', wraplength=270,
                                        text_color=COR_TEXTO_SUAVE)
        self.status_busca.grid(row=0, column=0, sticky='ew')
        self.botao_mais = ctk.CTkButton(rodape, text='Mostrar mais', width=100,
                                       command=self._mostrar_mais)

        # ---- Direita: ajuste + códigos ----
        direita = ctk.CTkFrame(ajustes, fg_color="transparent")
        direita.grid(row=1, column=1, sticky="nsew")
        direita.grid_columnconfigure(0, weight=1)
        direita.grid_rowconfigure(1, weight=1)

        ajuste = ctk.CTkFrame(direita, corner_radius=14)
        ajuste.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ajuste.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(ajuste, text="Dados, estoque e custo do produto", anchor="w",
                     font=ctk.CTkFont(size=16, weight="bold")
                     ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(14, 2))
        self.rotulo_produto = ctk.CTkLabel(ajuste, text="Nenhum produto selecionado.", anchor="w",
                                           justify="left", wraplength=520, text_color=COR_TEXTO_SUAVE)
        self.rotulo_produto.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 8))

        ctk.CTkLabel(ajuste, text="Nome", anchor="w").grid(row=2, column=0, sticky="w", padx=14, pady=4)
        self.entrada_nome = ctk.CTkEntry(ajuste, height=36)
        self.entrada_nome.grid(row=2, column=1, sticky="ew", padx=(0, 14), pady=4)
        ctk.CTkLabel(ajuste, text="Marca", anchor="w").grid(row=3, column=0, sticky="w", padx=14, pady=4)
        self.combo_marca = ctk.CTkComboBox(ajuste, values=config.MARCAS, state="readonly", width=260, height=36)
        self.combo_marca.grid(row=3, column=1, sticky="w", pady=4)
        ctk.CTkLabel(ajuste, text="Categoria", anchor="w").grid(row=4, column=0, sticky="w", padx=14, pady=4)
        self.combo_categoria = ctk.CTkComboBox(ajuste, values=config.CATEGORIAS, state="readonly", width=260, height=36)
        self.combo_categoria.grid(row=4, column=1, sticky="w", pady=4)
        ctk.CTkLabel(ajuste, text="Preço base (R$)", anchor="w").grid(row=5, column=0, sticky="w", padx=14, pady=4)
        self.entrada_preco = ctk.CTkEntry(ajuste, width=160, height=36)
        self.entrada_preco.grid(row=5, column=1, sticky="w", pady=4)
        ctk.CTkLabel(ajuste, text="Novo estoque atual", anchor="w").grid(row=6, column=0, sticky="w", padx=14, pady=4)
        self.entrada_estoque = ctk.CTkEntry(ajuste, width=160, height=36)
        self.entrada_estoque.grid(row=6, column=1, sticky="w", pady=4)
        ctk.CTkLabel(ajuste, text="Novo custo médio (R$)", anchor="w").grid(row=7, column=0, sticky="w", padx=14, pady=4)
        self.entrada_custo = ctk.CTkEntry(ajuste, width=160, height=36)
        self.entrada_custo.grid(row=7, column=1, sticky="w", pady=4)
        self.botao_ajuste = ctk.CTkButton(ajuste, text="Aplicar ajuste (gera log 'Ajuste')", height=40,
                                        command=self._aplicar_ajuste, state='disabled')
        self.botao_ajuste.grid(row=8, column=0, columnspan=2, sticky="ew", padx=14, pady=(10, 4))
        ctk.CTkLabel(ajuste, text="Exige a senha atual. Estoque e custo geram o log 'Ajuste' (desfazível); "
                                  "todo campo alterado fica em Relatórios › Alterações.",
                     anchor="w", justify="left", wraplength=520, text_color=COR_TEXTO_SUAVE
                     ).grid(row=9, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 12))

        codigos = ctk.CTkFrame(direita, corner_radius=14)
        codigos.grid(row=1, column=0, sticky="nsew")
        ctk.CTkLabel(codigos, text="Códigos de barras do produto", anchor="w",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(fill="x", padx=14, pady=(14, 6))
        linha_codigo = ctk.CTkFrame(codigos, fg_color="transparent")
        linha_codigo.pack(fill="x", padx=14)
        self.entrada_codigo = ctk.CTkEntry(linha_codigo, height=36,
                                           placeholder_text="Novo código de barras + Enter")
        self.entrada_codigo.pack(side="left", fill="x", expand=True, padx=(0, 8))
        for tecla in ("<Return>", "<KP_Enter>"):
            self.entrada_codigo.bind(tecla, self._vincular_codigo)
        self.botao_vincular = ctk.CTkButton(linha_codigo, text="Vincular", width=90, height=36,
                                           command=self._vincular_codigo, state='disabled')
        self.botao_vincular.pack(side="left")
        self.lista_codigos = ListaCodigos(codigos, ao_remover=self._desvincular_codigo, altura=120)
        self.lista_codigos.pack(fill="both", expand=True, padx=14, pady=(8, 14))

    # ------------------------------------------------------------------ #
    # Protocolo da janela principal
    # ------------------------------------------------------------------ #
    def ao_mostrar(self, **_dados) -> None:
        self._ao_trocar_aba()

    def _ao_trocar_aba(self) -> None:
        if self.abas.get() == "Produtos cadastrados":
            self._cancelar_busca()
            self.painel_produtos.atualizar()
            self.painel_produtos.entrada_busca.focus_set()
        else:
            self._buscar()
            self.entrada_busca.focus_set()

    def _abrir_produto_catalogo(self, produto_id: int) -> None:
        self.abas.set("Ajustes e códigos")
        self.var_busca.set(f'#{produto_id}')
        self._buscar()
        self.entrada_estoque.focus_set()

    # ------------------------------------------------------------------ #
    # Localizar / selecionar produto
    # ------------------------------------------------------------------ #
    def _cancelar_busca(self):
        if self._busca_agendada is not None:
            self.after_cancel(self._busca_agendada)
            self._busca_agendada = None

    def _agendar_busca(self, *_args):
        self._cancelar_busca()
        # A consulta mudou: nenhum ajuste deve continuar apontando para o item
        # anterior durante o intervalo de digitação ou após zero resultados.
        self._limpar_selecao()
        limpar_tabela(self.tabela_busca)
        self._resultados_busca = []
        self.botao_mais.grid_remove()
        self.status_busca.configure(text='Filtrando…')
        self._busca_agendada = self.after(220, self._buscar)

    def _buscar(self, _evento=None) -> None:
        self._cancelar_busca()
        anterior = self.produto_atual.id if self.produto_atual else None
        self._limpar_selecao()
        limpar_tabela(self.tabela_busca)
        self._resultados_busca = []
        self.botao_mais.grid_remove()
        try:
            resultado = self.controlador.pesquisar_produtos(self.var_busca.get())
        except ERROS_EXIBIVEIS as falha:
            self.status_busca.configure(text=mensagem_falha(falha))
            return
        self._resultados_busca = resultado.produtos
        self._busca_aproximada = resultado.aproximada
        self._mostrar_mais()
        if resultado.aviso:
            self.status_busca.configure(text=resultado.aviso)
        # Uma sugestão aproximada nunca escolhe um produto silenciosamente.
        ids = {p.id for p in resultado.produtos}
        escolhido = anterior if anterior in ids else None
        if escolhido is None and len(ids) == 1 and self.var_busca.get().strip() and not resultado.aproximada:
            escolhido = resultado.produtos[0].id
        if escolhido is not None:
            while not self.tabela_busca.exists(str(escolhido)):
                self._mostrar_mais()
            self.tabela_busca.selection_set(str(escolhido))
            self.tabela_busca.see(str(escolhido))
            self._carregar_produto(escolhido)

    def _mostrar_mais(self):
        inicio = len(self.tabela_busca.get_children())
        for item in self._resultados_busca[inicio:inicio + 200]:
            self.tabela_busca.insert("", "end", iid=str(item.id),
                                     values=(item.id, item.nome, item.marca, item.estoque_atual))
        exibidos = len(self.tabela_busca.get_children())
        total = len(self._resultados_busca)
        mensagem = f'{exibidos} de {total} produto(s)'
        if self._busca_aproximada and total:
            mensagem += ' · Opções próximas: selecione o produto.'
        elif not total:
            mensagem = 'Nenhum produto encontrado. Tente menos palavras ou confira a escrita.'
        self.status_busca.configure(text=mensagem)
        if exibidos < total:
            self.botao_mais.grid(row=1, column=0, sticky='w', pady=(6, 0))
        else:
            self.botao_mais.grid_remove()

    def _ao_selecionar(self, _evento=None) -> None:
        selecao = self.tabela_busca.selection()
        if selecao and self._busca_agendada is None and (self.produto_atual is None or self.produto_atual.id != int(selecao[0])):
            self._carregar_produto(int(selecao[0]))

    def _carregar_produto(self, produto_id: int) -> None:
        try:
            produto = self.controlador.obter_produto(produto_id)
        except ERROS_EXIBIVEIS as falha:
            erro("Produto", mensagem_falha(falha))
            return
        self.produto_atual = produto
        self.botao_ajuste.configure(state='normal')
        self.botao_vincular.configure(state='normal')
        self.rotulo_produto.configure(
            text=f"#{produto.id}  {produto.nome}  ({produto.marca} • {produto.categoria})\n"
                 f"Estoque atual: {produto.estoque_atual} un.   Custo médio: {formatar_moeda(produto.custo_medio)}   "
                 f"Preço base: {formatar_moeda(produto.preco_venda_base)}")
        for entrada, valor in ((self.entrada_nome, produto.nome),
                               (self.entrada_preco, self._texto_decimal(produto.preco_venda_base)),
                               (self.entrada_estoque, str(produto.estoque_atual)),
                               (self.entrada_custo, self._texto_decimal(produto.custo_medio))):
            entrada.delete(0, "end")
            entrada.insert(0, valor)
        self.combo_marca.set(produto.marca)
        self.combo_categoria.set(produto.categoria)
        self.lista_codigos.definir(produto.codigos)

    @staticmethod
    def _texto_decimal(valor: float) -> str:
        """Texto exibido no campo; comparado depois para detectar edição."""
        return str(valor).replace(".", ",")

    def _limpar_selecao(self) -> None:
        self.produto_atual = None
        self.botao_ajuste.configure(state='disabled')
        self.botao_vincular.configure(state='disabled')
        self.rotulo_produto.configure(text="Nenhum produto selecionado.")
        for entrada in (self.entrada_nome, self.entrada_preco, self.entrada_estoque,
                        self.entrada_custo, self.entrada_codigo):
            entrada.delete(0, "end")
        self.combo_marca.set("")
        self.combo_categoria.set("")
        self.lista_codigos.limpar()

    def ao_ocultar(self):
        self._cancelar_busca()

    def destroy(self):
        self._cancelar_busca()
        self.var_busca.trace_remove('write', self._trace_busca)
        self._resultados_busca = []
        super().destroy()

    # ------------------------------------------------------------------ #
    # Ajuste manual
    # ------------------------------------------------------------------ #
    def _campos_alterados(self) -> dict:
        """Somente os campos editados; os demais não sobrescrevem nem arredondam valores."""
        p = self.produto_atual
        campos = {}
        if self.entrada_nome.get().strip() != p.nome:
            campos["nome"] = self.entrada_nome.get()
        if self.combo_marca.get() != p.marca:
            campos["marca"] = self.combo_marca.get()
        if self.combo_categoria.get() != p.categoria:
            campos["categoria"] = self.combo_categoria.get()
        if self.entrada_preco.get() != self._texto_decimal(p.preco_venda_base):
            campos["preco_venda_base"] = self.entrada_preco.get()
        if self.entrada_estoque.get() != str(p.estoque_atual):
            campos["novo_estoque"] = self.entrada_estoque.get()
        if self.entrada_custo.get() != self._texto_decimal(p.custo_medio):
            campos["novo_custo"] = self.entrada_custo.get()
        return campos

    def _aplicar_ajuste(self) -> None:
        if self.produto_atual is None:
            erro("Ajuste", "Selecione um produto primeiro.")
            return
        campos = self._campos_alterados()
        if not campos:
            erro("Ajuste", "Nenhuma alteração detectada: os valores são iguais aos atuais.")
            return
        produto = self.produto_atual
        rotulos = {"nome": "Nome", "marca": "Marca", "categoria": "Categoria", "preco_venda_base": "Preço base",
                   "novo_estoque": "Estoque", "novo_custo": "Custo médio"}
        resultado = confirmar_com_senha(
            self, "Confirmar ajuste",
            f"Aplicar as alterações em '{produto.nome}'?\n"
            f"Campos alterados: {', '.join(rotulos[c] for c in campos)}.",
            lambda senha: self.controlador.editar_produto(
                produto.id, **campos, estoque_esperado=produto.estoque_atual,
                custo_esperado=produto.custo_medio, senha=senha),
            "Aplicar")
        if resultado is None:
            return
        informar("Ajuste aplicado", "\n".join(resultado.alteracoes))
        if not self.winfo_exists():
            return
        self._carregar_produto(produto.id)
        self._buscar()

    # ------------------------------------------------------------------ #
    # Códigos de barras
    # ------------------------------------------------------------------ #
    def _vincular_codigo(self, _evento=None) -> None:
        if self.produto_atual is None:
            erro("Códigos", "Selecione um produto primeiro.")
            return
        try:
            codigo = self.controlador.validar_codigo_barras(self.entrada_codigo.get())
            self.controlador.vincular_codigo_barras(codigo, self.produto_atual.id)
        except ERROS_EXIBIVEIS as falha:
            erro("Códigos", mensagem_falha(falha))
            return
        self.lista_codigos.adicionar(codigo)
        self.entrada_codigo.delete(0, "end")
        self.entrada_codigo.focus_set()

    def _desvincular_codigo(self, codigo: str) -> bool:
        """Callback da ListaCodigos: remove do banco antes de tirar da lista."""
        if not confirmar("Desvincular código", f"Remover o código {codigo} deste produto?"):
            return False
        try:
            if self.produto_atual is None:
                raise ErroNegocio("Selecione novamente o produto antes de remover o código.")
            self.controlador.desvincular_codigo_barras(codigo, produto_id_esperado=self.produto_atual.id)
        except ERROS_EXIBIVEIS as falha:
            erro("Códigos", mensagem_falha(falha))
            return False
        return True
