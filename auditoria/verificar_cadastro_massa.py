"""Cadastro em massa a partir da tela de Cadastro, reutilizando a importação de Configurações.

Execute: .venv/Scripts/python.exe -m unittest auditoria.verificar_cadastro_massa
Pastas temporárias e agente descartável; nunca abre os dados da instalação.
"""
from pathlib import Path
import sys
import tempfile
import time
import traceback
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import load_workbook

import config
from auditoria import verificar_ipc
from auditoria.verificar_gestao_dados import gtin, linha
from gestao import planilha
from views.gestao_dados import AcoesGestao, DialogoCadastroMassa, PainelGestao
from views.view_cadastro import ViewCadastro

SENHA = 'senha-cadastro-massa'


def raiz_tk(teste, servico=True):
    import customtkinter as ctk
    from views.tarefas import cancelar_tarefas
    raiz = ctk.CTk()
    raiz.withdraw()
    raiz.preferencias = Mock(spec=['chamar'] if servico else ['modo'])
    teste.addCleanup(lambda: (cancelar_tarefas(raiz, todas=True), raiz.destroy()))
    return raiz


class ModalCadastroMassa(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = Path(self.tmp.name)

    def dialogo(self, servico=True):
        dialogo = DialogoCadastroMassa(raiz_tk(self, servico))
        self.addCleanup(lambda: dialogo.winfo_exists() and dialogo.destroy())
        return dialogo

    def test_mesma_rota_de_configuracoes(self):
        # Um único conjunto de ações: nenhuma cópia do fluxo de planilha.
        for classe in (PainelGestao, DialogoCadastroMassa):
            self.assertTrue(issubclass(classe, AcoesGestao))
            for metodo in ('baixar_modelo', 'abrir', '_selecionar'):
                self.assertIs(getattr(classe, metodo), getattr(AcoesGestao, metodo))

    def test_botao_do_cadastro_abre_o_modal(self):
        tela = Mock()
        with patch('views.view_cadastro.DialogoCadastroMassa') as classe:
            ViewCadastro._cadastrar_em_massa(tela)
        classe.assert_called_once_with(tela.janela)
        classe.return_value.mostrar.assert_called_once()

    def test_download_grava_o_modelo_xlsx(self):
        dialogo = self.dialogo()
        destino = self.pasta / 'modelo_produtos.xlsx'
        with patch('views.gestao_dados.filedialog.asksaveasfilename', return_value=str(destino)) as salvar, \
                patch('views.gestao_dados.informar') as informar:
            dialogo.botao_modelo.invoke()
        self.assertIs(salvar.call_args.kwargs['parent'], dialogo)
        informar.assert_called_once()
        livro = load_workbook(destino)
        self.assertEqual(livro.sheetnames, ['Produtos', 'Listas', 'Instruções'])
        self.assertEqual([c.value.rstrip(' *') for c in livro['Produtos'][1]], list(planilha.TITULOS))
        self.assertTrue(dialogo.winfo_exists())   # baixar o modelo não fecha o modal

    def test_anexar_entrega_o_arquivo_ao_dialogo_de_importacao(self):
        dialogo = self.dialogo()
        arquivo = self.pasta / 'produtos.xlsx'
        with patch('views.gestao_dados.filedialog.askopenfilename', return_value=str(arquivo)) as abrir, \
                patch('views.gestao_dados.DialogoGestao') as importacao:
            dialogo.aceitar.invoke()
        self.assertIn('*.xlsx', abrir.call_args.kwargs['filetypes'][0][1])
        importacao.assert_called_once_with(dialogo.janela, 'importar', str(arquivo))
        self.assertTrue(dialogo.resultado)
        self.assertFalse(dialogo.winfo_exists())

    def test_anexo_cancelado_mantem_o_modal(self):
        dialogo = self.dialogo()
        with patch('views.gestao_dados.filedialog.askopenfilename', return_value=''), \
                patch('views.gestao_dados.DialogoGestao') as importacao:
            dialogo.aceitar.invoke()
        importacao.assert_not_called()
        self.assertTrue(dialogo.winfo_exists())

    def test_fechar_nao_importa(self):
        dialogo = self.dialogo()
        with patch('views.gestao_dados.filedialog.askopenfilename') as abrir:
            dialogo.cancelar.invoke()
        abrir.assert_not_called()
        self.assertFalse(dialogo.winfo_exists())
        self.assertFalse(dialogo.resultado)

    def test_sem_servico_so_permite_baixar_o_modelo(self):
        dialogo = self.dialogo(servico=False)
        self.assertEqual(dialogo.aceitar.cget('state'), 'disabled')
        self.assertEqual(dialogo.botao_modelo.cget('state'), 'normal')


class FluxoCompleto(unittest.TestCase):
    """Janela real e agente Windows real: modal → modelo → anexo → senha → banco."""
    setUp = verificar_ipc.PipeWindows.setUp
    tearDown = verificar_ipc.PipeWindows.tearDown

    def entrar(self, janela, primeira_vez=False):
        tela = janela.tela_acesso
        if primeira_vez:
            tela.nova_senha.entrada.insert(0, SENHA)
            tela.confirmacao.entrada.insert(0, SENHA)
        else:
            tela.campo_senha.entrada.insert(0, SENHA)
        tela._entrar()

    def test_planilha_do_modal_cadastra_no_banco_sem_afetar_cadastro_unitario(self):
        import customtkinter as ctk
        from views.main_view import JanelaPrincipal
        ctk.set_default_color_theme(config.TEMA_COR)
        janela = JanelaPrincipal(self.cliente)
        janela.withdraw()
        falhas = []
        janela.report_callback_exception = lambda tipo, valor, tb: falhas.append(
            ''.join(traceback.format_exception(tipo, valor, tb)))
        importacao = None
        try:
            self.entrar(janela, primeira_vez=True)
            janela.mostrar_view('cadastro')
            dialogo = DialogoCadastroMassa(janela)
            modelo = Path(self.tmp.name) / 'modelo_produtos.xlsx'
            with patch('views.gestao_dados.filedialog.asksaveasfilename', return_value=str(modelo)), \
                    patch('views.gestao_dados.informar'):
                dialogo.botao_modelo.invoke()
            # O usuário preenche o modelo baixado: um produto válido, um com quantidade vazia e um inválido.
            livro = load_workbook(modelo)
            for valores in (linha(1, qtd='4', preco='59,90'), linha(2, qtd=''),
                            [gtin(3), 'Produto 3', 'Marca inexistente', config.CATEGORIAS[0], '1', '', '']):
                livro[planilha.ABA_PRODUTOS].append(valores)
            livro.save(modelo)
            with patch('views.gestao_dados.filedialog.askopenfilename', return_value=str(modelo)):
                dialogo.aceitar.invoke()
            self.assertFalse(dialogo.winfo_exists())
            importacao = janela._dialogo_gestao
            self.assertEqual((importacao.tipo, importacao.caminho), ('importar', str(modelo)))
            importacao.senha.entrada.insert(0, SENHA)
            importacao.aceite.select()
            importacao.iniciar()
            limite = time.monotonic() + 30
            while importacao.executando and time.monotonic() < limite:
                janela.update()
                time.sleep(.02)
            self.assertTrue(importacao.sucesso, importacao.resumo.cget('text'))
            self.assertIn('Novos produtos: 2', importacao.relatorio)
            self.assertIn('Linha 4:', importacao.relatorio)
            importacao.fechar()
            importacao = None
            # Mesmo comportamento de Configurações: bloqueia para recarregar as telas.
            self.assertFalse(janela._desbloqueado)
            self.entrar(janela)
            estoque = janela.controlador_estoque
            produtos = {p.nome: p for p in estoque.listar_produtos()}
            self.assertEqual(set(produtos), {'Produto 1', 'Produto 2'})
            self.assertEqual((produtos['Produto 1'].estoque_atual, produtos['Produto 1'].preco_venda_base,
                              produtos['Produto 1'].codigos), (4, 59.9, [gtin(1)]))
            self.assertEqual(produtos['Produto 2'].estoque_atual, 0)
            # O cadastro unitário segue funcionando na mesma sessão.
            janela.mostrar_view('cadastro')
            tela = janela.views['cadastro']
            tela.var_nome.set('Produto unitário')
            tela.combo_marca.set(config.MARCAS[1])
            tela.combo_categoria.set(config.CATEGORIAS[1])
            tela.entrada_quantidade.insert(0, '2')
            with patch('views.view_cadastro.informar'):
                tela._salvar()
            unitario = next(p for p in estoque.listar_produtos() if p.nome == 'Produto unitário')
            self.assertEqual((unitario.marca, unitario.estoque_atual), (config.MARCAS[1], 2))
            self.assertFalse(falhas, falhas[0] if falhas else '')
        finally:
            if importacao:
                importacao.executando = False
                importacao.fechar()
            janela._gestao_em_andamento = False
            janela._fechar()


if __name__ == '__main__':
    unittest.main(verbosity=2)
