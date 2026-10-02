"""Integração da pesquisa em widgets próprios, ocultos, com dados descartáveis."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import customtkinter as ctk
import config
from models.seguranca import Cofre
from views.main_view import JanelaPrincipal
from verificar_seguranca import SENHA


class InterfaceBusca(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cofre = Cofre(Path(self.temp.name) / 'dados' / 'estoque.db')
        self.cofre.abrir('', SENHA, SENHA)
        ctk.set_default_color_theme(config.TEMA_COR)
        self.janela = JanelaPrincipal(self.cofre)
        self.janela.withdraw()
        self.falhas = []
        self.janela.report_callback_exception = lambda _t, valor, _tb: self.falhas.append(valor)
        self.janela._liberar_acesso()
        self.c = self.janela.controlador_estoque
        self.p = self.c.cadastrar_produto('Colônia Malbec', config.MARCAS[0], config.CATEGORIAS[0],
                                         quantidade_inicial=4, codigos=['96385074'])
        self.c.cadastrar_produto('Refil Hidratante Lily', config.MARCAS[0], config.CATEGORIAS[0])
        self.janela.mostrar_view('admin')
        self.tela = self.janela.views['admin']
        self.tela.abas.set('Ajustes e códigos')
        self.tela._ao_trocar_aba()

    def tearDown(self):
        self.janela._fechar()
        self.temp.cleanup()
        self.assertEqual(self.falhas, [])

    def esperar(self):
        fim = ctk.BooleanVar(master=self.janela, value=False)
        self.janela.after(300, lambda: fim.set(True))
        self.janela.wait_variable(fim)

    def test_digitacao_colagem_limpeza_e_selecao_obsoleta(self):
        with patch.object(self.c, 'pesquisar_produtos', wraps=self.c.pesquisar_produtos) as pesquisar:
            self.tela.var_busca.set('mal')
            self.tela.var_busca.set('malb')
            self.tela.var_busca.set('malbec')
            self.esperar()
            self.assertEqual(pesquisar.call_count, 1)
        self.assertEqual(self.tela.produto_atual.id, self.p.id)
        self.tela.entrada_busca.delete(0, 'end')
        self.tela.entrada_busca.insert(0, 'zzzzzzzz')
        self.assertIsNone(self.tela.produto_atual)  # antes mesmo do debounce
        self.assertEqual(self.tela.botao_ajuste.cget('state'), 'disabled')
        self.esperar()
        self.assertEqual(self.tela.tabela_busca.get_children(), ())
        self.tela.var_busca.set('')
        self.esperar()
        self.assertEqual(len(self.tela.tabela_busca.get_children()), 2)
        self.assertIsNone(self.tela.produto_atual)

    def test_sugestao_exige_escolha_e_scanner_resolve_exato(self):
        self.tela.var_busca.set('malbce')
        self.esperar()
        self.assertIn('Opções próximas', self.tela.status_busca.cget('text'))
        self.assertIsNone(self.tela.produto_atual)
        self.tela.tabela_busca.selection_set(str(self.p.id))
        self.janela.update()
        self.assertEqual(self.tela.produto_atual.id, self.p.id)
        self.tela.var_busca.set('96385074')
        self.tela._buscar()  # mesmo caminho de Enter enviado pelo leitor
        self.assertIsNone(self.tela._busca_agendada)
        self.assertEqual(self.tela.produto_atual.id, self.p.id)

    def test_paginacao_permite_acessar_todos_resultados(self):
        with self.c.bd.transacao():
            self.c.bd.conexao.executemany('INSERT INTO Produtos(nome,marca,categoria) VALUES (?,?,?)',
                                         [(f'Produto {i:04}', config.MARCAS[0], config.CATEGORIAS[0]) for i in range(501)])
        self.tela.var_busca.set('produto')
        self.esperar()
        self.assertEqual(len(self.tela.tabela_busca.get_children()), 200)
        self.assertIn('200 de 501', self.tela.status_busca.cget('text'))
        self.tela._mostrar_mais()
        self.tela._mostrar_mais()
        self.assertEqual(len(self.tela.tabela_busca.get_children()), 501)

    def test_busca_pendente_cancelada_ao_sair_e_bloquear(self):
        self.tela.var_busca.set('malbec')
        self.janela.mostrar_view('operacao')
        self.assertIsNone(self.tela._busca_agendada)
        self.janela.mostrar_view('admin')
        self.assertEqual(self.tela.produto_atual.id, self.p.id)
        self.tela.var_busca.set('lily')
        self.janela.bloquear()
        self.esperar()
        self.assertIsNone(self.cofre.banco)

    def test_catalogo_abre_ajustes_com_filtro_id(self):
        self.tela._abrir_produto_catalogo(self.p.id)
        self.assertEqual(self.tela.var_busca.get(), f'#{self.p.id}')
        self.assertEqual(self.tela.produto_atual.id, self.p.id)
        self.assertEqual(len(self.tela.tabela_busca.get_children()), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
