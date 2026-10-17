"""
Busca, histórico e exportação (View_Relatorios).

  * busca inteligente de produtos ("refil lily" encontra "Refil Hidratante Lily");
  * Treeview com o histórico completo de Logs_Movimentacao (logs cancelados
    aparecem esmaecidos); selecionar um produto filtra o histórico;
  * exportação de estoque e logs para CSV com carimbo de data/hora (pandas).
"""
from __future__ import annotations

import os
import sys

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
ATRASO_BUSCA_MS = 250


class ViewRelatorios(ctk.CTkFrame):
    def __init__(self, master, janela):
        super().__init__(master, fg_color="transparent")
        self.janela = janela
        self.controlador = janela.controlador_estoque
        self.relatorios = janela.controlador_relatorios
        self._busca_agendada = None
        self.produto_filtro: int | None = None
        self._ultimo_log = None
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

        # Histórico
        linha_logs = ctk.CTkFrame(self, fg_color="transparent")
        linha_logs.grid(row=3, column=0, sticky="ew", pady=(14, 6))
        ctk.CTkLabel(linha_logs, text="Histórico de movimentações",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        self.rotulo_filtro = ctk.CTkLabel(linha_logs, text="", text_color=COR_TEXTO_SUAVE)
        self.rotulo_filtro.pack(side="left", padx=12)
        ctk.CTkButton(linha_logs, text="Mostrar todos", width=120, height=30,
                      fg_color="transparent", border_width=1, text_color=("gray10", "#DCE4EE"),
                      command=self._limpar_filtro).pack(side="right")
        self.botao_mais_logs = ctk.CTkButton(linha_logs, text='Carregar mais', width=120, height=30,
                                             command=lambda: self._carregar_logs(mais=True))
        self.botao_mais_logs.pack(side='right', padx=8)

        quadro_logs, self.tabela_logs = criar_tabela(self, COLUNAS_LOGS, altura=12, rolagem_horizontal=True)
        quadro_logs.grid(row=4, column=0, sticky="nsew")
        self.ao_mudar_tema()

    # ------------------------------------------------------------------ #
    # Protocolo da janela principal
    # ------------------------------------------------------------------ #
    def ao_mostrar(self, **_dados) -> None:
        self._buscar()
        self._carregar_logs()
        self.entrada_busca.focus_set()

    def ao_mudar_tema(self) -> None:
        self.tabela_logs.tag_configure("cancelado", foreground=paleta_atual()["texto_suave"])

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
        self._carregar_logs()

    def _limpar_filtro(self) -> None:
        self.produto_filtro = None
        self.rotulo_filtro.configure(text="")
        self.tabela_produtos.selection_remove(self.tabela_produtos.selection())
        self._carregar_logs()

    # ------------------------------------------------------------------ #
    # Histórico
    # ------------------------------------------------------------------ #
    def _carregar_logs(self, mais=False) -> None:
        logs = self.controlador.listar_logs(limite=200, produto_id=self.produto_filtro,
                                            antes_id=self._ultimo_log if mais else None)
        if not mais:
            limpar_tabela(self.tabela_logs)
        self._ultimo_log = logs[-1]['id'] if logs else None
        self.botao_mais_logs.configure(state='normal' if len(logs) == 200 else 'disabled')
        for log in logs:
            etiquetas = ("cancelado",) if log["cancelado"] else ()
            self.tabela_logs.insert("", "end", tags=etiquetas, values=(
                log["id"], formatar_data_hora(log["data_hora"]), log["tipo"],
                log["produto_nome"], log["produto_marca"], log["quantidade"],
                formatar_moeda(log["custo_no_momento"]), log["estoque_anterior"],
                log["estoque_posterior"], "Cancelado" if log["cancelado"] else "Válido",
                log["observacao"] or "",
                {'FISICO':'Físico','SHOPEE':'Shopee','TIKTOK':'TikTok Shop'}.get(log.get('origem','FISICO'),'Físico'),
                ('•••'+str(log.get('referencia'))[-6:]) if log.get('referencia') else '',
            ))

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
