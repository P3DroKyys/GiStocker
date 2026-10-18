"""Modal único de confirmação por senha para ações administrativas sensíveis.

A senha nunca é validada na interface: ``acao(senha)`` envia o pedido ao
serviço, que confere a senha (com o mesmo intervalo crescente do login) antes
de gravar. Recusas e erros aparecem no próprio modal, que continua aberto.
"""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from utils.erros import ERROS_EXIBIVEIS, mensagem_falha
from views.acesso import CampoSenha
from views.componentes import COR_TEXTO_ERRO, COR_TEXTO_SUAVE
from views.dialogos import SECUNDARIO, DialogoGiStocker


class DialogoSenha(DialogoGiStocker):
    def __init__(self, parent, titulo: str, mensagem: str, acao: Callable[[str], object],
                 texto_botao: str = 'Confirmar'):
        self._acao = acao
        self._ocupado = False
        self.retorno = None
        super().__init__(parent, titulo, mensagem, 'confirmacao')
        self.aceitar.configure(text=texto_botao)

    def _montar_conteudo(self, corpo):
        ctk.CTkLabel(corpo, text='Senha atual do sistema', font=ctk.CTkFont(size=13, weight='bold'),
                     text_color=SECUNDARIO, anchor='w', corner_radius=0).grid(
                         row=3, column=0, columnspan=2, sticky='ew', padx=24)
        self.senha = CampoSenha(corpo)
        self.senha.grid(row=4, column=0, columnspan=2, sticky='ew', padx=24, pady=(4, 6))
        self.status = ctk.CTkLabel(corpo, text='', font=ctk.CTkFont(size=13), text_color=COR_TEXTO_ERRO,
                                   anchor='w', justify='left', wraplength=410, corner_radius=0)
        self.status.grid(row=5, column=0, columnspan=2, sticky='ew', padx=24, pady=(0, 18))
        for tecla in ('<Return>', '<KP_Enter>'):
            self.senha.entrada.bind(tecla, lambda _: self._fechar(True))

    def _foco_inicial(self):
        return self.senha.entrada

    def _mudar_foco(self, direcao):
        """Tab percorre o campo de senha e os botões."""
        ordem = [self.senha.entrada, *self._botoes]
        botao = self._botao_focado()
        atual = ordem.index(botao) if botao else 0
        ordem[(atual + direcao) % len(ordem)].focus_set()
        return 'break'

    def _fechar(self, resultado):
        if self._ocupado:
            return 'break'
        if not resultado:
            return super()._fechar(False)
        senha = self.senha.get()
        if not senha:
            self.status.configure(text='Informe a senha atual do sistema.', text_color=COR_TEXTO_ERRO)
            self.senha.entrada.focus_set()
            return 'break'
        self._definir_ocupado(True)
        try:
            self.retorno = self._acao(senha)
        except ERROS_EXIBIVEIS as falha:
            # Uma sessão expirada bloqueia a janela principal e destrói este modal.
            if self.winfo_exists():
                self._definir_ocupado(False)
                self.senha.limpar()
                self.status.configure(text=mensagem_falha(falha), text_color=COR_TEXTO_ERRO)
                self.senha.entrada.focus_set()
            return 'break'
        if self.winfo_exists():
            super()._fechar(True)
        return 'break'

    def _definir_ocupado(self, ocupado: bool) -> None:
        self._ocupado = ocupado
        estado = 'disabled' if ocupado else 'normal'
        for widget in (self.senha.entrada, self.senha.botao, *self._botoes):
            widget.configure(state=estado)
        if ocupado:
            self.status.configure(text='Verificando a senha…', text_color=COR_TEXTO_SUAVE)
            self.update_idletasks()


def confirmar_com_senha(origem, titulo: str, mensagem: str, acao: Callable[[str], object],
                        texto_botao: str = 'Confirmar'):
    """Devolve o retorno de ``acao(senha)`` após o sucesso, ou None se o usuário cancelar."""
    dialogo = DialogoSenha(origem.winfo_toplevel(), titulo, mensagem, acao, texto_botao)
    return dialogo.retorno if dialogo.mostrar() else None
