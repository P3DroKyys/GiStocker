"""Prévia isolada dos diálogos: não abre banco de dados."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import customtkinter as ctk
import config
from views.dialogos import mostrar_dialogo

ctk.set_default_color_theme(config.TEMA_COR)
ctk.set_appearance_mode('dark')
janela = ctk.CTk()
janela.title('GiStocker · PRÉVIA DOS DIÁLOGOS · sem banco')
janela.geometry('760x540')
ctk.CTkLabel(janela, text='Diálogos GiStocker', font=ctk.CTkFont(size=26, weight='bold')).pack(pady=(30, 10))
ctk.CTkLabel(janela, text='Prévia isolada · nenhum dado será gravado').pack(pady=(0, 15))
resultado = ctk.CTkLabel(janela, text='Escolha uma mensagem para visualizar.')


def abrir(tipo, longo=False):
    titulos = {'erro': 'Código de barras', 'sucesso': 'Produto cadastrado',
               'aviso': 'Estoque insuficiente', 'confirmacao': 'Confirmar ajuste'}
    mensagens = {'erro': 'O código GTIN deve conter somente números de 0 a 9, sem espaços internos ou símbolos.',
                'sucesso': 'Lily · Hidratante corporal cadastrado com sucesso.\n\nEstoque inicial: 12 unidades\nCódigo vinculado: 7891000100103',
                'aviso': 'Este produto possui 3 unidades disponíveis.\nConfira a quantidade antes de continuar.',
                'confirmacao': 'Deseja aplicar o ajuste de estoque deste produto?\n\nA alteração ficará registrada no histórico de movimentações.'}
    texto = mensagens[tipo] if not longo else '\n\n'.join(f'Produto fictício {i}: descrição detalhada para conferir a rolagem e a leitura da mensagem.' for i in range(25))
    valor = mostrar_dialogo(titulos[tipo], texto, tipo)
    resultado.configure(text=f'Retorno de {tipo}: {valor}')


for tipo, nome in [('erro', 'Erro'), ('sucesso', 'Sucesso'), ('aviso', 'Aviso'), ('confirmacao', 'Confirmação')]:
    ctk.CTkButton(janela, text=nome, height=38, width=250, command=lambda t=tipo: abrir(t)).pack(pady=5)
ctk.CTkButton(janela, text='Mensagem longa', height=38, width=250, command=lambda: abrir('erro', True)).pack(pady=5)
ctk.CTkSwitch(janela, text='Modo claro', command=lambda: ctk.set_appearance_mode('light' if ctk.get_appearance_mode() == 'Dark' else 'dark')).pack(pady=15)
resultado.pack(pady=10)
janela.mainloop()
