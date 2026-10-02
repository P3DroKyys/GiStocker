"""Testes de GTIN em memória; não abre bancos de uso nem janelas.

Execute: .venv/Scripts/python.exe -B auditoria/verificar_gtin.py
"""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from controllers.controllers import ControladorEstoque, ErroNegocio
from models.models import BancoDados
from utils.gtin import validar_gtin
from views.view_admin import ViewAdmin
from views.view_cadastro import ViewCadastro


# Vetores fixos: os resultados esperados não são gerados pelo validador.
VALIDOS = ("96385074", "036000291452", "4006381333931", "10012345000017")


class ValidacaoGTIN(unittest.TestCase):
    def test_quatro_tamanhos(self):
        for codigo in VALIDOS:
            with self.subTest(codigo=codigo):
                self.assertEqual(validar_gtin(codigo), codigo)

    def test_trim_e_zeros_preservados(self):
        for codigo in ("00123457", "036000291452", "00036000291452"):
            with self.subTest(codigo=codigo):
                self.assertEqual(validar_gtin(" \t" + codigo + "\r\n"), codigo)

    def test_somente_string(self):
        for valor in (None, 96385074, 96385074.0, True, b"96385074", ["96385074"]):
            with self.subTest(valor=valor), self.assertRaisesRegex(ValueError, "como texto"):
                validar_gtin(valor)

    def test_caracteres_ascii_exclusivos(self):
        for valor in ("", "  ", "9638507a", "9638 5074", "9638-5074", "9638.5074",
                      "+96385074", "９６３８５０７４", "٩٦٣٨٥٠٧٤", "9638\t5074",
                      "9638\n5074", "9638\x005074", "96385074\u200b", "9e6385074"):
            with self.subTest(valor=valor), self.assertRaisesRegex(ValueError, "somente números"):
                validar_gtin(valor)

    def test_comprimentos_exatos(self):
        for tamanho in (1, 7, 9, 10, 11, 15, 16, 100):
            with self.subTest(tamanho=tamanho), self.assertRaisesRegex(ValueError, "Tamanho inválido"):
                validar_gtin(("1234567890" * 10)[:tamanho])

    def test_repeticoes_inclusive_as_que_passariam_no_modulo(self):
        for tamanho in (8, 12, 13, 14):
            for digito in "0123456789":
                with self.subTest(tamanho=tamanho, digito=digito):
                    with self.assertRaisesRegex(ValueError, "dígitos repetidos"):
                        validar_gtin(digito * tamanho)

    def test_rejeita_todos_os_outros_dvs(self):
        for codigo in VALIDOS:
            for dv in "0123456789":
                if dv != codigo[-1]:
                    with self.subTest(codigo=codigo, dv=dv):
                        with self.assertRaises(ValueError) as falha:
                            validar_gtin(codigo[:-1] + dv)
                        self.assertEqual(str(falha.exception), "Código GTIN/EAN inválido")

    def test_soma_multipla_de_dez_dv_zero(self):
        self.assertEqual(validar_gtin("12345670"), "12345670")


class IntegracaoGTIN(unittest.TestCase):
    def setUp(self):
        self.bd = BancoDados(":memory:", permitir_legado=True)
        self.addCleanup(self.bd.fechar)
        self.c = ControladorEstoque(self.bd)

    def cadastrar(self, codigos):
        return self.c.cadastrar_produto("Produto teste", config.MARCAS[0], config.CATEGORIAS[0],
                                        30, 10, 2, codigos)

    def test_persistencia_textual_e_deduplicacao_apos_trim(self):
        produto = self.cadastrar([" 036000291452 ", "036000291452", "10012345000017"])
        self.assertEqual(produto.codigos, ["036000291452", "10012345000017"])
        linha = self.bd.buscar_um("SELECT codigo, typeof(codigo) AS tipo FROM Codigos_Barras WHERE codigo=?",
                                   ("036000291452",))
        self.assertEqual((linha["codigo"], linha["tipo"]), ("036000291452", "text"))
        self.assertEqual(self.c.resolver_codigo_barras("10012345000017").id, produto.id)

    def test_cadastro_invalido_nao_grava_nada(self):
        for invalido in ("96385075", "123", "lixo", "", "00000000", 96385074):
            with self.subTest(invalido=invalido):
                with self.assertRaises(ErroNegocio):
                    self.cadastrar([VALIDOS[0], invalido])
                for tabela in ("Produtos", "Codigos_Barras", "Logs_Movimentacao"):
                    self.assertEqual(self.bd.buscar_um(f"SELECT COUNT(*) AS n FROM {tabela}")["n"], 0)

    def test_parametro_codigos_nao_aceita_string_solitaria_ou_numero(self):
        for codigos in (VALIDOS[0], 0, 123, b"96385074"):
            with self.subTest(codigos=codigos), self.assertRaises(ErroNegocio):
                self.cadastrar(codigos)

    def test_vinculo_valida_e_mantem_unicidade(self):
        produto = self.cadastrar([])
        for codigo in ("96385075", "abc", "1111111111111", None):
            with self.subTest(codigo=codigo), self.assertRaises(ErroNegocio):
                self.c.vincular_codigo_barras(codigo, produto.id)
        self.assertEqual(self.c.listar_codigos(produto.id), [])
        self.c.vincular_codigo_barras(" 036000291452 ", produto.id)
        with self.assertRaises(ErroNegocio):
            self.c.vincular_codigo_barras("036000291452", produto.id)
        self.assertEqual(self.c.listar_codigos(produto.id), ["036000291452"])

    def tela_cadastro(self, codigo):
        tela = SimpleNamespace(controlador=Mock(wraps=self.c), entrada_codigo=Mock(),
                               lista_codigos=Mock(), entrada_nome=Mock())
        tela.entrada_codigo.get.return_value = codigo
        tela._adicionar_codigo = lambda: ViewCadastro._adicionar_codigo(tela)
        return tela

    @patch("views.view_cadastro.erro")
    def test_front_cadastro_rejeita_sem_incluir_na_lista(self, erro):
        tela = self.tela_cadastro("9638507X")
        self.assertFalse(tela._adicionar_codigo())
        tela.lista_codigos.adicionar.assert_not_called()
        tela.controlador.resolver_codigo_barras.assert_not_called()
        tela.entrada_codigo.delete.assert_not_called()
        erro.assert_called_once()

    @patch("views.view_cadastro.erro")
    def test_salvar_nao_ignora_campo_gtin_invalido_pendente(self, erro):
        tela = self.tela_cadastro("96385075")
        ViewCadastro._salvar(tela)
        tela.controlador.cadastrar_produto.assert_not_called()
        erro.assert_called_once_with("Código de barras", "Código GTIN/EAN inválido")

    @patch("views.view_cadastro.erro")
    def test_codigo_vindo_da_operacao_tambem_valida(self, erro):
        tela = self.tela_cadastro("123")
        ViewCadastro.ao_mostrar(tela, codigo="123")
        tela.lista_codigos.adicionar.assert_not_called()
        erro.assert_called_once()

    def test_front_cadastro_preserva_codigo_valido(self):
        tela = self.tela_cadastro(" 036000291452 ")
        self.assertTrue(tela._adicionar_codigo())
        tela.lista_codigos.adicionar.assert_called_once_with("036000291452")

    @patch("views.view_admin.erro")
    def test_front_admin_rejeita_antes_de_gravar(self, erro):
        produto = self.cadastrar([])
        tela = SimpleNamespace(produto_atual=produto, controlador=Mock(wraps=self.c),
                               entrada_codigo=Mock(), lista_codigos=Mock())
        tela.entrada_codigo.get.return_value = "123-4567"
        ViewAdmin._vincular_codigo(tela)
        tela.controlador.vincular_codigo_barras.assert_not_called()
        self.assertEqual(self.c.listar_codigos(produto.id), [])
        erro.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
