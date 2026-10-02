"""Integração com widgets Tk reais, janela oculta e bancos descartáveis.

Não acessa nem controla janelas da instalação da loja. Executar separadamente
da suíte sem interface: python -B auditoria/smoke_interface_upgrade.py.
"""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import customtkinter as ctk
import config
from controllers.controllers import ControladorEstoque, ControladorRelatorios
from models.models import BancoDados
from models.seguranca import Cofre
from verificar_seguranca import SENHA, NOVA, criar_preferencias_legadas, cadastrar
from views.main_view import JanelaPrincipal


class InterfaceReal(unittest.TestCase):
    def test_bloqueio_durante_mensagem_de_cadastro_nao_repete_nem_falha(self):
        with tempfile.TemporaryDirectory() as pasta:
            cofre = Cofre(Path(pasta) / 'dados' / 'estoque.db')
            cofre.abrir('', SENHA, SENHA)
            ctk.set_default_color_theme(config.TEMA_COR)
            janela = JanelaPrincipal(cofre)
            janela.withdraw()
            try:
                janela._liberar_acesso()
                janela.mostrar_view('cadastro')
                tela = janela.views['cadastro']
                tela.var_nome.set('Produto de teste do bloqueio')
                tela.combo_marca.set(config.MARCAS[0])
                tela.combo_categoria.set(config.CATEGORIAS[0])
                with patch('views.view_cadastro.informar', side_effect=lambda *_: janela.bloquear()):
                    tela._salvar()
                self.assertFalse(janela._desbloqueado)
                self.assertIsNone(cofre.banco)
                janela.tela_acesso.campo_senha.entrada.insert(0, SENHA)
                janela.tela_acesso._entrar()
                self.assertEqual(len(janela.controlador_estoque.listar_produtos()), 1)
            finally:
                janela._fechar()

    def test_primeira_criacao_usa_nova_senha_sem_padrao(self):
        with tempfile.TemporaryDirectory() as pasta:
            cofre = Cofre(Path(pasta) / 'dados' / 'estoque.db')
            ctk.set_default_color_theme(config.TEMA_COR)
            janela = JanelaPrincipal(cofre)
            janela.withdraw()
            try:
                tela = janela.tela_acesso
                self.assertEqual(tela.modo, 'novo')
                tela.nova_senha.entrada.insert(0, SENHA)
                tela.confirmacao.entrada.insert(0, SENHA)
                tela._entrar()
                self.assertTrue(janela._desbloqueado)
                self.assertFalse(cofre.legado.exists())
                self.assertTrue(cofre.verificar_senha(SENHA))
            finally:
                janela._fechar()

    def test_migracao_interrompida_retoma_na_tela_com_nova_senha(self):
        with tempfile.TemporaryDirectory() as pasta:
            cofre = Cofre(Path(pasta) / 'dados' / 'estoque.db')
            cofre.caminho.parent.mkdir()
            bd = BancoDados(cofre.caminho, permitir_legado=True, backup_automatico=False)
            cadastrar(bd)
            bd.fechar()
            criar_preferencias_legadas(cofre.legado)
            ctk.set_default_color_theme(config.TEMA_COR)
            janela = JanelaPrincipal(cofre)
            janela.withdraw()
            try:
                tela = janela.tela_acesso
                self.assertEqual(tela.modo, 'legado')
                for campo, senha in ((tela.campo_senha, '1234'), (tela.nova_senha, SENHA), (tela.confirmacao, SENHA)):
                    campo.entrada.insert(0, senha)
                with patch('models.seguranca.proteger_arquivo', side_effect=OSError('falha simulada')):
                    tela._entrar()
                self.assertFalse(janela._desbloqueado)
                tela.after_cancel(tela._espera)
                tela._reativar()
                tela = janela.tela_acesso
                self.assertEqual(tela.modo, 'protegido')
                self.assertIn('NOVA senha', tela.mensagem.cget('text'))
                tela.campo_senha.entrada.insert(0, SENHA)
                tela._entrar()
                self.assertTrue(janela._desbloqueado)
                self.assertEqual(len(janela.controlador_estoque.listar_produtos()), 1)
                self.assertFalse(cofre.legado.exists())
            finally:
                janela._fechar()

    def test_sessao_completa_isolada(self):
        with tempfile.TemporaryDirectory(prefix='gistocker_teste_interface_') as pasta:
            preferencias = Cofre(Path(pasta) / 'dados' / 'estoque.db')
            preferencias.abrir('', SENHA, SENHA)
            preferencias.fechar()
            ctk.set_default_color_theme(config.TEMA_COR)
            ctk.set_appearance_mode('dark')
            janela = JanelaPrincipal(preferencias)
            janela.withdraw()
            falhas = []
            janela.report_callback_exception = lambda tipo, valor, tb: falhas.append(valor)
            try:
                # Não há sidebar, telas ou atalhos de navegação antes do acesso.
                janela.mostrar_view('admin')
                self.assertEqual(janela.views, {})
                self.assertEqual(janela.bind('<F5>'), '')
                self.assertEqual(janela.tela_acesso.campo_senha.entrada.cget('show'), '•')
                janela.tela_acesso.campo_senha.entrada.insert(0, 'incorreta')
                janela.tela_acesso._entrar()
                self.assertFalse(janela._desbloqueado)
                self.assertEqual(janela.tela_acesso.campo_senha.get(), '')
                janela.tela_acesso.after_cancel(janela.tela_acesso._espera)
                janela.tela_acesso._reativar()
                janela.tela_acesso.campo_senha.entrada.insert(0, SENHA)
                janela.tela_acesso._entrar()
                self.assertTrue(janela._desbloqueado)
                self.assertTrue(janela.bind('<F5>'))
                self.assertFalse(janela.tela_acesso.winfo_exists())

                estoque = janela.controlador_estoque
                banco = preferencias.banco
                janela.mostrar_view('cadastro')
                cadastro = janela.views['cadastro']
                cadastro.var_nome.set('Teste sem preços')
                cadastro.combo_marca.set(config.MARCAS[0])
                cadastro.combo_categoria.set(config.CATEGORIAS[0])
                cadastro.entrada_quantidade.insert(0, '12')
                cadastro.entrada_codigo.insert(0, '96385074')
                cadastro._adicionar_codigo()
                with patch('views.view_cadastro.informar') as sucesso:
                    cadastro._salvar()
                    sucesso.assert_called_once()
                produto = estoque.resolver_codigo_barras('96385074')
                self.assertEqual((produto.estoque_atual, produto.custo_medio, produto.preco_venda_base), (12, 0, 0))

                janela.mostrar_view('admin')
                admin = janela.views['admin']
                self.assertFalse(hasattr(admin, 'entrada_pin'))
                self.assertFalse(hasattr(admin, 'entrada_motivo'))
                admin._abrir_produto_catalogo(produto.id)
                admin.entrada_estoque.delete(0, 'end')
                admin.entrada_estoque.insert(0, '15')
                with patch('views.view_admin.confirmar', return_value=True), patch('views.view_admin.informar'):
                    admin._aplicar_ajuste()
                self.assertEqual(estoque.obter_produto(produto.id).estoque_atual, 15)
                self.assertEqual(estoque.listar_logs()[0]['observacao'], 'Ajuste manual (Admin)')

                janela.mostrar_view('configuracoes')
                painel = janela.views['configuracoes']
                for campo, texto in ((painel.senha_atual, SENHA), (painel.nova_senha, NOVA),
                                     (painel.confirmacao, NOVA)):
                    campo.entrada.insert(0, texto)
                    self.assertEqual(campo.entrada.cget('show'), '•')
                    campo.alternar_visibilidade()
                    self.assertEqual(campo.entrada.cget('show'), '')
                painel._alterar_senha()
                self.assertTrue(preferencias.verificar_senha(NOVA))
                self.assertFalse(preferencias.verificar_senha(SENHA))
                for campo in (painel.senha_atual, painel.nova_senha, painel.confirmacao):
                    self.assertEqual(campo.get(), '')
                    self.assertEqual(campo.entrada.cget('show'), '•')
                painel._alterar_tema('Claro')
                self.assertEqual(preferencias.obter_tema(), 'light')
                self.assertEqual(ctk.get_appearance_mode(), 'Light')
                painel.senha_atual.entrada.insert(0, 'não deve ficar no campo')
                painel.senha_atual.alternar_visibilidade()
                janela.mostrar_view('dashboard')
                self.assertEqual(painel.senha_atual.get(), '')
                self.assertEqual(painel.senha_atual.entrada.cget('show'), '•')
                dashboard = janela.views['dashboard']
                self.assertEqual(dashboard.kpi_produtos.rotulo_valor.cget('text'), '1')
                self.assertEqual(dashboard.kpi_itens.rotulo_valor.cget('text'), '15 un.')
                janela.mostrar_view('relatorios')
                janela.mostrar_view('operacao')
                janela.update_idletasks()
                # Bloqueio destrói telas, encerra a conexão e exige a nova senha.
                janela.bloquear()
                self.assertIsNone(preferencias.banco)
                self.assertEqual(janela.views, {})
                self.assertIsNone(janela.controlador_estoque)
                self.assertEqual(janela.bind('<F5>'), '')
                janela.tela_acesso.campo_senha.entrada.insert(0, NOVA)
                janela.tela_acesso._entrar()
                self.assertTrue(janela._desbloqueado)
                janela.mostrar_view('dashboard')
                self.assertEqual(janela.views['dashboard'].kpi_itens.rotulo_valor.cget('text'), '15 un.')
                # Dez minutos já não bloqueiam; noventa minutos bloqueiam.
                janela._ultimo_uso -= 601
                janela.after_cancel(janela._inatividade)
                janela._conferir_inatividade()
                self.assertTrue(janela._desbloqueado)
                janela._ultimo_uso -= 4800
                janela.after_cancel(janela._inatividade)
                janela._conferir_inatividade()
                self.assertFalse(janela._desbloqueado)
                self.assertIsNone(preferencias.banco)
                janela.update()
                self.assertEqual(falhas, [])
            finally:
                janela._fechar()
            self.assertTrue(Cofre(Path(pasta) / 'dados' / 'estoque.db').verificar_senha(NOVA))
            self.assertEqual(Cofre(Path(pasta) / 'dados' / 'estoque.db').obter_tema(), 'light')


if __name__ == '__main__':
    unittest.main(verbosity=2)
