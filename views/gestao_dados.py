"""Apresentação da gestão de dados; arquivos e banco ficam nos módulos dedicados."""
import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

import config
from gestao.arquivos import SaidaAtomica
from gestao.planilha import modelo
from servico.transferencia import Transferencia
from views.acesso import CampoSenha
from views.componentes import COR_TEXTO_ERRO, COR_TEXTO_SUAVE, erro, informar
from views.tarefas import cancelar_tarefas

AVISO_EXPORTACAO = 'Atenção: O arquivo exportado conterá todos os seus dados sem criptografia. Guarde-o em local seguro.'
TITULOS = {'exportar': 'Exportar backup do sistema', 'restaurar': 'Restaurar backup do sistema',
           'importar': 'Importar produtos via planilha'}
DESCRICOES = {
    'exportar': AVISO_EXPORTACAO,
    'restaurar': 'Todos os produtos e o histórico atuais serão substituídos pelo backup. '
                 'Sua senha atual será mantida. Antes da substituição, uma cópia criptografada será criada automaticamente.',
    'importar': 'Os códigos GTIN identificam os produtos. Quantidades serão SOMADAS ao estoque. '
                'Nome, marca e categoria serão atualizados. Preços vazios preservam os atuais. '
                'Linhas inválidas serão ignoradas e listadas ao final.',
}


def destino_seguro(caminho, extensao):
    p = Path(caminho).resolve()
    if not p.name.lower().endswith(extensao):
        raise ValueError(f'O nome do arquivo deve terminar em {extensao}.')
    # Impede que um seletor de arquivos sobrescreva o envelope/chaves da instalação.
    if p.is_relative_to(config.DIRETORIO_DADOS.resolve()) or p.is_relative_to(config.DIRETORIO_RECURSOS.resolve()):
        raise ValueError('Escolha uma pasta pessoal fora dos dados internos do programa.')
    return p


class RotuloResponsivo(ctk.CTkLabel):
    """Quebra pela caixa externa, nunca pela largura variável do texto interno.

    CTkLabel.bind encaminha Configure ao texto E ao canvas. Usá-lo aqui cria
    realimentação de geometria. O bind Tk abaixo preserva o callback do CTk e
    observa apenas o Frame externo, cuja largura é atribuída pelo layout.
    """
    def __init__(self, master, texto, **kwargs):
        self._redimensionamento = None
        super().__init__(master, text=texto, width=1, anchor='w', justify='left', wraplength=400, **kwargs)
        tk.Misc.bind(self, '<Configure>', self._agendar_quebra, add='+')

    def _agendar_quebra(self, evento):
        if evento.widget is self and self._redimensionamento is None:
            self._redimensionamento = self.after_idle(self._ajustar_quebra)

    def _ajustar_quebra(self):
        self._redimensionamento = None
        largura = max(40, round(self.winfo_width() / self._get_widget_scaling() - 8))
        if abs(largura - self.cget('wraplength')) >= 1:
            self.configure(wraplength=largura)

    def destroy(self):
        if self._redimensionamento is not None:
            self.after_cancel(self._redimensionamento)
            self._redimensionamento = None
        super().destroy()


def rotulo(master, texto, **kwargs):
    label = RotuloResponsivo(master, texto, **kwargs)
    label.pack(fill='x', padx=22, pady=(4, 8))
    return label


class PainelGestao(ctk.CTkFrame):
    def __init__(self, master, janela):
        super().__init__(master, corner_radius=14)
        self.janela = janela
        self.pack(fill='x', padx=4, pady=(0, 14))
        rotulo(self, 'Gestão de dados', font=ctk.CTkFont(size=17, weight='bold'))
        rotulo(self, 'Backup completo do banco principal e importação de produtos. '
                    'Encerre o laboratório de integrações antes de usar estas operações.', text_color=COR_TEXTO_SUAVE)
        for tipo in ('exportar', 'restaurar'):
            ctk.CTkButton(self, text=TITULOS[tipo], height=40, command=lambda t=tipo: self.abrir(t),
                          state='normal' if hasattr(janela.preferencias, 'chamar') else 'disabled'
                          ).pack(fill='x', padx=22, pady=5)
        rotulo(self, 'Planilha de produtos · CSV UTF-8', font=ctk.CTkFont(size=14, weight='bold'))
        rotulo(self, 'Use o modelo com uma linha por produto. No Excel, importe a coluna codigo como Texto '
                    'para preservar os zeros à esquerda. Salve como CSV UTF-8. Quantidade zero permite '
                    'atualizar o cadastro sem adicionar estoque.', text_color=COR_TEXTO_SUAVE)
        ctk.CTkButton(self, text='Baixar planilha modelo', height=40, command=self.baixar_modelo
                      ).pack(fill='x', padx=22, pady=5)
        ctk.CTkButton(self, text=TITULOS['importar'], height=40, command=lambda: self.abrir('importar'),
                      state='normal' if hasattr(janela.preferencias, 'chamar') else 'disabled'
                      ).pack(fill='x', padx=22, pady=(5, 22))

    def baixar_modelo(self):
        caminho = self._selecionar(filedialog.asksaveasfilename, title='Salvar modelo de produtos',
                                               initialfile='modelo_produtos.csv', defaultextension='.csv',
                                               filetypes=[('Planilha CSV UTF-8', '*.csv')])
        if not caminho:
            return
        try:
            with SaidaAtomica(destino_seguro(caminho, '.csv')) as arquivo:
                arquivo.write(modelo())
        except (OSError, ValueError) as exc:
            erro('Planilha modelo', str(exc))
        else:
            informar('Planilha modelo', 'Modelo salvo. Preencha as colunas mantendo os códigos como texto.')

    def abrir(self, tipo):
        if self.janela.__dict__.get('_gestao_em_andamento', False):
            return
        if tipo == 'exportar':
            caminho = self._selecionar(filedialog.asksaveasfilename, title=TITULOS[tipo],
                initialfile=f'GiStocker_{datetime.now():%Y%m%d_%H%M%S}.gsdados.json',
                defaultextension='.gsdados.json', filetypes=[('Backup GiStocker JSON', '*.gsdados.json')])
        else:
            caminho = self._selecionar(filedialog.askopenfilename, title=TITULOS[tipo],
                filetypes=[('Backup GiStocker JSON', '*.json')] if tipo == 'restaurar' else [('Planilha CSV UTF-8', '*.csv')])
        if not caminho:
            return
        try:
            if tipo == 'exportar':
                caminho = str(destino_seguro(caminho, '.gsdados.json'))
            DialogoGestao(self.janela, tipo, caminho)
        except (OSError, ValueError) as exc:
            erro('Gestão de dados', str(exc))

    def _selecionar(self, seletor, **opcoes):
        if self.janela.__dict__.get('_gestao_em_andamento', False):
            return ''
        self.janela._gestao_em_andamento = True
        try:
            caminho = seletor(parent=self, **opcoes)
        finally:
            self.janela._gestao_em_andamento = False
        if self.janela.__dict__.pop('_bloqueio_pendente', False):
            self.janela.bloquear()   # a inatividade venceu com o seletor aberto; descarta a escolha
            return ''
        self.janela._ultimo_uso = time.monotonic()
        return caminho


class DialogoGestao(ctk.CTkToplevel):
    def __init__(self, janela, tipo, caminho):
        super().__init__(janela)
        self.withdraw()
        self.janela, self.tipo, self.caminho = janela, tipo, caminho
        self.executando = self.sucesso = False
        self.fila = queue.Queue()
        self.relatorio = ''
        self.title(TITULOS[tipo])
        escala = self._get_window_scaling()
        altura = max(360, min(680, int((self.winfo_screenheight() - 110) / escala)))
        largura = max(440, min(660, int((self.winfo_screenwidth() - 60) / escala)))
        self.geometry(f'{largura}x{altura}')
        self.minsize(min(520, largura), min(440, altura))
        if janela.winfo_viewable():
            self.transient(janela)
        self.protocol('WM_DELETE_WINDOW', self.fechar)
        if sys.platform == 'win32':
            self.after(220, lambda: self.iconbitmap(str(config.CAMINHO_ICONE)))
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        area = ctk.CTkScrollableFrame(self, fg_color='transparent')
        area.grid(row=0, column=0, sticky='nsew', padx=8, pady=12)
        rotulo(area, TITULOS[tipo], font=ctk.CTkFont(size=22, weight='bold'))
        rotulo(area, Path(caminho).name, text_color=COR_TEXTO_SUAVE)
        rotulo(area, DESCRICOES[tipo])
        if tipo == 'importar':
            rotulo(area, 'Com quantidade maior que zero, o custo informado entra no cálculo do custo médio. '
                        'Com quantidade zero, ele substitui o custo. Os demais produtos não serão apagados.',
                   text_color=COR_TEXTO_SUAVE)
        rotulo(area, 'Confirme a senha atual do sistema')
        self.senha = CampoSenha(area)
        self.senha.pack(fill='x', padx=22, pady=4)
        confirmacao = ctk.CTkFrame(area, fg_color='transparent')
        confirmacao.pack(fill='x', padx=22, pady=14)
        self.aceite = ctk.CTkCheckBox(confirmacao, text='', width=24)
        self.aceite.pack(side='left', anchor='n')
        texto_aceite = RotuloResponsivo(confirmacao, 'Entendo que os dados atuais serão substituídos.'
                                        if tipo == 'restaurar' else 'Li e entendi as informações acima.')
        texto_aceite.pack(side='left', fill='x', expand=True, padx=(10, 0))
        texto_aceite.bind('<Button-1>', lambda _: self.aceite.toggle() if self.aceite.cget('state') == 'normal' else None)
        self.status = rotulo(area, 'Aguardando confirmação', text_color=COR_TEXTO_SUAVE)
        self.progresso = ctk.CTkProgressBar(area, mode='determinate')
        self.progresso.pack(fill='x', padx=22, pady=8)
        self.progresso.set(0)
        self.resumo = rotulo(area, '')
        self.detalhes = ctk.CTkTextbox(area, height=150, wrap='word')
        self.detalhes.configure(state='disabled')
        self.salvar_log = ctk.CTkButton(area, text='Salvar relatório da importação', command=self.salvar_relatorio)
        rodape = ctk.CTkFrame(self, fg_color='transparent')
        rodape.grid(row=1, column=0, sticky='ew', padx=30, pady=(0, 22))
        self.botao_fechar = ctk.CTkButton(rodape, text='Cancelar', width=130, command=self.fechar)
        self.botao_fechar.pack(side='left')
        self.botao_executar = ctk.CTkButton(rodape, text='Confirmar e continuar', command=self.iniciar)
        self.botao_executar.pack(side='right')
        janela._gestao_em_andamento = True
        janela._dialogo_gestao = self
        self.deiconify()
        self.after(100, self._focar)

    def _focar(self):
        self.grab_set()
        self.senha.entrada.focus_set()

    def iniciar(self):
        if self.executando or self.sucesso:
            return
        if not self.aceite.get() or not self.senha.get():
            self.resumo.configure(text='Confirme o aviso e informe sua senha.', text_color=COR_TEXTO_ERRO)
            return
        transferencia = Transferencia(self.janela.preferencias)
        senha = self.senha.get()
        self.senha.limpar()
        self.senha.entrada.configure(state='disabled')
        self.senha.botao.configure(state='disabled')
        self.executando = True
        self.resumo.configure(text='Aguarde a conclusão antes de fechar o programa.', text_color=COR_TEXTO_SUAVE)
        for botao in (self.botao_executar, self.botao_fechar, self.aceite):
            botao.configure(state='disabled')
        self.status.configure(text='Autorizando e preparando…')
        self.progresso.set(0)
        try:
            threading.Thread(target=self._trabalhar, args=(transferencia, senha), daemon=True).start()
        except RuntimeError:
            self.fila.put(('erro', 'Não foi possível iniciar o processamento. Tente novamente.'))
        self.after(100, self._acompanhar)

    def _trabalhar(self, transferencia, senha):
        try:
            resultado = transferencia.executar(self.tipo, self.caminho, senha,
                lambda etapa, feitos, total: self.fila.put(('progresso', (etapa, feitos, total))))
            self.fila.put(('sucesso', resultado))
        except Exception as exc:
            if not isinstance(exc, ValueError):   # ValueError traz a recusa esperada do agente
                from utils.erros import registrar_falha
                registrar_falha(exc)
            self.fila.put(('erro', str(exc) if isinstance(exc, (OSError, ValueError)) else
                           'Falha ao concluir. Confira o histórico antes de repetir; para retomar, use o mesmo arquivo.'))
        finally:
            senha = None

    def _acompanhar(self):
        ultimo_progresso = None
        for _ in range(100):
            try:
                evento, dados = self.fila.get_nowait()
            except queue.Empty:
                break
            if evento == 'progresso':
                ultimo_progresso = dados
            else:
                self.executando = False
                self.botao_fechar.configure(state='normal', text='Concluir' if evento == 'sucesso' else 'Fechar')
                if evento == 'erro':
                    self.status.configure(text='Operação não concluída')
                    self.resumo.configure(text=dados, text_color=COR_TEXTO_ERRO)
                    self.senha.entrada.configure(state='normal')
                    self.senha.botao.configure(state='normal')
                    self.aceite.configure(state='normal')
                    self.botao_executar.configure(state='normal', text='Tentar novamente')
                    self.senha.entrada.focus_set()
                else:
                    self.sucesso = True
                    self.progresso.set(1)
                    self.status.configure(text='Operação concluída · 100%')
                    self._resultado(dados)
        if self.executando:
            if ultimo_progresso:
                etapa, feitos, total = ultimo_progresso
                proporcao = min(1, feitos / total) if total else 1
                self.progresso.set(proporcao)
                self.status.configure(text=f'{etapa} · {proporcao:.0%} ({feitos:,}/{total:,})')
            self.after(100, self._acompanhar)

    def _resultado(self, dados):
        if self.tipo == 'exportar':
            texto = 'Backup salvo com todos os registros do banco principal.\n' + AVISO_EXPORTACAO
        elif self.tipo == 'restaurar':
            texto = (f"Backup restaurado: {dados['produtos']} produtos e {dados['historico']} movimentações.\n"
                     f"Cópia anterior criptografada: {dados['snapshot']}")
        else:
            texto = (f"Linhas lidas: {dados['total']}. Novos produtos: {dados['novos']}. "
                     f"Atualizados: {dados['atualizados']}. Ignorados: {len(dados['erros'])}.")
            self.relatorio = texto + '\n\n' + ('\n'.join(
                f"Linha {e['linha']}: {e['motivo']}" for e in dados['erros']) or 'Nenhuma linha com erro.')
            self.detalhes.pack(fill='x', padx=22, pady=8)
            self.detalhes.configure(state='normal')
            self.detalhes.insert('1.0', self.relatorio)
            self.detalhes.configure(state='disabled')
            self.salvar_log.pack(fill='x', padx=22, pady=8)
        if self.tipo != 'exportar':
            texto += '\n\nAo concluir, desbloqueie novamente para recarregar todas as telas com os dados atualizados.'
        self.resumo.configure(text=texto)

    def salvar_relatorio(self):
        caminho = filedialog.asksaveasfilename(parent=self, title='Salvar relatório',
            initialfile='resultado.importacao.txt', defaultextension='.txt', filetypes=[('Relatório de texto', '*.txt')])
        if caminho:
            try:
                with SaidaAtomica(destino_seguro(caminho, '.txt')) as arquivo:
                    arquivo.write(self.relatorio.encode('utf-8'))
            except (OSError, ValueError):
                self.resumo.configure(text='Não foi possível salvar o relatório. Escolha outra pasta.', text_color=COR_TEXTO_ERRO)

    def fechar(self):
        if self.executando:
            return
        self.grab_release()
        self.janela._gestao_em_andamento = False
        self.janela._dialogo_gestao = None
        self.janela._ultimo_uso = time.monotonic()
        cancelar_tarefas(self)
        self.destroy()
        if self.sucesso and self.tipo != 'exportar':
            self.janela.bloquear()
