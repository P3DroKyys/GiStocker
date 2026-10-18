"""Auditoria isolada: não abre nem modifica os bancos de uso.

Execute da raiz do projeto: .venv/Scripts/python.exe -B auditoria/verificar.py
Os testes de defeitos são regressões das falhas encontradas e devem passar.
"""
import ast
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config
from controllers.controllers import ControladorEstoque, ControladorRelatorios, ErroNegocio
from models.models import BancoDados
from utils.texto import converter_para_float, converter_para_int, sugerir_categoria


class Auditoria(unittest.TestCase):
    def setUp(self):
        self.bd = BancoDados(':memory:', permitir_legado=True)
        self.addCleanup(self.bd.fechar)
        self.c = ControladorEstoque(self.bd)
        self.r = ControladorRelatorios(self.bd)

    def produto(self, **kwargs):
        dados = dict(nome='Colônia Lily', marca=config.MARCAS[0],
                     categoria=config.CATEGORIAS[0], preco_venda_base='30,00',
                     custo_inicial='10,00', quantidade_inicial=10,
                     codigos=['00123457', '96385074'])
        dados.update(kwargs)
        return self.c.cadastrar_produto(**dados)

    def test_sintaxe_fontes(self):
        fontes = list(ROOT.glob('*.py'))
        for pasta in ('controllers', 'models', 'utils', 'views'):
            fontes.extend((ROOT / pasta).glob('*.py'))
        for fonte in fontes:
            with self.subTest(arquivo=fonte.name):
                ast.parse(fonte.read_text(encoding='utf-8-sig'))

    def test_cadastro_multiplos_codigos(self):
        p = self.produto()
        for codigo in p.codigos:
            self.assertEqual(self.c.resolver_codigo_barras(codigo).id, p.id)
        self.assertEqual(len(self.c.listar_logs()), 1)
        self.assertEqual(self.c.listar_logs()[0]['observacao'], 'Cadastro inicial')

    def test_codigo_duplicado_nao_cria_produto(self):
        self.produto()
        with self.assertRaises(ErroNegocio):
            self.produto(nome='Outro')
        self.assertEqual(len(self.c.listar_produtos()), 1)

    def test_custo_medio_e_entrada_sem_custo(self):
        p = self.produto()
        resultado = self.c.registrar_entrada(p.id, 10, 20)
        self.assertEqual((resultado.estoque_novo, resultado.custo_novo), (20, 15))
        self.assertEqual(self.c.registrar_entrada(p.id, 2, '').custo_novo, 15)

    def test_saida_e_bloqueio_sem_estoque(self):
        p = self.produto()
        self.assertEqual(self.c.registrar_saida(p.id, 3).estoque_novo, 7)
        with self.assertRaises(ErroNegocio):
            self.c.registrar_saida(p.id, 8)
        self.assertEqual(self.c.obter_produto(p.id).estoque_atual, 7)
        self.assertEqual(len(self.c.listar_logs()), 2)

    def test_validacoes_comuns(self):
        p = self.produto()
        for valor in ('0', '-1', '1,5', 'abc'):
            with self.subTest(valor=valor), self.assertRaises(ErroNegocio):
                self.c.registrar_saida(p.id, valor)
        with self.assertRaises(ErroNegocio):
            self.c.registrar_entrada(p.id, 1, '-0,01')
        self.assertEqual(converter_para_float('R$ 1.234,56'), 1234.56)
        self.assertEqual(converter_para_int('1.000'), 1000)

    def test_desfazer_entrada_saida_ajuste(self):
        p = self.produto()
        for acao in (lambda: self.c.registrar_entrada(p.id, 3, 20),
                     lambda: self.c.registrar_saida(p.id, 2),
                     lambda: self.c.ajustar_produto(p.id, 8, 12, 'Inventário')):
            acao()
            resultado = self.c.desfazer_ultima_acao()
            self.assertTrue(resultado.log.cancelado)
            self.assertEqual((resultado.produto.estoque_atual, resultado.produto.custo_medio), (10, 10))

    def test_rollback_estoque_se_log_falhar(self):
        p = self.produto()
        with patch.object(self.c.logs, 'inserir', side_effect=RuntimeError('falha simulada')):
            with self.assertRaises(RuntimeError):
                self.c.registrar_entrada(p.id, 3, 20)
        self.assertEqual(self.c.obter_produto(p.id).estoque_atual, 10)
        self.assertEqual(len(self.c.listar_logs()), 1)

    def test_busca_sem_acento_e_ordem(self):
        p = self.produto()
        self.assertEqual(self.c.buscar_produtos('lily colonia')[0].id, p.id)
        self.assertEqual(self.c.buscar_produtos('00123457')[0].id, p.id)

    def test_vincular_desvincular(self):
        p = self.produto()
        self.c.vincular_codigo_barras('036000291452', p.id)
        self.assertEqual(self.c.resolver_codigo_barras('036000291452').id, p.id)
        self.c.desvincular_codigo_barras('036000291452')
        self.assertIsNone(self.c.resolver_codigo_barras('036000291452'))

    def test_kpis_rankings_cancelamento(self):
        p = self.produto()
        self.c.registrar_saida(p.id, 3)
        self.assertEqual(self.r.obter_kpis()['valor_investido'], 70)
        self.assertEqual(self.r.obter_kpis()['receita_potencial'], 210)
        self.assertEqual(self.r.ranking_marcas(), [(config.MARCAS[0], 3)])
        self.assertEqual(self.r.ranking_categorias(), [(config.CATEGORIAS[0], 3)])
        self.assertEqual(self.r.curva_a()[0]['total_saidas'], 3)
        self.assertEqual(sum(self.r.movimentacao_ultimos_dias()[2]), 3)
        self.c.desfazer_ultima_acao()
        self.assertEqual(self.r.curva_a(), [])
        self.assertEqual(sum(self.r.movimentacao_ultimos_dias()[2]), 0)

    def test_estoque_parado(self):
        p = self.produto()
        self.bd.executar("UPDATE Logs_Movimentacao SET data_hora='2020-01-01 00:00:00'")
        self.assertEqual(self.r.estoque_parado()[0]['id'], p.id)
        self.c.registrar_saida(p.id, 1)
        self.assertEqual(self.r.estoque_parado(), [])

    def test_exportacao_vazia_e_preenchida(self):
        with tempfile.TemporaryDirectory() as pasta:
            for preenchido in (False, True):
                if preenchido:
                    self.produto()
                estoque, logs = self.r.exportar_csv(pasta)
                self.assertTrue(estoque.read_bytes().startswith(b'\xef\xbb\xbf'))
                self.assertIn('codigos_barras', estoque.read_text(encoding='utf-8-sig'))
                self.assertIn('cancelado', logs.read_text(encoding='utf-8-sig'))
                if preenchido:
                    self.assertIn('00123457;96385074', estoque.read_text(encoding='utf-8-sig'))

    def test_defeito_infinito_deveria_ser_rejeitado(self):
        with self.assertRaises(ErroNegocio):
            self.produto(custo_inicial='inf')

    def test_defeito_nan_deveria_gerar_erro_negocio(self):
        with self.assertRaises(ErroNegocio):
            self.produto(custo_inicial='nan')

    def test_defeito_tonico_capilar(self):
        self.assertEqual(sugerir_categoria('Tônico capilar'), 'Cabelos')

    def test_defeito_exportacoes_no_mesmo_minuto(self):
        with tempfile.TemporaryDirectory() as pasta:
            with patch('controllers.controllers.datetime') as relogio:
                relogio.now.return_value = datetime(2026, 9, 30, 12, 0)
                primeira = self.r.exportar_csv(pasta)
                self.produto()
                segunda = self.r.exportar_csv(pasta)
            self.assertNotEqual(primeira, segunda)

    def test_defeito_admin_arredonda_custo_ao_ajustar_quantidade(self):
        p = self.produto(custo_inicial='10,1234')
        # Exercita o preenchimento real do campo, sem criar janela.
        from types import SimpleNamespace
        from unittest.mock import Mock
        from views.view_admin import ViewAdmin
        campo = Mock()
        tela = SimpleNamespace(controlador=self.c, rotulo_produto=Mock(), entrada_estoque=Mock(),
                               entrada_custo=campo, lista_codigos=Mock(),
                               botao_ajuste=Mock(), botao_vincular=Mock(), entrada_nome=Mock(),
                               entrada_preco=Mock(), combo_marca=Mock(), combo_categoria=Mock(),
                               _texto_decimal=ViewAdmin._texto_decimal)
        ViewAdmin._carregar_produto(tela, p.id)
        campo_custo = campo.insert.call_args.args[1]
        self.c.ajustar_produto(p.id, 11, campo_custo)
        self.assertEqual(self.c.obter_produto(p.id).custo_medio, 10.1234)

    def test_defeito_duas_instancias_perdem_movimentacao(self):
        with tempfile.TemporaryDirectory() as pasta:
            a = BancoDados(Path(pasta) / 'teste.db', permitir_legado=True)
            b = BancoDados(Path(pasta) / 'teste.db', permitir_legado=True)
            try:
                ca, cb = ControladorEstoque(a), ControladorEstoque(b)
                p = ca.cadastrar_produto('Teste', config.MARCAS[0], config.CATEGORIAS[0], 30, 10, 10)
                transacao_original = a.transacao

                @contextmanager
                def intercalar():
                    # B confirma entre a leitura do estoque por A e o BEGIN de A.
                    cb.registrar_entrada(p.id, 2, 10)
                    with transacao_original() as conexao:
                        yield conexao

                with patch.object(a, 'transacao', intercalar):
                    ca.registrar_entrada(p.id, 3, 10)
                self.assertEqual(ca.obter_produto(p.id).estoque_atual, 15)
            finally:
                b.fechar()
                a.fechar()


if __name__ == '__main__':
    unittest.main(verbosity=2)
