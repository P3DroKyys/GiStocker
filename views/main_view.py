"""
Janela principal (JanelaPrincipal): barra lateral de navegação + área de conteúdo.

Cada tela é um CTkFrame criado sob demanda e trocado na área central.
Protocolo opcional que as telas podem implementar:
  * ao_mostrar(**dados)  -> chamado sempre que a tela é exibida
                            (ex.: refocar o leitor, atualizar o dashboard);
  * ao_mudar_tema()      -> chamado após alternar claro/escuro
                            (ex.: redesenhar gráficos e cores de tabela).
Para navegar a partir de qualquer tela: ``self.janela.mostrar_view("cadastro", codigo="789...")``.
"""
from __future__ import annotations

from typing import Callable
import sys
import time

from controllers.controllers import ControladorEstoque, ControladorRelatorios

import customtkinter as ctk
from PIL import Image

import config
from views.componentes import COR_TEXTO_SUAVE, aplicar_estilo_treeview
from views.acesso import TelaAcesso
from views.tarefas import cancelar_tarefas
from views.view_configuracoes import ViewConfiguracoes
from views.view_integracoes import ViewIntegracoes
from views.view_admin import ViewAdmin
from views.view_cadastro import ViewCadastro
from views.view_dashboard import ViewDashboard
from views.view_operacao import ViewOperacao
from views.view_relatorios import ViewRelatorios

# (chave, rótulo do menu, atalho, classe)
TELAS = [
    ("operacao",   "Operação",   "F1", ViewOperacao),
    ("cadastro",   "Cadastro",   "F2", ViewCadastro),
    ("dashboard",  "Dashboard",  "F3", ViewDashboard),
    ("relatorios", "Relatórios", "F4", ViewRelatorios),
    ("admin",      "Admin",      "F5", ViewAdmin),
]


class JanelaPrincipal(ctk.CTk):
    def __init__(self, preferencias):
        super().__init__()
        self.controlador_estoque = None
        self.controlador_relatorios = None
        self._ao_fechar = preferencias.fechar
        self.preferencias = preferencias
        self._desbloqueado = False
        self._atualizacao_tema = None

        self.title(config.NOME_APP)
        if sys.platform == "win32":
            self.iconbitmap(default=str(config.CAMINHO_ICONE))
        self.geometry(f"{config.LARGURA_JANELA}x{config.ALTURA_JANELA}")
        self.minsize(config.LARGURA_MINIMA, config.ALTURA_MINIMA)
        self.protocol("WM_DELETE_WINDOW", self._fechar)
        aplicar_estilo_treeview()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.views: dict[str, ctk.CTkFrame] = {}
        self.view_atual: ctk.CTkFrame | None = None
        self.botoes_navegacao: dict[str, ctk.CTkButton] = {}

        self._ultimo_uso = time.monotonic()
        self._inatividade = self.after(1000, self._conferir_inatividade)
        for evento in ("<KeyPress>", "<ButtonPress>", "<MouseWheel>"):
            self.bind_all(evento, self._registrar_atividade, add="+")
        self.bind("<Control-l>", lambda _e: self.bloquear())
        self.tela_acesso = TelaAcesso(self, preferencias, self._liberar_acesso)
        self.tela_acesso.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self._foco_acesso = self.after(150, self._focar_acesso)

    def _focar_acesso(self) -> None:
        self._foco_acesso = None
        if not self._desbloqueado:
            campo = self.tela_acesso.nova_senha if self.tela_acesso.modo == "novo" else self.tela_acesso.campo_senha
            campo.entrada.focus_set()

    def _servico_indisponivel(self):
        if self._desbloqueado:
            self.after_idle(self.bloquear)

    def recarregar_acesso(self):
        """A migração do banco pode terminar antes de uma falha ao proteger cópias."""
        if self._desbloqueado:
            return
        if self._foco_acesso is not None:
            self.after_cancel(self._foco_acesso)
            self._foco_acesso = None
        cancelar_tarefas(self.tela_acesso)
        self.tela_acesso.destroy()
        self.tela_acesso = TelaAcesso(self, self.preferencias, self._liberar_acesso)
        self.tela_acesso.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.tela_acesso.mensagem.configure(
            text="O banco já foi protegido. Use a NOVA senha para concluir a proteção das cópias antigas. "
                 "Se houver erro, confira o espaço e as permissões da pasta.")
        self._focar_acesso()

    def _liberar_acesso(self) -> None:
        """Chamado pela tela de acesso somente após conferir a senha."""
        if self._desbloqueado:
            return
        banco = self.preferencias.banco
        if banco is None or banco._fechado or not banco.criptografado:
            return
        if hasattr(self.preferencias, 'criar_controladores'):
            self.controlador_estoque, self.controlador_relatorios = self.preferencias.criar_controladores()
            self.preferencias.ao_indisponivel = self._servico_indisponivel
        else:
            # Injeção de dependências dos testes antigos; main.py sempre usa IPC.
            self.controlador_estoque = ControladorEstoque(banco)
            self.controlador_relatorios = ControladorRelatorios(banco)
        self._ultimo_uso = time.monotonic()
        if self._foco_acesso is not None:
            self.after_cancel(self._foco_acesso)
            self._foco_acesso = None
        cancelar_tarefas(self.tela_acesso)
        self.tela_acesso.destroy()
        self._desbloqueado = True
        ctk.set_appearance_mode(self.preferencias.obter_tema())
        aplicar_estilo_treeview()

        self._construir_barra_lateral()
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.grid(row=0, column=1, sticky="nsew", padx=24, pady=24)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        for chave, _, atalho, _ in TELAS:
            self.bind(f"<{atalho}>", lambda e, c=chave: self.mostrar_view(c) if not e.state & 0x2000 and not e.state & 0x8 else None)

        self.mostrar_view("operacao")

    # ------------------------------------------------------------------ #
    # Barra lateral
    # ------------------------------------------------------------------ #
    def _construir_barra_lateral(self) -> None:
        barra = ctk.CTkFrame(self, width=216, corner_radius=0,
                            fg_color=("#E9EDF4", "#191E27"))
        self.barra = barra
        barra.grid(row=0, column=0, sticky="nsw")
        barra.grid_propagate(False)
        barra.grid_rowconfigure(10, weight=1)     # empurra o rodapé para baixo

        # A imagem original tem transparência e é compartilhada pelos dois temas.
        with Image.open(config.CAMINHO_LOGO) as imagem:
            original = imagem.copy()
        largura_logo = 184
        altura_logo = round(largura_logo * original.height / original.width)
        self.logo = ctk.CTkImage(light_image=original, dark_image=original,
                                 size=(largura_logo, altura_logo))
        # CTkLabel adiciona padding interno quando há corner_radius. A logo
        # ocupa 184 + 2*16 = 216 px; não pode herdar esse padding do tema.
        ctk.CTkLabel(barra, text="", image=self.logo, corner_radius=0,
                     width=largura_logo, height=altura_logo, padx=0, pady=0
                     ).grid(row=0, column=0, padx=16, pady=(24, 18))
        ctk.CTkLabel(barra, text="NAVEGAÇÃO", text_color=COR_TEXTO_SUAVE,
                     font=ctk.CTkFont(size=10, weight="bold")
                     ).grid(row=1, column=0, padx=22, pady=(8, 10), sticky="w")

        for indice, (chave, rotulo, atalho, _) in enumerate(TELAS, start=2):
            botao = ctk.CTkButton(
                barra, text=f"{rotulo}   ·   {atalho}", anchor="w", height=44, corner_radius=10,
                fg_color="transparent", hover_color=("#DDE5F0", "#293342"),
                text_color=("#475467", "#AFBBCD"), font=ctk.CTkFont(size=14),
                command=lambda c=chave: self.mostrar_view(c),
            )
            botao.grid(row=indice, column=0, padx=12, pady=3, sticky="ew")
            self.botoes_navegacao[chave] = botao
        barra.grid_columnconfigure(0, weight=1)

        botao = ctk.CTkButton(barra, text="⚙   Configurações", anchor="w", height=44,
                              fg_color="transparent", hover_color=("#DDE5F0", "#293342"),
                              text_color=("#475467", "#AFBBCD"), font=ctk.CTkFont(size=14),
                              command=lambda: self.mostrar_view("configuracoes"))
        botao.grid(row=11, column=0, padx=12, pady=(12, 18), sticky="ew")
        self.botoes_navegacao["configuracoes"] = botao

    def _destacar_botao(self, chave_ativa: str) -> None:
        for chave, botao in self.botoes_navegacao.items():
            ativo = chave == chave_ativa
            botao.configure(fg_color=("#D3E6F8", "#233C56") if ativo else "transparent",
                            text_color=("#075B9F", "#99D3FF") if ativo else ("#475467", "#AFBBCD"),
                            font=ctk.CTkFont(size=14, weight="bold" if ativo else "normal"))

    # ------------------------------------------------------------------ #
    # Navegação
    # ------------------------------------------------------------------ #
    def mostrar_view(self, chave: str, **dados) -> None:
        """Exibe a tela ``chave``; ``dados`` são repassados a ``ao_mostrar``."""
        if not self._desbloqueado:
            return
        if chave not in self.views:
            classe = ViewIntegracoes if chave == 'integracoes' else ViewConfiguracoes if chave == "configuracoes" else next(cls for c, _, _, cls in TELAS if c == chave)
            self.views[chave] = classe(self.container, self)
        if self.view_atual is not None:
            if hasattr(self.view_atual, "ao_ocultar"):
                self.view_atual.ao_ocultar()
            self.view_atual.grid_forget()
        view = self.views[chave]
        view.grid(row=0, column=0, sticky="nsew")
        self.view_atual = view
        self._destacar_botao(chave)
        if hasattr(view, "ao_mostrar"):
            view.ao_mostrar(**dados)

    # ------------------------------------------------------------------ #
    # Tema
    # ------------------------------------------------------------------ #
    def alternar_tema(self, tema: str) -> None:
        if not self._desbloqueado:
            return
        self.preferencias.definir_tema(tema)
        ctk.set_appearance_mode(tema)
        aplicar_estilo_treeview()
        # Pequeno atraso para o customtkinter terminar de repintar os widgets.
        if self._atualizacao_tema is not None:
            self.after_cancel(self._atualizacao_tema)
        self._atualizacao_tema = self.after(80, self._notificar_mudanca_tema)

    def _notificar_mudanca_tema(self) -> None:
        self._atualizacao_tema = None
        for view in self.views.values():
            if hasattr(view, "ao_mudar_tema"):
                view.ao_mudar_tema()

    # ------------------------------------------------------------------ #
    def _registrar_atividade(self, _evento=None):
        agora = time.monotonic()
        if self._desbloqueado and agora - self._ultimo_uso >= config.MINUTOS_BLOQUEIO_INATIVIDADE * 60:
            self.bloquear()
        if self._desbloqueado and hasattr(self.preferencias, 'atividade') and agora-self.__dict__.get('_ultimo_ipc',0)>30:
            from models.seguranca import ErroSeguranca
            try:
                self.preferencias.atividade()
                self._ultimo_ipc = agora
            except ErroSeguranca:
                self.bloquear()
        self._ultimo_uso = agora

    def _conferir_inatividade(self):
        self._inatividade = None
        if self._desbloqueado and time.monotonic() - self._ultimo_uso >= config.MINUTOS_BLOQUEIO_INATIVIDADE * 60:
            self.bloquear()
        self._inatividade = self.after(1000, self._conferir_inatividade)

    def bloquear(self):
        if not self._desbloqueado:
            return
        self._desbloqueado = False
        if self._atualizacao_tema is not None:
            self.after_cancel(self._atualizacao_tema)
            self._atualizacao_tema = None
        for _, _, atalho, _ in TELAS:
            self.unbind(f"<{atalho}>")
        # Destruir widgets também fecha diálogos que possam exibir informações.
        for filho in list(self.winfo_children()):
            if filho.winfo_exists():
                cancelar_tarefas(filho)
                filho.destroy()
        self.views.clear()
        self.view_atual = None
        self.botoes_navegacao.clear()
        self.controlador_estoque = self.controlador_relatorios = None
        self.preferencias.fechar()
        self.tela_acesso = TelaAcesso(self, self.preferencias, self._liberar_acesso)
        self.tela_acesso.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self._foco_acesso = self.after(150, self._focar_acesso)

    def _fechar(self) -> None:
        for tarefa in (self._foco_acesso, self._atualizacao_tema, self._inatividade):
            if tarefa is not None:
                self.after_cancel(tarefa)
        try:
            self._ao_fechar()
        finally:
            cancelar_tarefas(self, todas=True)
            self.destroy()

    def report_callback_exception(self, tipo, valor, traceback_obj):
        """Última proteção para falhas em callbacks, inclusive consultas e atualização visual."""
        from utils.erros import registrar_falha
        from views.componentes import erro
        registrar_falha(valor.with_traceback(traceback_obj))
        erro('Não foi possível concluir a ação',
             'Ocorreu uma falha. Confira o estoque e o histórico antes de repetir a operação. '
             'Verifique o espaço e as permissões da pasta do programa. Detalhes em erros.log.')
