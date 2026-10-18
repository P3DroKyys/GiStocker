"""Exclusão em lote, edição completa, modal de senha e auditoria de alterações.

Execute: .venv/Scripts/python.exe -m unittest auditoria.verificar_edicao_exclusao
Bancos em memória ou temporários; nunca abre os dados da instalação.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from controllers.controllers import ErroNegocio
from models.models import BancoDados
from models.seguranca import ErroSeguranca
from multicanal.motor import Motor
from servico.cliente import Cliente
from servico.nucleo import Nucleo

SENHA = 'senha-teste-2026'
MARCA, OUTRA_MARCA = config.MARCAS[0], config.MARCAS[1]
CATEGORIA, OUTRA_CATEGORIA = config.CATEGORIAS[0], config.CATEGORIAS[1]


def raiz_tk(teste):
    import customtkinter as ctk
    from views.tarefas import cancelar_tarefas
    raiz = ctk.CTk()
    raiz.withdraw()
    teste.addCleanup(lambda: (cancelar_tarefas(raiz, todas=True), raiz.destroy()))
    return raiz


def consumir(gerador):
    while True:
        try:
            next(gerador)
        except StopIteration as fim:
            return fim.value


class Controlador(unittest.TestCase):
    """Regras e registros no banco, pelo mesmo caminho de escrita do serviço (Motor.fisico)."""

    def setUp(self):
        self.bd = BancoDados(':memory:')
        self.addCleanup(self.bd.fechar)
        self.motor = Motor(self.bd)
        self.c = self.motor.estoque
        self.chave = 0

    def escrever(self, metodo, *args, **kwargs):
        self.chave += 1
        return self.motor.fisico(metodo, list(args), kwargs, f'teste:{self.chave}')

    def produto(self, nome='Hidratante Lily', **dados):
        valores = dict(preco_venda_base='50', custo_inicial='10', quantidade_inicial=5)
        valores.update(dados)
        return self.escrever('cadastrar_produto', nome, MARCA, CATEGORIA, **valores)

    def alteracoes(self, **filtro):
        return self.c.listar_alteracoes(limite=200, **filtro)

    def test_edicao_registra_antes_e_depois_de_cada_campo(self):
        p = self.produto()
        resultado = self.escrever('editar_produto', p.id, nome='Hidratante Lily 400 ml', marca=OUTRA_MARCA,
                                  categoria=OUTRA_CATEGORIA, preco_venda_base='55', novo_estoque='8',
                                  novo_custo='10,5')
        esperado = [
            'Nome alterado de "Hidratante Lily" para "Hidratante Lily 400 ml"',
            f'Marca alterada de {MARCA} para {OUTRA_MARCA}',
            f'Categoria alterada de {CATEGORIA} para {OUTRA_CATEGORIA}',
            'Preço alterado de R$ 50,00 para R$ 55,00',
            'Estoque alterado de 5 para 8 un.',
            'Custo médio alterado de R$ 10,0000 para R$ 10,5000',
        ]
        self.assertEqual(resultado.alteracoes, esperado)
        registros = self.alteracoes()
        self.assertEqual([r['descricao'] for r in reversed(registros)], esperado)
        self.assertEqual({r['produto_id'] for r in registros}, {p.id})
        self.assertEqual({r['produto_nome'] for r in registros}, {'Hidratante Lily'})
        self.assertEqual({r['acao'] for r in registros}, {'Edição'})
        self.assertEqual(len({(r['operacao'], r['data_hora']) for r in registros}), 1)
        self.assertRegex(registros[0]['data_hora'], r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$')
        preco = next(r for r in registros if r['campo'] == 'Preço base')
        self.assertEqual((preco['valor_anterior'], preco['valor_novo']), ('R$ 50,00', 'R$ 55,00'))
        atual = self.c.obter_produto(p.id)
        self.assertEqual((atual.nome, atual.marca, atual.categoria, atual.preco_venda_base,
                          atual.estoque_atual, atual.custo_medio),
                         ('Hidratante Lily 400 ml', OUTRA_MARCA, OUTRA_CATEGORIA, 55.0, 8, 10.5))
        ajuste = self.c.listar_logs(limite=1)[0]
        self.assertEqual((ajuste['id'], ajuste['tipo'], ajuste['quantidade']),
                         (resultado.log_id, config.TIPO_AJUSTE, 3))

    def test_edicao_so_de_dados_nao_gera_movimentacao(self):
        p = self.produto()
        logs = len(self.c.listar_logs(limite=200))
        resultado = self.escrever('editar_produto', p.id, categoria=OUTRA_CATEGORIA)
        self.assertIsNone(resultado.log_id)
        self.assertEqual(len(self.c.listar_logs(limite=200)), logs)
        self.assertEqual([r['campo'] for r in self.alteracoes()], ['Categoria'])

    def test_edicao_invalida_ou_igual_nao_grava_nada(self):
        p = self.produto()
        # Um campo inválido descarta também os válidos da mesma edição.
        for kwargs, mensagem in (({'nome': '   '}, 'nome'),
                                 ({'nome': 'Outro', 'marca': 'Desconhecida'}, 'marca'),
                                 ({'nome': 'Outro', 'categoria': 'Outra'}, 'categoria'),
                                 ({'nome': 'Outro', 'preco_venda_base': 'abc'}, 'Preço'),
                                 ({'nome': 'Outro', 'novo_estoque': '-1'}, 'negativo'),
                                 ({'nome': p.nome, 'novo_estoque': '5'}, 'Nenhuma alteração')):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ErroNegocio, mensagem):
                self.escrever('editar_produto', p.id, **kwargs)
        self.assertEqual(self.alteracoes(), [])
        self.assertEqual(self.c.obter_produto(p.id).nome, 'Hidratante Lily')

    def test_edicao_recusa_produto_movimentado_apos_selecao(self):
        p = self.produto()
        self.escrever('registrar_saida', p.id, 1)
        with self.assertRaisesRegex(ErroNegocio, 'movimentado'):
            self.escrever('editar_produto', p.id, nome='Novo', estoque_esperado=5, custo_esperado=10.0)
        self.assertEqual(self.alteracoes(), [])

    def test_ajuste_da_edicao_continua_desfazivel(self):
        p = self.produto()
        self.escrever('editar_produto', p.id, novo_estoque='20', nome='Renomeado')
        desfeito = self.escrever('desfazer_ultima_acao')
        self.assertEqual(desfeito.produto.estoque_atual, 5)
        self.assertEqual(len(self.alteracoes()), 2)   # a auditoria preserva o que foi feito

    def test_codigos_vinculados_e_desvinculados_sao_auditados(self):
        p = self.produto()
        self.escrever('vincular_codigo_barras', '7891000100103', p.id)
        self.escrever('desvincular_codigo_barras', '7891000100103', produto_id_esperado=p.id)
        self.assertEqual([r['descricao'] for r in self.alteracoes()],
                         ['Código de barras 7891000100103 desvinculado', 'Código de barras 7891000100103 vinculado'])
        self.assertEqual({r['acao'] for r in self.alteracoes()}, {'Código'})

    def test_exclusao_remove_historico_e_registra_instantaneo(self):
        alvo = self.produto(codigos=['7891000100103'])
        self.escrever('registrar_saida', alvo.id, 2)
        outro = self.produto(nome='Shampoo Siàge')
        self.escrever('registrar_entrada', outro.id, 3)
        resultado = self.escrever('excluir_produtos', [alvo.id])
        self.assertEqual(resultado, {'excluidos': 1, 'movimentacoes': 2})
        self.assertEqual([p.id for p in self.c.listar_produtos()], [outro.id])
        for tabela in ('Logs_Movimentacao', 'Eventos_Estoque', 'Codigos_Barras', 'Politicas_Alocacao',
                       'Cobertura_Produto_Canal'):
            coluna = 'produto_id'
            self.assertEqual(self.bd.buscar_um(f'SELECT count(*) FROM {tabela} WHERE {coluna}=?', (alvo.id,))[0], 0, tabela)
        registro = self.alteracoes(produto_id=alvo.id)[0]
        self.assertEqual((registro['acao'], registro['produto_nome'], registro['campo']),
                         ('Exclusão', 'Hidratante Lily', 'Produto'))
        self.assertIn('estoque 3 un.', registro['valor_anterior'])
        self.assertIn('7891000100103', registro['valor_anterior'])
        self.assertEqual(registro['descricao'], 'Produto excluído com 2 movimentação(ões) e 1 código(s)')
        # O livro de eventos volta a ser imutável e o desfazer segue nos demais produtos.
        with self.assertRaisesRegex(Exception, 'imutaveis'):
            self.bd.executar('DELETE FROM Eventos_Estoque WHERE produto_id=?', (outro.id,))
        self.assertEqual(self.escrever('desfazer_ultima_acao').produto.estoque_atual, 5)
        self.assertEqual(self.bd.conexao.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_exclusao_em_lote_acima_do_tamanho_de_lote(self):
        ids = [self.escrever('cadastrar_produto', f'Produto {i:04}', MARCA, CATEGORIA).id for i in range(620)]
        self.assertEqual(self.escrever('excluir_produtos', ids)['excluidos'], 620)
        self.assertEqual(self.c.listar_produtos(), [])
        self.assertEqual(len(self.alteracoes()), 200)

    def test_exclusao_recusa_entrada_invalida_vinculos_e_simulacao(self):
        p = self.produto()
        for valor in ([], 'abc', [0], [True], (p.id,)):
            with self.subTest(valor=valor), self.assertRaisesRegex(ErroNegocio, 'Selecione'):
                self.escrever('excluir_produtos', valor)
        with self.assertRaisesRegex(ErroNegocio, 'não encontrado'):
            self.escrever('excluir_produtos', [p.id, 999])
        with self.bd.transacao():
            self.bd.executar("INSERT INTO Lojas_Externas VALUES('L','SHOPEE','Loja','SIMULADO',1)")
            self.bd.executar("INSERT INTO Catalogo_Remoto(id,loja,produto_externo,sku,armazem,titulo) VALUES('R','L','1','1','A','T')")
            self.bd.executar('INSERT INTO Vinculos_SKU VALUES(?,?)', ('R', p.id))
        with self.assertRaisesRegex(ErroNegocio, 'anúncios'):
            self.escrever('excluir_produtos', [p.id])
        with self.bd.transacao():
            self.bd.executar('DELETE FROM Vinculos_SKU')
            self.bd.executar("UPDATE Config_Multicanal SET estado='MULTICANAL_ATIVO'")
        with self.assertRaisesRegex(ErroNegocio, 'laboratório'):
            self.escrever('excluir_produtos', [p.id])
        self.assertEqual(self.c.obter_produto(p.id).nome, 'Hidratante Lily')
        self.assertEqual(self.alteracoes(), [])

    def test_listagem_pagina_e_filtra(self):
        p = self.produto()
        for i in range(3):
            self.escrever('editar_produto', p.id, nome=f'Nome {i}')
        primeira = self.c.listar_alteracoes(limite=2)
        seguinte = self.c.listar_alteracoes(limite=2, antes_id=primeira[-1]['id'])
        self.assertEqual(len(primeira) + len(seguinte), 3)
        self.assertEqual(self.c.listar_alteracoes(limite=5, produto_id=999), [])
        with self.assertRaises(ValueError):
            self.c.listar_alteracoes(limite=0)


class EsquemaBackup(unittest.TestCase):
    def test_banco_v3_migra_e_backup_antigo_restaura_auditoria_vazia(self):
        from gestao import backup
        from models.seguranca import validar_esquema_legado
        with tempfile.TemporaryDirectory() as pasta:
            n = Nucleo(Path(pasta))
            try:
                cliente = Cliente(Path(pasta))
                with patch('servico.cliente.chamar', side_effect=lambda _n, pedido, _p: n.executar(pedido, 'S-1')):
                    cliente.abrir('', SENHA, SENHA)
                    p = cliente.chamar('estoque.cadastrar_produto', 'Produto', MARCA, CATEGORIA, quantidade_inicial=4)
                    cliente.chamar('estoque.editar_produto', p.id, nome='Renomeado', senha=SENHA)
                    pacote = json.loads(consumir(backup.exportar(n.cofre.banco)))
                    self.assertEqual(pacote['esquema'], 4)
                    self.assertEqual(len(pacote['tabelas']['Logs_Alteracao']['linhas']), 1)
                    # Banco e backup como gravados pela versão anterior (esquema 3).
                    con = n.cofre.banco.conexao
                    con.execute('DROP TABLE Logs_Alteracao')
                    con.execute('PRAGMA user_version=3')
                    validar_esquema_legado(con)
                    del pacote['tabelas']['Logs_Alteracao']
                    pacote['esquema'] = 3
                    n.fechar()
                    cliente.abrir(SENHA)
                    con = n.cofre.banco.conexao
                    self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0], BancoDados.VERSAO_ESQUEMA)
                    validar_esquema_legado(con)
                    cliente.chamar('estoque.editar_produto', p.id, nome='Outro', senha=SENHA)
                    consumir(backup.restaurar(n.cofre, json.dumps(pacote).encode(), lambda r: None))
                    self.assertEqual(cliente.chamar('estoque.listar_alteracoes'), [])
                    self.assertEqual(cliente.chamar('estoque.obter_produto', p.id).nome, 'Renomeado')
            finally:
                n.fechar()

    def test_backup_com_tabela_a_mais_ou_a_menos_e_recusado(self):
        from gestao import backup
        with tempfile.TemporaryDirectory() as pasta:
            n = Nucleo(Path(pasta))
            try:
                cliente = Cliente(Path(pasta))
                with patch('servico.cliente.chamar', side_effect=lambda _n, pedido, _p: n.executar(pedido, 'S-1')):
                    cliente.abrir('', SENHA, SENHA)
                pacote = json.loads(consumir(backup.exportar(n.cofre.banco)))
                del pacote['tabelas']['Logs_Alteracao']   # esquema 4 exige a tabela
                with self.assertRaisesRegex(ValueError, 'incompatível'):
                    consumir(backup.restaurar(n.cofre, json.dumps(pacote).encode(), lambda r: None))
            finally:
                n.fechar()


class ServicoSenha(unittest.TestCase):
    """A senha é conferida no agente antes de qualquer escrita protegida."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.n = Nucleo(Path(self.tmp.name))
        self.addCleanup(self.n.fechar)
        self.cliente = Cliente(Path(self.tmp.name))
        transporte = patch('servico.cliente.chamar',
                           side_effect=lambda _n, pedido, _p: self.n.executar(pedido, 'S-1-5-21-1-2-3-1001'))
        transporte.start()
        self.addCleanup(transporte.stop)
        self.cliente.abrir('', SENHA, SENHA)
        self.estoque, _ = self.cliente.criar_controladores()
        self.p = self.estoque.cadastrar_produto('Produto', MARCA, CATEGORIA, quantidade_inicial=3)

    def liberar_intervalo(self):
        self.n.tentativas.clear()

    def test_senha_nas_duas_acoes(self):
        acoes = (('editar_produto', (self.p.id,), {'nome': 'Novo nome'}),
                 ('excluir_produtos', ([self.p.id],), {}))
        for metodo, args, kwargs in acoes:
            operacao = getattr(self.estoque, metodo)
            with self.subTest(metodo=metodo):
                antes = (self.estoque.listar_produtos(), self.estoque.listar_alteracoes())
                with self.assertRaisesRegex(ValueError, 'Informe a senha'):
                    operacao(*args, **kwargs)
                with self.assertRaisesRegex(ValueError, 'Senha incorreta'):
                    operacao(*args, senha='errada', **kwargs)
                # Repetição imediata aguarda o mesmo intervalo crescente do login.
                with self.assertRaisesRegex(ErroSeguranca, 'Aguarde'):
                    operacao(*args, senha=SENHA, **kwargs)
                self.assertEqual((self.estoque.listar_produtos(), self.estoque.listar_alteracoes()), antes)
                self.liberar_intervalo()
                operacao(*args, senha=SENHA, **kwargs)
        self.assertEqual(self.estoque.listar_produtos(), [])
        self.assertEqual([r['acao'] for r in self.estoque.listar_alteracoes()], ['Exclusão', 'Edição'])

    def test_senha_errada_nao_altera_dados(self):
        with self.assertRaisesRegex(ValueError, 'Senha incorreta'):
            self.estoque.editar_produto(self.p.id, nome='Outro', senha='errada')
        self.liberar_intervalo()
        with self.assertRaisesRegex(ValueError, 'Senha incorreta'):
            self.estoque.excluir_produtos([self.p.id], senha='errada')
        self.assertEqual(self.estoque.obter_produto(self.p.id).nome, 'Produto')
        self.assertEqual(self.estoque.listar_alteracoes(), [])

    def test_senha_fica_fora_do_journal_e_do_recibo(self):
        with patch.object(self.cliente.journal, 'iniciar', wraps=self.cliente.journal.iniciar) as journal:
            self.estoque.editar_produto(self.p.id, nome='Outro', senha=SENHA)
            journal.assert_not_called()
            self.estoque.vincular_codigo_barras('7891000100103', self.p.id)
            journal.assert_called_once()
        recibos = self.n.cofre.banco.conexao.execute('SELECT resposta FROM Comandos_IPC').fetchall()
        self.assertTrue(recibos)
        self.assertFalse(any(SENHA in r[0] for r in recibos))

    def test_ajuste_sem_senha_nao_e_exposto(self):
        with self.assertRaises(AttributeError):
            self.estoque.ajustar_produto
        with self.assertRaisesRegex(ValueError, 'não permitido'):
            self.cliente.chamar('estoque.ajustar_produto', self.p.id, 9)
        self.assertEqual(self.estoque.obter_produto(self.p.id).estoque_atual, 3)


class Tabela:
    """Treeview mínima: ordem das linhas, valores por coluna e títulos."""

    def __init__(self):
        self.linhas, self.selecao, self.titulos = {}, (), {}

    def get_children(self):
        return tuple(self.linhas)

    def selection(self):
        return self.selecao

    def selection_set(self, item):
        self.selecao = (item,)

    def exists(self, item):
        return item in self.linhas

    def delete(self, *itens):
        for item in itens:
            del self.linhas[item]

    def insert(self, _pai, _posicao, iid, values):
        self.linhas[iid] = list(values)

    def set(self, item, _coluna, valor):
        self.linhas[item][0] = valor

    def heading(self, coluna, **opcoes):
        self.titulos.setdefault(coluna, {}).update(opcoes)


class PainelSelecao(unittest.TestCase):
    def setUp(self):
        from views.painel_produtos import PainelProdutos, TODAS_CATEGORIAS, TODAS_MARCAS
        self.bd = BancoDados(':memory:')
        self.addCleanup(self.bd.fechar)
        self.motor = Motor(self.bd)
        self.ids = [self.motor.estoque.cadastrar_produto(f'Produto {nome}', MARCA, CATEGORIA).id
                    for nome in ('Alfa', 'Bravo', 'Charlie', 'Delta', 'Eco', 'Foxtrot')]
        p = self.painel = object.__new__(PainelProdutos)
        p.controlador = Mock(listar_produtos=self.motor.estoque.listar_produtos)
        p._produtos, p._busca_agendada, p._ordenacao, p._decrescente = [], None, 'nome', False
        p._marcados, p._ancora = set(), None
        p.var_busca = Mock(get=Mock(return_value=''))
        p.marca = Mock(get=Mock(return_value=TODAS_MARCAS))
        p.categoria = Mock(get=Mock(return_value=TODAS_CATEGORIAS))
        p.tabela = Tabela()
        p.contagem, p.detalhes, p.botao_abrir, p.botao_excluir = Mock(), Mock(), Mock(), Mock()
        p.atualizar()

    def marcados(self):
        return [int(i) for i, valores in self.painel.tabela.linhas.items() if valores[0] == '☑']

    def clicar(self, indice, shift=False, coluna='#1'):
        tabela = self.painel.tabela
        tabela.identify_region = Mock(return_value='cell')
        tabela.identify_column = Mock(return_value=coluna)
        tabela.identify_row = Mock(return_value=str(self.ids[indice]))
        return self.painel._clicar(Mock(x=10, y=10, state=0x0001 if shift else 0))

    def test_shift_clique_marca_e_desmarca_intervalo(self):
        self.assertEqual(self.clicar(1), 'break')
        self.clicar(4, shift=True)
        self.assertEqual(self.marcados(), self.ids[1:5])
        self.assertEqual(self.painel._marcados, set(self.ids[1:5]))
        # Shift em linha marcada desmarca do último clique (linha 4) até ela.
        self.clicar(2, shift=True)
        self.assertEqual(self.marcados(), [self.ids[1]])
        # Intervalo em sentido inverso parte da nova âncora (linha 2).
        self.clicar(0, shift=True)
        self.assertEqual(self.marcados(), self.ids[0:3])

    def test_clique_simples_e_fora_da_caixa(self):
        self.clicar(3)
        self.clicar(3)
        self.assertEqual(self.marcados(), [])
        self.assertIsNone(self.clicar(2, coluna='#2'))
        self.assertEqual(self.marcados(), [])

    def test_botao_visivel_somente_com_selecao(self):
        botao = self.painel.botao_excluir
        botao.pack_forget.assert_called()
        botao.pack.assert_not_called()
        self.clicar(0)
        self.clicar(2, shift=True)
        botao.pack.assert_called()
        self.assertEqual(botao.configure.call_args.kwargs['text'], 'Deletar produtos selecionados (3)')
        botao.reset_mock()
        self.painel._marcar_todos()
        self.assertEqual(self.marcados(), self.ids)
        self.assertEqual(self.painel.tabela.titulos['marcado']['text'], '☑')
        self.painel._marcar_todos()
        self.assertEqual(self.marcados(), [])
        botao.pack_forget.assert_called()

    def test_filtro_descarta_marcas_ocultas(self):
        self.clicar(0)
        self.clicar(5, shift=True)
        self.painel.var_busca.get.return_value = 'charlie'
        self.painel._filtrar()
        self.assertEqual(self.painel._marcados, {self.ids[2]})
        self.assertIsNone(self.painel._ancora)

    def test_exclusao_passa_ids_e_senha_ao_servico(self):
        self.clicar(1)
        self.clicar(2, shift=True)
        excluir = self.painel.controlador.excluir_produtos
        excluir.return_value = {'excluidos': 2, 'movimentacoes': 0}
        self.painel.winfo_exists = Mock(return_value=True)
        self.painel.atualizar = Mock()
        with patch('views.painel_produtos.confirmar_com_senha') as modal, \
                patch('views.painel_produtos.informar') as informar:
            modal.side_effect = lambda _origem, _titulo, mensagem, acao, botao: acao('senha digitada')
            self.painel._excluir_marcados()
        excluir.assert_called_once_with(self.ids[1:3], senha='senha digitada')
        self.assertIn('Produto Bravo', modal.call_args.args[2])
        informar.assert_called_once()
        self.painel.atualizar.assert_called_once()
        self.assertEqual(self.painel._marcados, set())

    def test_exclusao_cancelada_nao_altera_nada(self):
        self.clicar(0)
        self.painel.atualizar = Mock()
        with patch('views.painel_produtos.confirmar_com_senha', return_value=None), \
                patch('views.painel_produtos.informar') as informar:
            self.painel._excluir_marcados()
        informar.assert_not_called()
        self.painel.atualizar.assert_not_called()
        self.assertEqual(self.painel._marcados, {self.ids[0]})


class AjusteAdmin(unittest.TestCase):
    def tela(self):
        from views.view_admin import ViewAdmin
        produto = Mock(id=7, nome='Produto', marca=MARCA, categoria=CATEGORIA, preco_venda_base=50.0,
                       estoque_atual=5, custo_medio=10.1234)
        tela = Mock(produto_atual=produto)
        tela._texto_decimal = ViewAdmin._texto_decimal
        tela._campos_alterados = lambda: ViewAdmin._campos_alterados(tela)
        for campo, valor in (('entrada_nome', 'Produto'), ('combo_marca', MARCA), ('combo_categoria', CATEGORIA),
                             ('entrada_preco', '50,0'), ('entrada_estoque', '5'), ('entrada_custo', '10,1234')):
            getattr(tela, campo).get.return_value = valor
        return tela

    def test_envia_somente_campos_alterados_com_senha(self):
        from views.view_admin import ViewAdmin
        tela = self.tela()
        tela.entrada_preco.get.return_value = '55'
        tela.combo_categoria.get.return_value = OUTRA_CATEGORIA
        tela.controlador.editar_produto.return_value = Mock(alteracoes=['Preço alterado'])
        with patch('views.view_admin.confirmar_com_senha') as modal, patch('views.view_admin.informar'):
            modal.side_effect = lambda _origem, _titulo, mensagem, acao, botao: acao('s3nha')
            ViewAdmin._aplicar_ajuste(tela)
        tela.controlador.editar_produto.assert_called_once_with(
            7, categoria=OUTRA_CATEGORIA, preco_venda_base='55', estoque_esperado=5,
            custo_esperado=10.1234, senha='s3nha')
        self.assertIn('Categoria, Preço base', modal.call_args.args[2])
        tela._carregar_produto.assert_called_once_with(7)

    def test_sem_alteracao_nao_pede_senha(self):
        from views.view_admin import ViewAdmin
        tela = self.tela()
        with patch('views.view_admin.confirmar_com_senha') as modal, patch('views.view_admin.erro') as erro:
            ViewAdmin._aplicar_ajuste(tela)
        modal.assert_not_called()
        erro.assert_called_once()

    def test_modal_cancelado_ou_recusado_nao_recarrega(self):
        from views.view_admin import ViewAdmin
        tela = self.tela()
        tela.entrada_nome.get.return_value = 'Outro'
        with patch('views.view_admin.confirmar_com_senha', return_value=None), \
                patch('views.view_admin.informar') as informar:
            ViewAdmin._aplicar_ajuste(tela)
        informar.assert_not_called()
        tela._carregar_produto.assert_not_called()


class ModalSenha(unittest.TestCase):
    """Modal real (Tk) sem wait_window: o fluxo de confirmação é chamado diretamente."""

    def setUp(self):
        self.raiz = raiz_tk(self)

    def dialogo(self, acao):
        from views.confirmacao_senha import DialogoSenha
        return DialogoSenha(self.raiz, 'Excluir produtos', 'Texto', acao, 'Excluir')

    def test_senha_vazia_nao_chama_acao(self):
        acao = Mock()
        d = self.dialogo(acao)
        self.addCleanup(d.destroy)
        d._fechar(True)
        acao.assert_not_called()
        self.assertIn('Informe', d.status.cget('text'))

    def test_recusa_fica_no_modal_e_limpa_senha(self):
        acao = Mock(side_effect=ValueError('Senha incorreta. Nenhum dado foi alterado.'))
        d = self.dialogo(acao)
        self.addCleanup(d.destroy)
        d.senha.entrada.insert(0, 'errada')
        d._fechar(True)
        acao.assert_called_once_with('errada')
        self.assertTrue(d.winfo_exists())
        self.assertEqual(d.status.cget('text'), 'Senha incorreta. Nenhum dado foi alterado.')
        self.assertEqual(d.senha.get(), '')
        self.assertEqual(d.aceitar.cget('state'), 'normal')
        self.assertIsNone(d.retorno)

    def test_falha_tecnica_mostra_mensagem_amigavel(self):
        d = self.dialogo(Mock(side_effect=OSError('disco')))
        self.addCleanup(d.destroy)
        d.senha.entrada.insert(0, 'x')
        with patch('utils.erros.registrar_falha'):
            d._fechar(True)
        self.assertIn('espaço em disco', d.status.cget('text'))

    def test_sucesso_fecha_e_devolve_resultado(self):
        d = self.dialogo(Mock(return_value={'excluidos': 2}))
        d.senha.entrada.insert(0, SENHA)
        d._fechar(True)
        self.assertTrue(d.resultado)
        self.assertEqual(d.retorno, {'excluidos': 2})
        self.assertFalse(d.winfo_exists())

    def test_cancelar_enquanto_verifica_e_ignorado(self):
        d = self.dialogo(Mock())
        self.addCleanup(d.destroy)
        d._ocupado = True
        d._fechar(False)
        self.assertTrue(d.winfo_exists())

    def test_helper_devolve_none_ao_cancelar(self):
        from views.confirmacao_senha import confirmar_com_senha
        with patch('views.confirmacao_senha.DialogoSenha') as classe:
            classe.return_value.mostrar.return_value = False
            self.assertIsNone(confirmar_com_senha(self.raiz, 'T', 'M', Mock()))
            classe.return_value.mostrar.return_value = True
            classe.return_value.retorno = 'ok'
            self.assertEqual(confirmar_com_senha(self.raiz, 'T', 'M', Mock()), 'ok')


class RelatoriosSeparados(unittest.TestCase):
    def test_abas_consultam_movimentacoes_e_alteracoes_separadamente(self):
        import customtkinter as ctk
        from views.view_relatorios import ABA_ALTERACOES, ABA_MOVIMENTACOES, ViewRelatorios
        raiz = raiz_tk(self)
        controlador = Mock()
        controlador.buscar_produtos.return_value = []
        controlador.listar_logs.return_value = [dict(
            id=9, data_hora='2026-10-18 10:00:00', tipo='Saída', produto_nome='P', produto_marca=MARCA,
            quantidade=1, custo_no_momento=1.0, estoque_anterior=2, estoque_posterior=1, cancelado=False,
            observacao=None)]
        controlador.listar_alteracoes.return_value = [dict(
            id=3, data_hora='2026-10-18 10:01:00', acao='Edição', produto_id=1, produto_nome='P',
            campo='Preço base', descricao='Preço alterado de R$ 50,00 para R$ 55,00')] * 200
        tela = ViewRelatorios(raiz, Mock(controlador_estoque=controlador))
        tela.ao_mostrar()
        abas = next(w for w in tela.winfo_children() if isinstance(w, ctk.CTkTabview))
        self.assertEqual(set(abas._tab_dict), {ABA_MOVIMENTACOES, ABA_ALTERACOES})
        movimento = tela.movimentacoes.tabela
        alteracao = tela.alteracoes.tabela
        self.assertEqual(movimento.item(movimento.get_children()[0], 'values')[2], 'Saída')
        self.assertEqual(alteracao.item(alteracao.get_children()[0], 'values')[-1],
                         'Preço alterado de R$ 50,00 para R$ 55,00')
        self.assertEqual(tela.movimentacoes.botao_mais.cget('state'), 'disabled')
        self.assertEqual(tela.alteracoes.botao_mais.cget('state'), 'normal')
        tela.alteracoes.botao_mais.invoke()
        controlador.listar_alteracoes.assert_called_with(limite=200, produto_id=None, antes_id=3)
        tela.produto_filtro = 1
        tela._carregar_historicos()
        controlador.listar_logs.assert_called_with(limite=200, produto_id=1, antes_id=None)
        controlador.listar_alteracoes.assert_called_with(limite=200, produto_id=1, antes_id=None)


if __name__ == '__main__':
    unittest.main(verbosity=2)
