"""Campo de senha reutilizável e tela de desbloqueio da aplicação."""
from models.seguranca import ERROS_BANCO, ErroSeguranca, validar_nova_senha

import customtkinter as ctk
from PIL import Image

import config
from models.preferencias import ErroPreferencias
from views.componentes import COR_TEXTO_ERRO, COR_TEXTO_SUAVE


class CampoSenha(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.entrada = ctk.CTkEntry(self, height=42, show="•")
        self.entrada.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.botao = ctk.CTkButton(
            self, text="Mostrar", width=76, height=42, fg_color="transparent",
            border_width=1, text_color=("#475467", "#AFBBCD"),
            hover_color=("#DDE5F0", "#293342"), command=self.alternar_visibilidade)
        self.botao.grid(row=0, column=1)

    def get(self):
        return self.entrada.get()

    def alternar_visibilidade(self):
        visivel = self.entrada.cget("show") == ""
        self.entrada.configure(show="•" if visivel else "")
        self.botao.configure(text="Mostrar" if visivel else "Ocultar")
        self.entrada.focus_set()

    def ocultar(self):
        self.entrada.configure(show="•")
        self.botao.configure(text="Mostrar")

    def limpar(self):
        self.entrada.delete(0, "end")
        self.ocultar()


class TelaAcesso(ctk.CTkFrame):
    def __init__(self, master, preferencias, ao_desbloquear):
        super().__init__(master, fg_color="transparent")
        self.preferencias = preferencias
        self.ao_desbloquear = ao_desbloquear
        self._ocupado = False
        self._espera = None
        self._tentativas = 0
        try:
            self.modo = preferencias.modo
        except (ErroSeguranca, OSError):
            self.modo = "protegido"
        cartao = ctk.CTkFrame(self, width=440, corner_radius=20)
        cartao.place(relx=0.5, rely=0.48, anchor="center")
        with Image.open(config.CAMINHO_LOGO) as arquivo:
            imagem = arquivo.copy()
        self.logo = ctk.CTkImage(light_image=imagem, dark_image=imagem,
                                size=(258, round(258 * imagem.height / imagem.width)))
        ctk.CTkLabel(cartao, text="", image=self.logo, corner_radius=0, padx=0
                     ).pack(padx=76, pady=(30, 22))
        titulo = ("Bem-vindo ao GiStocker" if self.modo == "novo" else
                  "Proteger seus dados" if self.modo == "legado" else "Bem-vindo de volta")
        ctk.CTkLabel(cartao, text=titulo, font=ctk.CTkFont(size=24, weight="bold")
                     ).pack(padx=30)
        descricao = (
            "Vamos preparar seu acesso. Crie uma senha para desbloquear o sistema e proteger os dados do seu estoque."
            if self.modo == "novo" else
            "Digite sua senha para abrir os dados protegidos."
            if self.modo == "protegido" else
            f"Crie uma senha com pelo menos {config.MINIMO_CARACTERES_SENHA} caracteres para proteger seus dados."
        )
        ctk.CTkLabel(cartao, text=descricao, wraplength=350, justify="center",
                     text_color=COR_TEXTO_SUAVE).pack(padx=30, pady=(4, 18))
        if self.modo == "novo":
            aviso = ctk.CTkFrame(
                cartao, corner_radius=12, border_width=1,
                fg_color=("#F3F7FC", "#222B37"),
                border_color=("#DCE5F0", "#354253"))
            aviso.pack(fill="x", padx=30, pady=(0, 14))
            ctk.CTkLabel(
                aviso, text="Sobre sua senha",
                anchor="w", justify="left",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=("#34445A", "#D9E4F2")
            ).pack(fill="x", padx=14, pady=(11, 3))
            ctk.CTkLabel(
                aviso,
                text=(f"Use pelo menos {config.MINIMO_CARACTERES_SENHA} caracteres. Ela protege o banco de dados e será "
                      "necessária sempre que você abrir o GiStocker. Se esquecê-la, não será possível recuperar "
                      "o acesso aos seus produtos e movimentações. Guarde-a em um local seguro."),
                anchor="w", justify="left", wraplength=350,
                text_color=("#526174", "#AFBBCD")
            ).pack(fill="x", padx=14, pady=(0, 11))
        if self.modo != "novo":
            ctk.CTkLabel(cartao, text="Senha atual" if self.modo == "legado" else "Senha de acesso", anchor="w").pack(fill="x", padx=30)
        self.campo_senha = CampoSenha(cartao)
        self.campo_senha.pack(fill="x", padx=30, pady=(6, 0))
        self.nova_senha = self.confirmacao = None
        if self.modo in ("novo", "legado"):
            if self.modo == "novo":
                self.campo_senha.pack_forget()
            ctk.CTkLabel(cartao, text="Nova frase de senha", anchor="w").pack(fill="x", padx=30, pady=(10, 4))
            self.nova_senha = CampoSenha(cartao)
            self.nova_senha.pack(fill="x", padx=30)
            ctk.CTkLabel(cartao, text="Confirme a nova senha", anchor="w").pack(fill="x", padx=30, pady=(10, 4))
            self.confirmacao = CampoSenha(cartao)
            self.confirmacao.pack(fill="x", padx=30)
        for tecla in ("<Return>", "<KP_Enter>"):
            self.campo_senha.entrada.bind(tecla, self._entrar)
            if self.nova_senha:
                # Enter na nova senha leva à confirmação; na confirmação, envia.
                self.nova_senha.entrada.bind(tecla, self._avancar)
                self.confirmacao.entrada.bind(tecla, self._entrar)
        self.mensagem = ctk.CTkLabel(cartao, text="", wraplength=350,
                                     text_color=COR_TEXTO_ERRO)
        self.mensagem.pack(fill="x", padx=30, pady=(8, 4))
        self.botao_entrar = ctk.CTkButton(cartao, text="Proteger e abrir" if self.modo != "protegido" else "Desbloquear", height=44, command=self._entrar)
        self.botao_entrar.pack(fill="x", padx=30, pady=(0, 30))

    def _avancar(self, _evento=None):
        self.confirmacao.entrada.focus_set()
        return "break"

    def _entrar(self, _evento=None):
        if self._ocupado:
            return
        if self.modo in ('novo', 'legado'):
            try:
                validar_nova_senha(self.nova_senha.get(), self.confirmacao.get())
            except ValueError as falha:
                self.mensagem.configure(text=str(falha))
                return
        self._ocupado = True
        self.botao_entrar.configure(state="disabled")
        for campo in (self.campo_senha, self.nova_senha, self.confirmacao):
            if campo:
                campo.ocultar()
        self.mensagem.configure(text="Verificando e preparando os dados. Aguarde…")
        self.update_idletasks()
        try:
            self.preferencias.abrir(
                self.campo_senha.get(),
                self.nova_senha.get() if self.nova_senha else None,
                self.confirmacao.get() if self.confirmacao else None)
        except (ValueError, ErroSeguranca, ErroPreferencias) as falha:
            self.mensagem.configure(text=str(falha))
            self._tentativas += 1
            self._espera = self.after(min(30000, 1000 * 2 ** min(self._tentativas - 1, 5)), self._reativar)
            return
        except (*ERROS_BANCO, OSError):
            self.mensagem.configure(text="Não foi possível abrir os dados. Confira o espaço e as permissões da pasta. "
                                         "Feche outras versões do programa antes de migrar.")
            self._espera = self.after(1000, self._reativar)
            return
        finally:
            for campo in (self.campo_senha, self.nova_senha, self.confirmacao):
                if campo:
                    campo.limpar()
        self.mensagem.configure(text="")
        self.ao_desbloquear()

    def _reativar(self):
        self._espera = None
        self._ocupado = False
        try:
            mudou = self.modo != "protegido" and self.preferencias.modo == "protegido"
        except (ErroSeguranca, OSError):
            mudou = False
        if mudou:
            self.master.recarregar_acesso()
            return
        self.botao_entrar.configure(state="normal")
        (self.nova_senha if self.modo == "novo" else self.campo_senha).entrada.focus_set()

    def destroy(self):
        if self._espera is not None:
            self.after_cancel(self._espera)
        for campo in (self.campo_senha, self.nova_senha, self.confirmacao):
            if campo:
                campo.limpar()
        super().destroy()
