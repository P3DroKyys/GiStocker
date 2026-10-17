"""Painel de aparência, versão e troca da senha de acesso."""
import sqlite3
from models.seguranca import ERROS_BANCO, ERROS_OPERACIONAIS, ErroSeguranca

import customtkinter as ctk

import config
from models.preferencias import ErroPreferencias
from views.acesso import CampoSenha
from views.componentes import COR_TEXTO_ERRO, COR_TEXTO_SUAVE, COR_TEXTO_SUCESSO
from views.gestao_dados import PainelGestao


class ViewConfiguracoes(ctk.CTkFrame):
    def __init__(self, master, janela):
        super().__init__(master, fg_color="transparent")
        self.janela = janela
        self._salvando = False
        cabecalho = ctk.CTkFrame(self, fg_color="transparent")
        cabecalho.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(cabecalho, text="Configurações", anchor="w", font=ctk.CTkFont(size=24, weight="bold")
                     ).pack(side="left")
        ctk.CTkLabel(cabecalho, text=f"GiStocker  ·  Versão {config.VERSAO_APP}",
                     text_color=COR_TEXTO_SUAVE).pack(side="right", padx=12)
        area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        area.pack(fill="both", expand=True)
        aparencia = ctk.CTkFrame(area, corner_radius=14)
        aparencia.pack(fill="x", pady=(0, 14), padx=4)
        descricao = ctk.CTkFrame(aparencia, fg_color="transparent")
        descricao.pack(side="left", fill="x", expand=True, padx=22, pady=20)
        ctk.CTkLabel(descricao, text="Aparência", anchor="w", font=ctk.CTkFont(size=17, weight="bold")
                     ).pack(fill="x")
        ctk.CTkLabel(descricao, text="Escolha o modo de exibição.", anchor="w",
                     text_color=COR_TEXTO_SUAVE).pack(fill="x")
        self.seletor_tema = ctk.CTkSegmentedButton(
            aparencia, values=["Claro", "Escuro"], width=220, height=40,
            dynamic_resizing=False, command=self._alterar_tema)
        self.seletor_tema.pack(side="right", padx=22, pady=20)

        protecao = self._cartao(area, "Proteção da sessão", f"Bloqueio automático após {config.MINUTOS_BLOQUEIO_INATIVIDADE} minutos sem uso. Atalho: Ctrl+L.")
        ctk.CTkButton(protecao, text="Bloquear agora", command=janela.bloquear, height=40).pack(anchor="w", padx=22, pady=16)
        integracoes = self._cartao(area, 'Integrações', 'Modo físico offline e ambiente isolado para simular Shopee e TikTok Shop.')
        ctk.CTkButton(integracoes, text='Abrir integrações', height=40,
                      state='normal' if hasattr(janela.preferencias,'chamar') else 'disabled',
                      command=lambda:janela.mostrar_view('integracoes')).pack(anchor='w',padx=22,pady=16)
        self.gestao_dados = PainelGestao(area, janela)
        senha = self._cartao(area, "Senha de acesso", "Confirme sua senha atual para cadastrar uma nova.")
        self.senha_atual = self._campo(senha, "Senha atual")
        self.nova_senha = self._campo(senha, f"Nova senha · {config.MINIMO_CARACTERES_SENHA} a 128 caracteres")
        self.confirmacao = self._campo(senha, "Confirme a nova senha")
        self.confirmacao.entrada.bind("<Return>", self._alterar_senha)
        self.confirmacao.entrada.bind("<KP_Enter>", self._alterar_senha)
        self.mensagem = ctk.CTkLabel(senha, text="", anchor="w", justify="left", wraplength=520)
        self.mensagem.pack(fill="x", padx=22, pady=(8, 0))
        self.botao_salvar = ctk.CTkButton(senha, text="Alterar senha", height=42, width=180,
                                         command=self._alterar_senha)
        self.botao_salvar.pack(anchor="w", padx=22, pady=(6, 22))

    @staticmethod
    def _cartao(master, titulo, descricao):
        cartao = ctk.CTkFrame(master, corner_radius=14)
        cartao.pack(fill="x", pady=(0, 14), padx=4)
        ctk.CTkLabel(cartao, text=titulo, anchor="w", font=ctk.CTkFont(size=17, weight="bold")
                     ).pack(fill="x", padx=22, pady=(18, 2))
        ctk.CTkLabel(cartao, text=descricao, anchor="w", text_color=COR_TEXTO_SUAVE
                     ).pack(fill="x", padx=22)
        return cartao

    @staticmethod
    def _campo(master, titulo):
        ctk.CTkLabel(master, text=titulo, anchor="w").pack(fill="x", padx=22, pady=(12, 4))
        campo = CampoSenha(master)
        campo.pack(fill="x", padx=22)
        return campo

    def ao_mostrar(self, **_dados):
        self.seletor_tema.set("Escuro" if ctk.get_appearance_mode().lower() == "dark" else "Claro")
        self.ao_ocultar()

    def ao_ocultar(self):
        for campo in (self.senha_atual, self.nova_senha, self.confirmacao):
            campo.limpar()
        self.mensagem.configure(text="")

    def _alterar_tema(self, valor):
        try:
            self.janela.alternar_tema("dark" if valor == "Escuro" else "light")
        except (*ERROS_BANCO, OSError, ErroSeguranca, ErroPreferencias):
            self.seletor_tema.set("Escuro" if ctk.get_appearance_mode().lower() == "dark" else "Claro")
            self.mensagem.configure(text="Não foi possível salvar o tema. Confira as permissões da pasta dados.",
                                     text_color=COR_TEXTO_ERRO)

    def _alterar_senha(self, _evento=None):
        if self._salvando:
            return
        self._salvando = True
        self.botao_salvar.configure(state="disabled")
        for campo in (self.senha_atual, self.nova_senha, self.confirmacao):
            campo.ocultar()
        try:
            self.janela.preferencias.alterar_senha(
                self.senha_atual.get(), self.nova_senha.get(), self.confirmacao.get())
        except (ValueError, ErroSeguranca) as falha:   # recusas do serviço trazem o motivo
            self.mensagem.configure(text=str(falha), text_color=COR_TEXTO_ERRO)
        except (*ERROS_BANCO, OSError, ErroPreferencias):
            self.mensagem.configure(text="Não foi possível salvar a senha. Confira o espaço livre e "
                                        "as permissões da pasta dados.", text_color=COR_TEXTO_ERRO)
        else:
            self.ao_ocultar()
            self.mensagem.configure(text="Senha alterada. Cópias antigas continuam usando a senha da época em que foram criadas.",
                                     text_color=COR_TEXTO_SUCESSO)
        finally:
            self._salvando = False
            self.botao_salvar.configure(state="normal")
            if self.janela.preferencias.banco is None:
                self.after_idle(self.janela.bloquear)
