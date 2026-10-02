"""
Componentes visuais reutilizáveis e paleta de cores da interface.

Aqui ficam:
  * PALETA ............... cores para gráficos e tabelas nos modos claro/escuro
                           (paleta categórica validada para daltonismo/contraste);
  * aplicar_estilo_treeview / criar_tabela ... ttk.Treeview integrada ao tema;
  * CartaoKPI ............ cartão de indicador do dashboard;
  * ListaCodigos ......... lista de "chips" de códigos de barras com botão remover;
  * informar / alertar / erro / confirmar ... atalhos para caixas de diálogo.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

import customtkinter as ctk
from views.dialogos import mostrar_dialogo

PALETA = {
    "light": {
        "texto": "#202632",
        "texto_secundario": "#526174",
        "texto_suave": "#8794A6",
        "grade": "#E5EAF2",
        "eixo": "#A0ACBD",
        "tabela_fundo": "#FFFFFF",
        "tabela_cabecalho": "#EDF2F8",
        "selecao": "#0875D1",
        "series": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
                   "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
    },
    "dark": {
        "texto": "#EFF2F7",
        "texto_secundario": "#A0ACBD",
        "texto_suave": "#8794A6",
        "grade": "#303947",
        "eixo": "#394150",
        "tabela_fundo": "#20252E",
        "tabela_cabecalho": "#29313D",
        "selecao": "#245582",
        "series": ["#3987e5", "#d95926", "#199e70", "#c98500",
                   "#d55181", "#008300", "#9085e9", "#e66767"],
    },
}

# Cores em tupla (claro, escuro): o customtkinter escolhe a certa automaticamente.
COR_TEXTO_SUCESSO = ("#006300", "#4ade80")
COR_TEXTO_ERRO = ("#b91c1c", "#f87171")
COR_TEXTO_INFO = ("#526174", "#A0ACBD")
COR_TEXTO_SUAVE = ("#667085", "#A0ACBD")
COR_PERIGO = ("#AE414C", "#963541")          # (fg_color, hover_color)
COR_BOTAO_SECUNDARIO = ("gray75", "gray30")


# --------------------------------------------------------------------------- #
# Tema / cores
# --------------------------------------------------------------------------- #
def modo_atual() -> str:
    """'light' ou 'dark' conforme o modo de aparência ativo."""
    return "dark" if ctk.get_appearance_mode().lower() == "dark" else "light"


def paleta_atual() -> dict:
    return PALETA[modo_atual()]


def cor_para_hex(widget: tk.Misc, cor: str) -> str:
    """Converte nomes de cor do Tk (ex.: 'gray90') para '#rrggbb' (matplotlib exige hex)."""
    if isinstance(cor, str) and cor.startswith("#") and len(cor) == 7:
        return cor
    r, g, b = widget.winfo_rgb(cor)
    return f"#{r // 256:02x}{g // 256:02x}{b // 256:02x}"


def _resolver_cor_modo(cor) -> str:
    if isinstance(cor, (list, tuple)):
        return cor[1] if modo_atual() == "dark" else cor[0]
    return cor


def cor_fundo_efetiva(widget: tk.Misc) -> str:
    """Cor de fundo real de um widget customtkinter (sobe a hierarquia se for
    'transparent'). Usada para o fundo dos gráficos matplotlib."""
    atual: tk.Misc | None = widget
    while atual is not None:
        try:
            cor = atual.cget("fg_color")
        except (tk.TclError, ValueError, AttributeError):
            cor = None
        if cor and cor != "transparent":
            return cor_para_hex(widget, _resolver_cor_modo(cor))
        atual = atual.master
    cor_janela = ctk.ThemeManager.theme["CTk"]["fg_color"]
    return cor_para_hex(widget, _resolver_cor_modo(cor_janela))


# --------------------------------------------------------------------------- #
# Tabelas (ttk.Treeview integrada ao tema)
# --------------------------------------------------------------------------- #
def aplicar_estilo_treeview() -> None:
    """Configura o estilo global das Treeviews para o modo claro/escuro ativo.
    Deve ser chamada na inicialização e sempre que o tema mudar."""
    p = paleta_atual()
    estilo = ttk.Style()
    try:
        estilo.theme_use("clam")        # único tema ttk que aceita cores livremente
    except tk.TclError:
        pass
    estilo.configure("Treeview",
                     background=p["tabela_fundo"], fieldbackground=p["tabela_fundo"],
                     foreground=p["texto"], rowheight=34, borderwidth=0, relief="flat",
                     font=("Segoe UI", 10))
    estilo.configure("Treeview.Heading",
                     background=p["tabela_cabecalho"], foreground=p["texto"],
                     relief="flat", borderwidth=0, padding=(10, 9),
                     font=("Segoe UI", 10, "bold"))
    estilo.map("Treeview",
               background=[("selected", p["selecao"])],
               foreground=[("selected", "#EFF2F7")])
    estilo.map("Treeview.Heading", background=[("active", p["tabela_cabecalho"])])


def criar_tabela(master, colunas: list[tuple], altura: int = 12,
                 rolagem_horizontal: bool = False) -> tuple[ctk.CTkFrame, ttk.Treeview]:
    """Cria uma Treeview com barra de rolagem.

    ``colunas``: lista de (id, título, largura, âncora, estica?) — ex.:
        ("nome", "Produto", 240, "w", True)
    Retorna (quadro, tabela). Posicione o ``quadro`` com grid/pack.
    """
    quadro = ctk.CTkFrame(master, fg_color="transparent")
    tabela = ttk.Treeview(quadro, columns=[c[0] for c in colunas], show="headings",
                          height=altura, selectmode="browse")
    for identificador, titulo, largura, ancora, estica in colunas:
        tabela.heading(identificador, text=titulo, anchor=ancora)
        tabela.column(identificador, width=largura, minwidth=largura if rolagem_horizontal else 40,
                       anchor=ancora, stretch=estica)
    barra = ctk.CTkScrollbar(quadro, command=tabela.yview)
    tabela.configure(yscrollcommand=barra.set)
    tabela.grid(row=0, column=0, sticky="nsew")
    barra.grid(row=0, column=1, sticky="ns", padx=(4, 0))
    if rolagem_horizontal:
        barra_horizontal = ctk.CTkScrollbar(quadro, orientation="horizontal", command=tabela.xview)
        tabela.configure(xscrollcommand=barra_horizontal.set)
        barra_horizontal.grid(row=1, column=0, sticky="ew", pady=(4, 0))
    quadro.grid_columnconfigure(0, weight=1)
    quadro.grid_rowconfigure(0, weight=1)
    return quadro, tabela


def limpar_tabela(tabela: ttk.Treeview) -> None:
    tabela.delete(*tabela.get_children())


# --------------------------------------------------------------------------- #
# Cartão de KPI
# --------------------------------------------------------------------------- #
class CartaoKPI(ctk.CTkFrame):
    def __init__(self, master, titulo: str, **kwargs):
        super().__init__(master, corner_radius=14, **kwargs)
        ctk.CTkLabel(self, text=titulo, text_color=COR_TEXTO_SUAVE, anchor="w",
                     font=ctk.CTkFont(size=13)).pack(fill="x", padx=16, pady=(14, 0))
        self.rotulo_valor = ctk.CTkLabel(self, text="—", anchor="w",
                                         font=ctk.CTkFont(size=26, weight="bold"))
        self.rotulo_valor.pack(fill="x", padx=16, pady=(2, 14))

    def definir(self, valor: str) -> None:
        self.rotulo_valor.configure(text=valor)


# --------------------------------------------------------------------------- #
# Lista de códigos de barras ("chips")
# --------------------------------------------------------------------------- #
class ListaCodigos(ctk.CTkFrame):
    """Mostra códigos vinculados como linhas com botão ✕.

    ``ao_remover(codigo) -> bool``: callback opcional chamado antes de remover;
    se retornar False a remoção é cancelada (ex.: falha ao desvincular no banco).
    """

    def __init__(self, master, ao_remover: Callable[[str], bool] | None = None,
                 altura: int = 150, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._codigos: list[str] = []
        self._ao_remover = ao_remover
        self._area = ctk.CTkScrollableFrame(self, height=altura, corner_radius=8)
        self._area.pack(fill="both", expand=True)
        self._redesenhar()

    # API pública ------------------------------------------------------- #
    def obter(self) -> list[str]:
        return list(self._codigos)

    def adicionar(self, codigo: str) -> bool:
        codigo = (codigo or "").strip()
        if not codigo or codigo in self._codigos:
            return False
        self._codigos.append(codigo)
        self._redesenhar()
        return True

    def remover(self, codigo: str) -> None:
        if codigo in self._codigos:
            self._codigos.remove(codigo)
            self._redesenhar()

    def definir(self, codigos: list[str]) -> None:
        self._codigos = [c for c in codigos if c]
        self._redesenhar()

    def limpar(self) -> None:
        self.definir([])

    # Interno ----------------------------------------------------------- #
    def _tentar_remover(self, codigo: str) -> None:
        if self._ao_remover is not None and not self._ao_remover(codigo):
            return
        self.remover(codigo)

    def _redesenhar(self) -> None:
        for filho in self._area.winfo_children():
            filho.destroy()
        if not self._codigos:
            ctk.CTkLabel(self._area, text="Nenhum código vinculado.",
                         text_color=COR_TEXTO_SUAVE).pack(anchor="w", padx=8, pady=6)
            return
        for codigo in self._codigos:
            linha = ctk.CTkFrame(self._area, fg_color="transparent")
            linha.pack(fill="x", pady=2)
            ctk.CTkLabel(linha, text=codigo, anchor="w",
                         font=ctk.CTkFont(family="Consolas", size=13)).pack(side="left", padx=(8, 0))
            ctk.CTkButton(linha, text="✕", width=30, height=26, fg_color="transparent",
                          hover_color=COR_PERIGO[0], text_color=COR_TEXTO_SUAVE,
                          command=lambda c=codigo: self._tentar_remover(c)).pack(side="right", padx=4)


# --------------------------------------------------------------------------- #
# Diálogos
# --------------------------------------------------------------------------- #
def informar(titulo: str, mensagem: str) -> None:
    mostrar_dialogo(titulo, mensagem, 'sucesso')


def alertar(titulo: str, mensagem: str) -> None:
    mostrar_dialogo(titulo, mensagem, 'aviso')


def erro(titulo: str, mensagem: str) -> None:
    mostrar_dialogo(titulo, mensagem, 'erro')


def confirmar(titulo: str, mensagem: str) -> bool:
    return mostrar_dialogo(titulo, mensagem, 'confirmacao')
