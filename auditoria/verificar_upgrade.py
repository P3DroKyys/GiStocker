"""Regressões de acesso, configurações, cadastro opcional e dashboard (bases isoladas)."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
import sqlite3
import sys
import tempfile
from threading import Barrier
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import config
from controllers.controllers import ControladorEstoque, ControladorRelatorios, ErroNegocio
from models.models import BancoDados
from models.preferencias import Preferencias, ErroPreferencias
from gerar_build import gerar_build
from views.acesso import CampoSenha, TelaAcesso
from views.componentes import PALETA
from views.main_view import JanelaPrincipal
from views.view_admin import ViewAdmin
from views.view_configuracoes import ViewConfiguracoes
from views.view_dashboard import ViewDashboard


# Testes da antiga senha padrão substituídos por verificar_seguranca.py.

class FluxosDasTelas(unittest.TestCase):
    def test_bloqueio_exatamente_apos_90_minutos_em_ambos_caminhos(self):
        for metodo in ('_registrar_atividade', '_conferir_inatividade'):
            for segundos in (600, 5399, 5400, 5401):
                with self.subTest(metodo=metodo, segundos=segundos):
                    janela = Mock(_desbloqueado=True, _ultimo_uso=0)
                    with patch('views.main_view.time.monotonic', return_value=segundos):
                        getattr(JanelaPrincipal, metodo)(janela)
                    self.assertEqual(janela.bloquear.call_count, int(segundos >= 5400))

    def acesso(self):
        return Mock(_ocupado=False, _espera=None, _tentativas=0, nova_senha=None, confirmacao=None)

    def test_senha_errada_nao_abre_sistema_e_limpa_campo(self):
        tela = self.acesso()
        tela.preferencias.abrir.side_effect = ValueError("Senha incorreta")
        TelaAcesso._entrar(tela)
        tela.ao_desbloquear.assert_not_called()
        tela.campo_senha.limpar.assert_called_once()
        tela.after.assert_called_once_with(1000, tela._reativar)

    def test_senha_correta_abre_uma_unica_vez(self):
        tela = self.acesso()
        tela.preferencias.abrir.return_value = Mock()
        TelaAcesso._entrar(tela)
        TelaAcesso._entrar(tela)
        tela.ao_desbloquear.assert_called_once()
        tela.campo_senha.limpar.assert_called_once()

    def test_erro_no_arquivo_de_acesso_nao_libera_sistema(self):
        tela = self.acesso()
        tela.preferencias.abrir.side_effect = sqlite3.OperationalError('inacessível')
        TelaAcesso._entrar(tela)
        tela.ao_desbloquear.assert_not_called()
        tela.after.assert_called_once_with(1000, tela._reativar)

    def test_navegacao_e_tema_bloqueados_antes_da_senha(self):
        janela = Mock(_desbloqueado=False, views={})
        for chave in ('operacao', 'cadastro', 'admin', 'dashboard', 'relatorios', 'configuracoes'):
            JanelaPrincipal.mostrar_view(janela, chave)
        JanelaPrincipal.alternar_tema(janela, 'light')
        janela.preferencias.definir_tema.assert_not_called()
        self.assertEqual(janela.views, {})

    def test_tema_so_muda_depois_de_salvar(self):
        janela = Mock(_desbloqueado=True)
        janela.preferencias.definir_tema.side_effect = sqlite3.OperationalError('disco')
        with patch('views.main_view.ctk.set_appearance_mode') as aplicar, self.assertRaises(sqlite3.Error):
            JanelaPrincipal.alternar_tema(janela, 'light')
        aplicar.assert_not_called()

    def test_campo_senha_revela_e_oculta_sem_alterar_texto(self):
        campo = Mock()
        campo.entrada.cget.return_value = '•'
        CampoSenha.alternar_visibilidade(campo)
        campo.entrada.configure.assert_called_with(show='')
        campo.botao.configure.assert_called_with(text='Ocultar')
        campo.entrada.cget.return_value = ''
        CampoSenha.alternar_visibilidade(campo)
        campo.entrada.configure.assert_called_with(show='•')
        campo.botao.configure.assert_called_with(text='Mostrar')
        campo.entrada.delete.assert_not_called()

    def test_configuracoes_limpa_e_oculta_todas_senhas_ao_sair(self):
        tela = Mock()
        ViewConfiguracoes.ao_ocultar(tela)
        for campo in (tela.senha_atual, tela.nova_senha, tela.confirmacao):
            campo.limpar.assert_called_once()
        campo = Mock()
        CampoSenha.limpar(campo)
        campo.entrada.delete.assert_called_once_with(0, 'end')
        campo.ocultar.assert_called_once()

    def test_confirmacao_troca_nao_mostra_sucesso_quando_salvar_falha(self):
        for falha in (ValueError('Senha incorreta'), sqlite3.OperationalError('disco')):
            tela = Mock(_salvando=False)
            tela.janela.preferencias.alterar_senha.side_effect = falha
            ViewConfiguracoes._alterar_senha(tela)
            tela.ao_ocultar.assert_not_called()
            self.assertFalse(tela._salvando)
            tela.botao_salvar.configure.assert_called_with(state='normal')
            for campo in (tela.senha_atual, tela.nova_senha, tela.confirmacao):
                campo.ocultar.assert_called_once()

    def test_troca_bem_sucedida_limpa_campos(self):
        tela = Mock(_salvando=False)
        ViewConfiguracoes._alterar_senha(tela)
        tela.ao_ocultar.assert_called_once()
        self.assertIn('Senha alterada', tela.mensagem.configure.call_args.kwargs['text'])


class CadastroEAjuste(unittest.TestCase):
    def setUp(self):
        self.banco = BancoDados(':memory:', permitir_legado=True)
        self.addCleanup(self.banco.fechar)
        self.c = ControladorEstoque(self.banco)
        self.r = ControladorRelatorios(self.banco)

    def cadastrar(self, **kw):
        return self.c.cadastrar_produto('Produto', config.MARCAS[0], config.CATEGORIAS[0], **kw)

    def test_cadastro_aceita_precos_omitidos_vazios_ou_espacos(self):
        for preco, custo in ((None, None), ('', ''), ('  ', '\t'), ('10,50', ''), ('', '2,50')):
            p = self.cadastrar(preco_venda_base=preco, custo_inicial=custo, quantidade_inicial=3)
            produto = self.c.obter_produto(p.id)
            self.assertEqual(produto.preco_venda_base, 10.50 if preco == '10,50' else 0)
            self.assertEqual(produto.custo_medio, 2.50 if custo == '2,50' else 0)
            self.assertEqual(produto.estoque_atual, 3)
        self.assertEqual(self.cadastrar().custo_medio, 0)

    def test_precos_informados_invalidos_continuam_rejeitados(self):
        for invalido in ('abc', '-1', 'NaN', 'inf', '1e99'):
            for campo in ('preco_venda_base', 'custo_inicial'):
                with self.subTest(campo=campo, valor=invalido), self.assertRaises(ErroNegocio):
                    self.cadastrar(**{campo: invalido})
        self.assertEqual(self.r.obter_kpis()['total_produtos'], 0)

    def test_demais_validacoes_preservadas(self):
        for kw in ({'nome': ''}, {'marca': ''}, {'categoria': ''}, {'codigos': ['lixo']}, {'quantidade_inicial': -1}):
            dados = dict(nome='Teste', marca=config.MARCAS[0], categoria=config.CATEGORIAS[0])
            dados.update(kw)
            with self.assertRaises(ErroNegocio):
                self.c.cadastrar_produto(**dados)
        self.assertEqual(self.r.obter_kpis()['total_produtos'], 0)

    def test_produtos_conta_cadastros_inclui_zerados_sem_duplicar_codigos(self):
        self.assertEqual(self.r.obter_kpis()['total_produtos'], 0)
        self.cadastrar(codigos=['96385074', '036000291452'])
        self.cadastrar(quantidade_inicial=10)
        self.assertEqual(self.r.obter_kpis()['total_produtos'], 2)
        self.assertEqual(self.r.obter_kpis()['total_itens'], 10)

    def test_sem_precos_permite_entrada_saida_ajuste_desfazer_e_relatorios(self):
        produto = self.cadastrar(quantidade_inicial=10, codigos=['96385074'])
        self.c.registrar_entrada(produto.id, 10, '4,00')
        self.assertEqual(self.c.obter_produto(produto.id).custo_medio, 2)
        self.c.registrar_saida(produto.id, 5)
        self.c.ajustar_produto(produto.id, 18)
        self.assertEqual(self.c.listar_logs()[0]['observacao'], 'Ajuste manual (Admin)')
        self.c.desfazer_ultima_acao()
        p = self.c.obter_produto(produto.id)
        self.assertEqual((p.estoque_atual, p.custo_medio), (15, 2))
        self.assertEqual(self.r.obter_kpis()['valor_investido'], 30)
        self.assertEqual(self.r.obter_kpis()['receita_potencial'], 0)

    def test_admin_aplica_ajuste_sem_campo_motivo_e_preserva_concorrencia(self):
        p = self.cadastrar(quantidade_inicial=5)
        # O serviço confere e retira a senha antes de chamar o controlador.
        controlador = SimpleNamespace(editar_produto=lambda *a, senha, **k: self.c.editar_produto(*a, **k))
        tela = SimpleNamespace(produto_atual=p, controlador=controlador, _carregar_produto=Mock(), _buscar=Mock(),
                               winfo_exists=Mock(return_value=True), _texto_decimal=ViewAdmin._texto_decimal)
        tela._campos_alterados = lambda: ViewAdmin._campos_alterados(tela)
        for campo, valor in (('entrada_nome', p.nome), ('combo_marca', p.marca), ('combo_categoria', p.categoria),
                             ('entrada_preco', '0,0'), ('entrada_estoque', '7'), ('entrada_custo', '0,0')):
            setattr(tela, campo, Mock(get=Mock(return_value=valor)))
        recusas = []

        def modal(_origem, _titulo, _mensagem, acao, _botao):
            try:
                return acao('senha')
            except ErroNegocio as falha:   # o modal real exibe a recusa e continua aberto
                recusas.append(str(falha))

        with patch('views.view_admin.confirmar_com_senha', side_effect=modal), patch('views.view_admin.informar'):
            ViewAdmin._aplicar_ajuste(tela)
            self.assertEqual(self.c.obter_produto(p.id).estoque_atual, 7)
            self.assertEqual(self.c.listar_logs()[0]['observacao'], 'Ajuste manual (Admin)')
            tela.entrada_estoque.get.return_value = '8'
            ViewAdmin._aplicar_ajuste(tela)  # produto carregado anteriormente está desatualizado
        self.assertEqual(len(recusas), 1)
        self.assertIn('movimentado', recusas[0])
        self.assertEqual(self.c.obter_produto(p.id).estoque_atual, 7)


class LayoutDashboard(unittest.TestCase):
    def test_legenda_fora_das_barras_dentro_da_figura_em_ambos_temas(self):
        for tema in ('light', 'dark'):
            for largura in (700, 1000, 1900):
                for pico in (0, 125, 2**63 - 1):
                    with self.subTest(tema=tema, largura=largura, pico=pico):
                        fig = Figure(figsize=(largura / 100, 3), dpi=100, constrained_layout=True)
                        canvas = FigureCanvasAgg(fig)
                        eixo = fig.add_subplot()
                        eixo.set_title('Entradas x Saídas – últimos 30 dias', loc='left', pad=10)
                        tela = Mock()
                        tela._preparar_eixo.return_value = (eixo, PALETA[tema], canvas, '#FFFFFF')
                        datas = [date(2026, 9, 1) + timedelta(days=i) for i in range(30)]
                        tela.relatorios.movimentacao_ultimos_dias.return_value = (datas, [0] * 29 + [pico], [0] * 30)
                        ViewDashboard._desenhar_barras(tela)
                        canvas.draw()
                        legenda = eixo.get_legend().get_window_extent(canvas.get_renderer())
                        self.assertLess(legenda.y1, eixo.bbox.y0)
                        self.assertGreaterEqual(legenda.y0, 0)
                        self.assertLessEqual(legenda.x1, fig.bbox.x1)
                        self.assertGreaterEqual(legenda.x0, 0)
                        for barra in eixo.patches:
                            self.assertFalse(legenda.overlaps(barra.get_window_extent(canvas.get_renderer())))

    def test_kpis_reorganizam_para_duas_ou_quatro_colunas(self):
        tela = Mock(_colunas_kpi=None)
        tela._get_widget_scaling.return_value = 1.25
        for largura, colunas in ((900, 2), (1400, 4), (900, 2)):
            tela.linha_kpi.winfo_width.return_value = largura
            ViewDashboard._organizar_kpis(tela)
            self.assertEqual(tela._colunas_kpi, colunas)
            tela.kpi_receita.grid.assert_called_with(row=3 // colunas, column=3 % colunas,
                                                    sticky='ew', padx=6, pady=4)


class Distribuicao(unittest.TestCase):
    def test_builds_criam_destinos_distintos_sem_pasta_temporaria_privada(self):
        def empacotar(comando, **_kwargs):
            destino = Path(comando[comando.index('--distpath') + 1]) / 'GestorEstoque'
            destino.mkdir()
            (destino / 'GestorEstoque.exe').write_bytes(b'executavel simulado')
        with tempfile.TemporaryDirectory() as pasta:
            with patch('tempfile.mkdtemp', side_effect=AssertionError('não usar ACL privada na build')):
                primeiro = gerar_build(pasta, executar=empacotar)
                segundo = gerar_build(pasta, executar=empacotar)
            self.assertNotEqual(primeiro, segundo)
            self.assertEqual(primeiro.read_bytes(), b'executavel simulado')
            self.assertTrue(segundo.is_file())


if __name__ == '__main__':
    unittest.main(verbosity=2)
