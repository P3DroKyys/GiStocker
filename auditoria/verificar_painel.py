"""Verifica a consulta e a integração do painel sem abrir GUI ou banco de uso.

Execute: .venv/Scripts/python.exe -B auditoria/verificar_painel.py
Os widgets são substituídos por objetos de teste; não valida layout visual.
"""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from controllers.controllers import ControladorEstoque
from models.models import BancoDados
from views.painel_produtos import PainelProdutos, TODAS_CATEGORIAS, TODAS_MARCAS
from views.view_admin import ViewAdmin


class Campo:
    def __init__(self, valor=""):
        self.valor = valor
        self.opcoes = {}

    def get(self):
        return self.valor

    def set(self, valor):
        self.valor = valor

    def configure(self, **opcoes):
        self.opcoes.update(opcoes)


class Tabela:
    def __init__(self):
        self.linhas = {}
        self.selecao = ()

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
        self.selecao = ()

    def insert(self, pai, posicao, iid, values):
        self.linhas[iid] = values

    def heading(self, *args, **kwargs):
        pass


class TestePainel(unittest.TestCase):
    def setUp(self):
        self.bd = BancoDados(":memory:", permitir_legado=True)
        self.addCleanup(self.bd.fechar)
        self.controlador = ControladorEstoque(self.bd)
        self.painel = object.__new__(PainelProdutos)
        p = self.painel
        p.controlador = self.controlador
        p.ao_abrir = Mock()
        p._produtos = []
        p._busca_agendada = None
        p._ordenacao = "nome"
        p._decrescente = False
        p.var_busca = Campo()
        p.marca = Campo(TODAS_MARCAS)
        p.categoria = Campo(TODAS_CATEGORIAS)
        p.tabela = Tabela()
        p.contagem = Campo()
        p.detalhes = Campo()
        p.botao_abrir = Campo()
        p._marcados = set()
        p._ancora = None
        p.botao_excluir = Mock()

    def cadastrar(self, nome="Colônia Lily", **dados):
        valores = dict(nome=nome, marca=config.MARCAS[0], categoria=config.CATEGORIAS[0],
                       preco_venda_base=30, custo_inicial=10.1234)
        valores.update(dados)
        return self.controlador.cadastrar_produto(**valores)

    def test_lista_completa_acima_de_500(self):
        for i in range(501):
            self.cadastrar(nome=f"Produto {i:03}")
        self.painel.atualizar()
        self.assertEqual(len(self.painel.tabela.linhas), 501)
        self.assertEqual(self.painel.contagem.opcoes["text"], "501 de 501 produtos cadastrados")

    def test_busca_sem_acento_e_filtros_combinados(self):
        alvo = self.cadastrar(codigos=["00123457", "96385074"])
        self.cadastrar(nome="Colônia Lily alternativa", marca=config.MARCAS[1])
        self.painel.atualizar()
        self.painel.var_busca.set("lily colonia 96385074")
        self.painel.marca.set(alvo.marca)
        self.painel.categoria.set(alvo.categoria)
        self.painel._filtrar()
        self.assertEqual(list(self.painel.tabela.linhas), [str(alvo.id)])
        self.painel.marca.set(config.MARCAS[1])
        self.painel._filtrar()
        self.assertEqual(len(self.painel.tabela.linhas), 0)
        self.assertIn("Nenhum produto encontrado", self.painel.detalhes.opcoes["text"])

    def test_ordenacao_numerica_e_inversao(self):
        caro = self.cadastrar(nome="A", preco_venda_base=100)
        barato = self.cadastrar(nome="Z", preco_venda_base=9)
        self.painel.atualizar()
        self.painel._ordenar("preco_venda_base")
        self.assertEqual(list(self.painel.tabela.linhas), [str(barato.id), str(caro.id)])
        self.painel._ordenar("preco_venda_base")
        self.assertEqual(list(self.painel.tabela.linhas), [str(caro.id), str(barato.id)])

    def test_atualizacao_preserva_selecao_e_recarrega_codigos(self):
        produto = self.cadastrar()
        self.painel.atualizar()
        self.painel.tabela.selection_set(str(produto.id))
        self.controlador.vincular_codigo_barras("036000291452", produto.id)
        self.controlador.registrar_entrada(produto.id, 2)
        self.painel.atualizar()
        self.assertEqual(self.painel.tabela.selection(), (str(produto.id),))
        self.assertEqual(self.painel.tabela.linhas[str(produto.id)][5], 2)   # após a caixa de seleção
        self.assertIn("036000291452", self.painel.detalhes.opcoes["text"])
        self.assertIn("10,1234", self.painel.detalhes.opcoes["text"])
        self.painel._abrir()
        self.painel.ao_abrir.assert_called_once_with(produto.id)

    def test_vazio_e_acao_sem_selecao(self):
        self.painel.atualizar()
        self.assertIn("Ainda não há produtos", self.painel.detalhes.opcoes["text"])
        self.assertEqual(self.painel.botao_abrir.opcoes["state"], "disabled")
        self.painel._abrir()
        self.painel.ao_abrir.assert_not_called()

    def test_encaminhamento_admin_dispensa_segundo_bloqueio(self):
        admin = object.__new__(ViewAdmin)
        admin._carregar_produto = Mock()
        admin.var_busca = Mock()
        admin._buscar = Mock()
        admin.abas = Mock()
        admin.entrada_estoque = Mock()
        admin._abrir_produto_catalogo(5)
        admin.var_busca.set.assert_called_once_with('#5')
        admin._buscar.assert_called_once()
        admin.abas.set.assert_called_once_with("Ajustes e códigos")


if __name__ == "__main__":
    unittest.main(verbosity=2)
