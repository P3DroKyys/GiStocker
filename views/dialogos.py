"""Diálogos modais do GiStocker, com aparência clara/escura e ícones próprios."""
from __future__ import annotations

import sys
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageDraw
import config

FUNDO = ('#F5F7FB', '#191E27')
CARTAO = ('#FFFFFF', '#222A36')
TEXTO = ('#202632', '#EFF2F7')
SECUNDARIO = ('#526174', '#B1BDCD')
BORDA = ('#DCE3ED', '#354153')
ESTILOS = {
    'erro': ('Não foi possível continuar', ('#B93448', '#FF8796'), ('#FDECF0', '#422B38')),
    'aviso': ('Atenção', ('#956000', '#F5C66D'), ('#FFF4D9', '#403729')),
    'sucesso': ('Tudo certo', ('#087D68', '#60D6B9'), ('#E4F6EF', '#213E3A')),
    'confirmacao': ('Confirme para continuar', ('#0875D1', '#82C5FF'), ('#E5F1FD', '#233C56')),
}


def imagem_simbolo(tipo: str, modo: int) -> Image.Image:
    """Traços vetoriais próprios, renderizados em 4x para telas de alta densidade."""
    _, cores, fundos = ESTILOS[tipo]
    imagem = Image.new('RGBA', (224, 224), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(imagem)
    cor = cores[modo]
    desenho.rounded_rectangle((0, 0, 223, 223), radius=68, fill=fundos[modo])
    if tipo == 'aviso':
        desenho.line([(112, 52), (175, 164), (49, 164), (112, 52)], fill=cor, width=10, joint='curve')
        desenho.line((112, 93, 112, 125), fill=cor, width=10)
        desenho.ellipse((107, 140, 117, 150), fill=cor)
    elif tipo == 'sucesso':
        desenho.ellipse((48, 48, 176, 176), outline=cor, width=9)
        desenho.line([(78, 112), (102, 137), (148, 87)], fill=cor, width=11, joint='curve')
    elif tipo == 'erro':
        desenho.rounded_rectangle((52, 52, 172, 172), radius=36, outline=cor, width=9)
        desenho.line((89, 89, 135, 135), fill=cor, width=11)
        desenho.line((135, 89, 89, 135), fill=cor, width=11)
    else:
        # Balão com três pontos: decisão pendente, sem símbolo de erro do Windows.
        desenho.rounded_rectangle((45, 55, 179, 151), radius=30, outline=cor, width=9)
        desenho.line([(82, 148), (72, 176), (112, 151)], fill=cor, width=9, joint='curve')
        for x in (80, 112, 144):
            desenho.ellipse((x - 6, 97, x + 6, 109), fill=cor)
    return imagem


class DialogoGiStocker(ctk.CTkToplevel):
    def __init__(self, parent, titulo: str, mensagem: str, tipo: str):
        super().__init__(parent, fg_color=FUNDO)
        self.withdraw()
        self.resultado = False
        self.tipo = tipo
        self._parent = parent
        self._foco_anterior = parent.focus_get()
        self._grab_anterior = parent.grab_current()
        self.title(titulo)
        # CTkToplevel colore também a barra de título conforme a aparência ativa.
        if sys.platform == 'win32' and config.CAMINHO_ICONE.is_file():
            self.iconbitmap(str(config.CAMINHO_ICONE))
        if parent.winfo_viewable():
            self.transient(parent)
        self.resizable(False, False)
        self.protocol('WM_DELETE_WINDOW', lambda: self._fechar(False))
        self.bind('<Escape>', lambda _: self._fechar(False))
        self.bind('<Return>', self._enter)
        self.bind('<KP_Enter>', self._enter)
        self.grid_columnconfigure(0, weight=1)

        corpo = ctk.CTkFrame(self, fg_color=CARTAO, corner_radius=18,
                            border_width=1, border_color=BORDA)
        corpo.grid(row=0, column=0, sticky='nsew', padx=20, pady=(20, 14))
        corpo.grid_columnconfigure(1, weight=1)
        self.simbolo = ctk.CTkImage(light_image=imagem_simbolo(tipo, 0),
                                    dark_image=imagem_simbolo(tipo, 1), size=(56, 56))
        ctk.CTkLabel(corpo, text='', image=self.simbolo, width=56, height=56,
                     corner_radius=0).grid(row=0, column=0, rowspan=2, padx=(22, 16), pady=(24, 14), sticky='n')
        ctk.CTkLabel(corpo, text=ESTILOS[tipo][0], font=ctk.CTkFont(size=11, weight='bold'),
                     text_color=ESTILOS[tipo][1], anchor='w', corner_radius=0).grid(
                         row=0, column=1, sticky='ew', padx=(0, 22), pady=(24, 0))
        ctk.CTkLabel(corpo, text=titulo, font=ctk.CTkFont(size=21, weight='bold'),
                     text_color=TEXTO, anchor='w', justify='left', wraplength=320, corner_radius=0).grid(
                         row=1, column=1, sticky='ew', padx=(0, 22), pady=(0, 16))
        # Mensagens comuns se ajustam ao texto; textos extensos têm rolagem e cópia.
        if len(mensagem) > 480 or mensagem.count('\n') > 7:
            texto = ctk.CTkTextbox(corpo, height=210, fg_color='transparent', text_color=SECUNDARIO,
                                  font=ctk.CTkFont(size=14), wrap='word', border_width=0)
            texto.insert('1.0', mensagem)
            texto.configure(state='disabled')
        else:
            texto = ctk.CTkLabel(corpo, text=mensagem, font=ctk.CTkFont(size=14),
                                text_color=SECUNDARIO, justify='left', anchor='w', wraplength=410, corner_radius=0)
        texto.grid(row=2, column=0, columnspan=2, sticky='ew', padx=24, pady=(0, 24))

        rodape = ctk.CTkFrame(self, fg_color='transparent')
        rodape.grid(row=1, column=0, sticky='ew', padx=24, pady=(0, 22))
        rodape.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(rodape, text='GiStocker', font=ctk.CTkFont(size=11),
                     text_color=SECUNDARIO).grid(row=0, column=0, sticky='w')
        self.cancelar = None
        if tipo == 'confirmacao':
            self.cancelar = ctk.CTkButton(rodape, text='Cancelar', width=112, height=40,
                                         fg_color='transparent', border_width=1, border_color=BORDA,
                                         hover_color=('#E8EDF5', '#303C4D'), text_color=TEXTO,
                                         command=lambda: self._fechar(False))
            self.cancelar.grid(row=0, column=1, padx=(0, 10))
        self.aceitar = ctk.CTkButton(rodape, text='Confirmar' if self.cancelar else 'Entendi',
                                    width=120, height=40, corner_radius=10,
                                    fg_color=('#0875D1', '#227DC4'), hover_color=('#0664B4', '#3191DB'),
                                    text_color='#FFFFFF', font=ctk.CTkFont(size=14, weight='bold'),
                                    command=lambda: self._fechar(True))
        self.aceitar.grid(row=0, column=2)
        self._botoes = [b for b in (self.cancelar, self.aceitar) if b is not None]
        for botao in self._botoes:
            botao.bind('<space>', lambda _, b=botao: b.invoke())
            botao.bind('<FocusIn>', lambda _, b=botao: b.configure(border_width=2, border_color=('#075B9F', '#A5D7FF')))
            botao.bind('<FocusOut>', lambda _, b=botao: b.configure(border_width=1 if b is self.cancelar else 0, border_color=BORDA))
        self.bind('<Tab>', lambda _: self._mudar_foco(1))
        self.bind('<Shift-Tab>', lambda _: self._mudar_foco(-1))
        self.geometry('520x300')
        self.update_idletasks()
        # Medidas solicitadas dos widgets incluem a escala configurada pelo Windows.
        altura = int(self._reverse_window_scaling(self.winfo_reqheight()))
        self._altura_dialogo = max(250, altura)
        self.geometry(f'520x{self._altura_dialogo}')

    def _botao_focado(self):
        foco = self.focus_get()
        return next((b for b in self._botoes if foco is not None
                     and (foco == b or str(foco).startswith(str(b) + '.'))), None)

    def _enter(self, _evento=None):
        (self._botao_focado() or self.cancelar or self.aceitar).invoke()
        return 'break'

    def _mudar_foco(self, direcao):
        atual = self._botao_focado()
        indice = self._botoes.index(atual) if atual else -1
        self._botoes[(indice + direcao) % len(self._botoes)].focus_set()
        return 'break'

    def _fechar(self, resultado):
        self.resultado = bool(resultado)
        self.destroy()
        return 'break'

    def mostrar(self) -> bool:
        try:
            self.update_idletasks()
            # winfo_width/height podem ser 1 enquanto a janela está oculta.
            largura = round(self._apply_window_scaling(520))
            altura = round(self._apply_window_scaling(self._altura_dialogo))
            if self._parent.winfo_viewable():
                x = self._parent.winfo_rootx() + (self._parent.winfo_width() - largura) // 2
                y = self._parent.winfo_rooty() + (self._parent.winfo_height() - altura) // 2
            else:
                x = (self.winfo_screenwidth() - largura) // 2
                y = (self.winfo_screenheight() - altura) // 2
            self.geometry(f'{x:+d}{y:+d}')
            self.deiconify()
            self.wait_visibility()
            self.grab_set()
            self.lift()
            (self.cancelar or self.aceitar).focus_set()
            self.wait_window()
            return self.resultado
        finally:
            try:
                if self.winfo_exists():
                    self.destroy()
            except tk.TclError:
                pass
            for widget, acao in ((self._grab_anterior, 'grab_set'), (self._foco_anterior, 'focus_set')):
                try:
                    if widget is not None and widget.winfo_exists():
                        getattr(widget, acao)()
                except tk.TclError:
                    pass


def mostrar_dialogo(titulo: str, mensagem: str, tipo: str) -> bool:
    parent = tk._default_root
    temporaria = parent is None
    if temporaria:
        parent = ctk.CTk()
        parent.withdraw()
    else:
        foco = parent.focus_get()
        if foco is not None:
            parent = foco.winfo_toplevel()
    try:
        return DialogoGiStocker(parent, titulo, mensagem, tipo).mostrar()
    finally:
        if temporaria:
            parent.destroy()
