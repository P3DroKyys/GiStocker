"""Casos adicionais de regressão: nunca acessam dados de uso."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from contextlib import ExitStack
import csv
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from controllers.controllers import ControladorEstoque, ControladorRelatorios, ErroNegocio
from gerar_build import gerar_build
from models.models import BancoDados
from views.view_cadastro import ViewCadastro
from views.view_admin import ViewAdmin
from views.main_view import JanelaPrincipal


class Correcoes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.bd = BancoDados(self.base / 'teste.db', backup_automatico=False, permitir_legado=True)
        self.addCleanup(self.bd.fechar)
        self.c = ControladorEstoque(self.bd)
        self.r = ControladorRelatorios(self.bd)
        self.p = self.c.cadastrar_produto('Teste', config.MARCAS[0], config.CATEGORIAS[0], 30, 10, 10)

    def test_falha_publicacao_preserva_exportacao_anterior(self):
        pasta = self.base / 'csv'
        anteriores = self.r.exportar_csv(pasta)
        conteudos = [p.read_bytes() for p in anteriores]
        self.c.registrar_saida(self.p.id, 1)
        with patch('controllers.controllers.os.rename', side_effect=OSError('falha simulada')):
            with self.assertRaises(OSError):
                self.r.exportar_csv(pasta)
        self.assertEqual(list(pasta.iterdir()), [anteriores[0].parent])
        self.assertEqual([p.read_bytes() for p in anteriores], conteudos)

    def test_quatro_exportacoes_simultaneas(self):
        def exportar(_):
            bd = BancoDados(self.base / 'teste.db', backup_automatico=False, permitir_legado=True)
            try:
                return ControladorRelatorios(bd).exportar_csv(self.base / 'csv')
            finally:
                bd.fechar()
        with ThreadPoolExecutor(max_workers=4) as pool:
            pares = list(pool.map(exportar, range(4)))
        self.assertEqual(len({a.parent for a, _ in pares}), 4)
        for estoque, logs in pares:
            self.assertTrue(estoque.is_file() and logs.is_file())
            self.assertEqual(estoque.parent, logs.parent)
        self.assertFalse(any(p.name.startswith('.') for p in (self.base / 'csv').iterdir()))

    def test_falha_leitura_exportacao_libera_transacao(self):
        with patch.object(self.r.logs, 'listar', side_effect=sqlite3.OperationalError('falha')):
            with self.assertRaises(sqlite3.OperationalError):
                self.r.exportar_csv(self.base / 'csv')
        self.assertFalse(self.bd.conexao.in_transaction)
        self.assertEqual(self.c.registrar_saida(self.p.id, 1).estoque_novo, 9)

    def test_formula_neutralizada_sem_converter_numeros_negativos(self):
        nomes = ['=1+1', '+1+1', '-1+1', '@SUM(1)', '  =1+1', '\t=1+1', '\r=1+1']
        # Cadastro remove espaços externos; observação testa espaços/control chars internos ao CSV.
        for i, nome in enumerate(nomes):
            self.bd.executar('UPDATE Produtos SET nome=? WHERE id=?', (nome, self.p.id))
            self.c.ajustar_produto(self.p.id, 9 - i, motivo='=1+1')
            estoque, logs = self.r.exportar_csv(self.base / 'csv')
            with estoque.open(encoding='utf-8-sig', newline='') as f:
                self.assertEqual(next(csv.DictReader(f, delimiter=';'))['nome'], "'" + nome)
            with logs.open(encoding='utf-8-sig', newline='') as f:
                linha = next(csv.DictReader(f, delimiter=';'))
                self.assertEqual(linha['quantidade'], '-1')
                self.assertEqual(linha['observacao'], "'=1+1")

    def test_saldo_resultante_acima_limite_rejeitado_sem_gravar(self):
        self.c.ajustar_produto(self.p.id, config.LIMITE_QUANTIDADE)
        logs = self.c.listar_logs()
        with self.assertRaises(ErroNegocio):
            self.c.registrar_entrada(self.p.id, 1)
        self.assertEqual(self.c.obter_produto(self.p.id).estoque_atual, config.LIMITE_QUANTIDADE)
        self.assertEqual(self.c.listar_logs(), logs)

    def test_valores_extremos_recusados_tambem_em_entrada_e_ajuste(self):
        for valor in ('1e308', 'nan', 'inf', '-1', str(config.LIMITE_VALOR_UNITARIO + 1)):
            for acao in (lambda: self.c.registrar_entrada(self.p.id, 1, valor),
                         lambda: self.c.ajustar_produto(self.p.id, novo_custo=valor)):
                with self.subTest(valor=valor), self.assertRaises(ErroNegocio):
                    acao()
        self.assertEqual(self.c.obter_produto(self.p.id).estoque_atual, 10)
        self.assertEqual(len(self.c.listar_logs()), 1)

    def test_custo_legado_nao_arredonda_em_entrada_vazia(self):
        self.bd.executar('UPDATE Produtos SET custo_medio=? WHERE id=?', (10.123456, self.p.id))
        resultado = self.c.registrar_entrada(self.p.id, 2, '')
        self.assertEqual(resultado.custo_novo, 10.123456)
        self.assertEqual(self.c.desfazer_ultima_acao().produto.custo_medio, 10.123456)

    def test_kpi_legado_infinito_apresenta_erro_em_vez_de_valor(self):
        self.bd.executar('UPDATE Produtos SET custo_medio=? WHERE id=?', (1e308, self.p.id))
        with self.assertRaisesRegex(ValueError, 'não finitos'):
            self.r.obter_kpis()

    def test_graficos_e_rankings_somam_acima_de_int64(self):
        p = self.c.cadastrar_produto('Grande', config.MARCAS[0], config.CATEGORIAS[0], 1, 1, config.LIMITE_QUANTIDADE)
        for _ in range(2):
            self.c.registrar_saida(p.id, config.LIMITE_QUANTIDADE)
            self.c.registrar_entrada(p.id, config.LIMITE_QUANTIDADE)
        esperado = config.LIMITE_QUANTIDADE * 2
        self.assertEqual(self.r.curva_a()[0]['total_saidas'], esperado)
        self.assertEqual(self.r.ranking_marcas()[0][1], esperado)
        self.assertEqual(sum(self.r.movimentacao_ultimos_dias()[2]), esperado)

    def test_sugestoes_preservam_escolhas_manuais(self):
        view = Mock(_categoria_manual=True, _marca_manual=True)
        view.var_nome.get.return_value = ''
        ViewCadastro._ao_digitar_nome(view)
        view.combo_marca.set.assert_not_called()
        view.combo_categoria.set.assert_not_called()

    def test_sugestao_marca_limpa_quando_nome_nao_corresponde(self):
        view = Mock(_categoria_manual=False, _marca_manual=False)
        view.var_nome.get.return_value = 'Lily'
        ViewCadastro._ao_digitar_nome(view)
        view.combo_marca.set.assert_called_with('O Boticário')
        view.var_nome.get.return_value = 'Produto sem identificação'
        ViewCadastro._ao_digitar_nome(view)
        view.combo_marca.set.assert_called_with('')
        view.dica_marca.configure.assert_called_with(text='')

    def test_admin_envia_dono_esperado_ao_remover(self):
        view = Mock(produto_atual=self.p)
        with patch('views.view_admin.confirmar', return_value=True):
            self.assertTrue(ViewAdmin._desvincular_codigo(view, '96385074'))
        view.controlador.desvincular_codigo_barras.assert_called_once_with('96385074', produto_id_esperado=self.p.id)

    def test_callback_inesperado_avisa_e_registra(self):
        falha = RuntimeError('falha simulada')
        with patch('utils.erros.registrar_falha') as registro, patch('views.componentes.erro') as aviso:
            JanelaPrincipal.report_callback_exception(Mock(), RuntimeError, falha, None)
        registro.assert_called_once_with(falha)
        aviso.assert_called_once()

    def test_falha_gravacao_mostra_mensagem_no_cadastro_e_admin(self):
        with ExitStack() as stack:
            stack.enter_context(patch('utils.erros.registrar_falha'))
            aviso_cadastro = stack.enter_context(patch('views.view_cadastro.erro'))
            aviso_admin = stack.enter_context(patch('views.view_admin.erro'))
            modal = stack.enter_context(patch('views.view_admin.confirmar_com_senha', return_value=None))
            cadastro = Mock()
            cadastro.entrada_codigo.get.return_value = ''
            cadastro.controlador.cadastrar_produto.side_effect = sqlite3.OperationalError('full')
            ViewCadastro._salvar(cadastro)
            aviso_cadastro.assert_called_once()
            cadastro._limpar.assert_not_called()
            admin = Mock(produto_atual=self.p)
            admin._campos_alterados.return_value = {'novo_estoque': '9'}
            admin.controlador.editar_produto.side_effect = OSError('permissão')
            ViewAdmin._aplicar_ajuste(admin)
            # A falha chega ao modal de senha, que a exibe sem fechar
            # (verificar_edicao_exclusao.ModalSenha); a tela não recarrega.
            with self.assertRaises(OSError):
                modal.call_args.args[3]('senha')
            aviso_admin.assert_not_called()
            admin._carregar_produto.assert_not_called()

    def test_build_falha_preserva_distribuicao_anterior(self):
        banco = self.base / 'dist' / 'GestorEstoque' / 'dados' / 'estoque.db'
        banco.parent.mkdir(parents=True)
        banco.write_bytes(b'sentinela')
        with self.assertRaises(subprocess.CalledProcessError):
            gerar_build(self.base, executar=Mock(side_effect=subprocess.CalledProcessError(1, 'simulado')))
        self.assertEqual(banco.read_bytes(), b'sentinela')

    def test_build_sem_executavel_nao_informa_sucesso(self):
        with self.assertRaisesRegex(RuntimeError, 'sem produzir'):
            gerar_build(self.base, executar=Mock())


if __name__ == '__main__':
    unittest.main(verbosity=2)
