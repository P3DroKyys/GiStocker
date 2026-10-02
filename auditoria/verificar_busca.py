"""Pesquisa em dados fictícios: relevância, tolerância e invalidação do índice."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controllers.controllers import ControladorEstoque
from models.models import BancoDados, Produto
from utils.busca import IndiceProdutos
from verificar_seguranca import SENHA
import config


def produto(pid, nome, marca='Boticário', categoria='Corpo', codigos=()):
    return Produto(pid, nome, marca, categoria, codigos=list(codigos))


class BuscaInteligente(unittest.TestCase):
    def setUp(self):
        self.indice = IndiceProdutos([
            produto(1, 'Lily', codigos=['036000291452']),
            produto(2, 'Refil Hidratante Lily'),
            produto(3, 'Colônia Malbec 200ml', categoria='Perfume', codigos=['96385074']),
            produto(4, 'Creme 50 ml', marca='Lily'),
            produto(5, 'Creme 100% natural'),
            produto(6, 'Linha_A'),
            produto(7, "Leave-in L’Occitane"),
        ])

    def ids(self, consulta):
        return [p.id for p in self.indice.pesquisar(consulta).produtos]

    def test_exato_e_nome_tem_prioridade_sobre_marca(self):
        self.assertEqual(self.ids('lily'), [1, 2, 4])
        self.assertFalse(self.indice.pesquisar('lily').aproximada)

    def test_acentos_caixa_espacos(self):
        self.assertEqual(self.ids('  COLONIA   malbec  '), [3])

    def test_palavras_em_ordem_diferente_e_campos_diferentes(self):
        self.assertEqual(self.ids('lily refil boticario'), [2])

    def test_prefixo_e_trecho(self):
        self.assertEqual(self.ids('lil ref'), [2])
        self.assertEqual(self.ids('dratan'), [2])

    def test_palavras_de_ligacao(self):
        self.assertEqual(self.ids('refil de lily'), [2])

    def test_substituicao_insercao_remocao_transposicao(self):
        for consulta in ('malbex', 'malbecc', 'malbc', 'malbce', 'hidratnte'):
            with self.subTest(consulta=consulta):
                r = self.indice.pesquisar(consulta)
                self.assertEqual([p.id for p in r.produtos], [2] if consulta == 'hidratnte' else [3])
                self.assertTrue(r.aproximada)

    def test_todos_termos_precisam_corresponder(self):
        self.assertEqual(self.ids('lily zzzzzzzz'), [])
        self.assertEqual(self.ids('malbce boticario'), [3])

    def test_aproximacao_so_quando_nao_ha_resultado_direto(self):
        indice = IndiceProdutos([produto(1, 'Lily'), produto(2, 'Lili')])
        self.assertEqual([p.id for p in indice.pesquisar('lily').produtos], [1])

    def test_termos_curtos_nao_recebem_correcao(self):
        self.assertEqual(self.ids('kit'), [])

    def test_codigo_exato_preserva_zeros(self):
        self.assertEqual(self.ids('036000291452'), [1])

    def test_codigo_com_digito_errado_nao_sugere_outro(self):
        self.assertEqual(self.ids('036000291453'), [])
        self.assertEqual(self.ids('96385075'), [])

    def test_codigo_parcial(self):
        self.assertEqual(self.ids('0360'), [1])

    def test_id_explicito_nao_confunde_numero_com_volume(self):
        self.assertEqual(self.ids('#2'), [2])
        self.assertEqual(self.ids('#987'), [])
        indice = IndiceProdutos([produto(200, 'Lily'), produto(2, 'Malbec 200 ml')])
        self.assertEqual([p.id for p in indice.pesquisar('200').produtos], [2])
        self.assertEqual([p.id for p in indice.pesquisar('#200').produtos], [200])

    def test_numeros_e_unidades_nao_sao_corrigidos(self):
        self.assertEqual(self.ids('malbec 200 ml'), [3])
        self.assertEqual(self.ids('malbec 201 ml'), [])
        self.assertEqual(self.ids('50'), [4])

    def test_percentual_e_sublinhado_sao_literais(self):
        self.assertEqual(self.ids('%'), [5])
        self.assertEqual(self.ids('_'), [6])
        self.assertEqual(self.ids("' OR 1=1 --"), [])

    def test_hifen_apostrofo(self):
        self.assertEqual(self.ids('leave in l occitane'), [7])

    def test_vazio_lista_todos_e_pontuacao_nao_lista_tudo(self):
        self.assertEqual(len(self.ids('')), 7)
        self.assertEqual(self.ids('!!!'), [])

    def test_limites_nao_truncam_consulta_silenciosamente(self):
        self.assertTrue(self.indice.pesquisar('x' * 257).aviso)
        self.assertTrue(self.indice.pesquisar(' '.join('palavra' + chr(97+i) for i in range(17))).aviso)

    def test_todos_resultados_disponiveis_e_ordem_deterministica(self):
        indice = IndiceProdutos([produto(i, 'Creme') for i in reversed(range(1, 502))])
        self.assertEqual([p.id for p in indice.pesquisar('creme').produtos], list(range(1, 502)))


class IndiceBancoProtegido(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.caminho = Path(self.temp.name) / 'estoque.db'
        self.bd = BancoDados(self.caminho, senha=SENHA, criar=True, backup_automatico=False)
        self.addCleanup(self.bd.fechar)
        self.c = ControladorEstoque(self.bd)
        self.p = self.c.cadastrar_produto('Lily', config.MARCAS[0], config.CATEGORIAS[0], quantidade_inicial=4)

    def test_cache_reutilizado_e_atualizado_apos_movimento(self):
        self.c.pesquisar_produtos('lily')
        indice = self.bd._indice_pesquisa
        self.c.pesquisar_produtos('lil')
        self.assertIs(self.bd._indice_pesquisa, indice)
        self.c.registrar_saida(self.p.id, 1)
        self.assertEqual(self.c.pesquisar_produtos('lily').produtos[0].estoque_atual, 3)
        self.assertIsNot(self.bd._indice_pesquisa, indice)

    def test_codigo_vinculado_e_desvinculado(self):
        self.assertEqual(self.c.pesquisar_produtos('96385074').produtos, [])
        self.c.vincular_codigo_barras('96385074', self.p.id)
        self.assertEqual(self.c.pesquisar_produtos('96385074').produtos[0].id, self.p.id)
        self.c.desvincular_codigo_barras('96385074', produto_id_esperado=self.p.id)
        self.assertEqual(self.c.pesquisar_produtos('96385074').produtos, [])

    def test_cache_nao_retem_transacao_revertida(self):
        self.c.pesquisar_produtos('lily')
        with self.assertRaises(RuntimeError):
            with self.bd.transacao():
                self.bd.conexao.execute("UPDATE Produtos SET nome='Malbec' WHERE id=?", (self.p.id,))
                self.assertTrue(self.c.pesquisar_produtos('malbec').produtos)
                raise RuntimeError('rollback simulado')
        self.assertEqual(self.c.pesquisar_produtos('malbec').produtos, [])
        self.assertTrue(self.c.pesquisar_produtos('lily').produtos)

    def test_gravacao_em_outra_conexao_invalida_cache(self):
        self.c.pesquisar_produtos('lily')
        outra = BancoDados(self.caminho, senha=SENHA, backup_automatico=False)
        try:
            ControladorEstoque(outra).registrar_entrada(self.p.id, 2)
        finally:
            outra.fechar()
        self.assertEqual(self.c.pesquisar_produtos('lily').produtos[0].estoque_atual, 6)

    def test_sessao_fechada_nao_retorna_cache(self):
        self.c.pesquisar_produtos('lily')
        self.bd.fechar()
        self.assertIsNone(self.bd._indice_pesquisa)
        from models.seguranca import ERROS_BANCO
        with self.assertRaises(ERROS_BANCO):
            self.c.pesquisar_produtos('lily')


if __name__ == '__main__':
    unittest.main(verbosity=2)
