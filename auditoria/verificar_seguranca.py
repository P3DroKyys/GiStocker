"""Ataques e regressões exclusivamente em dados fictícios e pastas temporárias."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sqlcipher3
from controllers.controllers import ControladorEstoque, ControladorRelatorios, ErroNegocio
from models.models import BancoDados
from models.preferencias import Preferencias, ErroPreferencias, _hash_senha
from models.seguranca import (Cofre, ErroSeguranca, conectar, conferir_integridade,
                              validar_nova_senha, proteger_arquivo, ler_arquivo_protegido)
from views.main_view import JanelaPrincipal

SENHA = "Uma frase exclusiva de TESTE 2026!"
NOVA = "Outra frase exclusiva de TESTE 2027!"
MARCADOR = "SEGREDO_FICTICIO_94756"


def criar_preferencias_legadas(caminho, senha="1234"):
    with closing(sqlite3.connect(caminho)) as con, con:
        con.execute("CREATE TABLE Preferencias (id INTEGER PRIMARY KEY CHECK (id=1), senha_hash TEXT NOT NULL, tema TEXT NOT NULL)")
        con.execute("INSERT INTO Preferencias VALUES (1, ?, 'dark')", (_hash_senha(senha),))


def cadastrar(banco):
    return ControladorEstoque(banco).cadastrar_produto(
        nome=MARCADOR, marca="Natura", categoria="Corpo e Banho", codigos=["7891000100103"],
        quantidade_inicial=5, custo_inicial=10, preco_venda_base=20)


class BaseSeguranca(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pasta = Path(self.temp.name)
        self.caminho = self.pasta / "dados" / "estoque.db"
        self.caminho.parent.mkdir()
        self.cofre = Cofre(self.caminho)
        self.addCleanup(self.cofre.fechar)

    def iniciar(self):
        self.cofre.abrir("", SENHA, SENHA)
        return self.cofre.banco

    def legado(self):
        criar_preferencias_legadas(self.cofre.legado)
        bd = BancoDados(self.caminho, permitir_legado=True, backup_automatico=False)
        cadastrar(bd)
        bd.fechar()


class ProtecaoBanco(BaseSeguranca):
    def test_instalacao_nao_cria_banco_antes_da_senha(self):
        self.assertEqual(self.cofre.modo, "novo")
        self.assertFalse(self.caminho.exists())
        with self.assertRaises(ValueError):
            self.cofre.abrir("", "1234", "1234")
        self.assertFalse(self.caminho.exists())

    def test_sqlite_comum_nao_le_banco_protegido(self):
        cadastrar(self.iniciar())
        self.cofre.fechar()
        with closing(sqlite3.connect(self.caminho)) as con, self.assertRaises(sqlite3.DatabaseError):
            con.execute("SELECT * FROM Produtos").fetchall()
        self.assertNotIn(MARCADOR.encode(), self.caminho.read_bytes())

    def test_senha_errada_nao_cria_backup_ou_sessao(self):
        self.iniciar()
        self.cofre.fechar()
        antes = set(self.caminho.parent.rglob("*.db"))
        with self.assertRaises(ErroSeguranca):
            self.cofre.abrir("errada")
        self.assertIsNone(self.cofre.banco)
        self.assertIsNone(self.cofre.trava)
        self.assertEqual(antes, set(self.caminho.parent.rglob("*.db")))

    def test_motor_nativo_resiste_a_falhas_com_log_e_protecao_memoria(self):
        self.iniciar()
        self.cofre.fechar()
        codigo = '''
import sys,sqlcipher3 as s
for i in range(40):
 c=s.connect(sys.argv[1]);c.set_key('senha ficticia incorreta')
 c.execute('PRAGMA cipher_log_level=WARN')
 c.execute('PRAGMA cipher_memory_security=ON')
 try:
  c.execute('SELECT * FROM sqlite_master').fetchall()
 except s.DatabaseError:
  pass
 else:
  raise AssertionError('Senha errada foi aceita')
 finally:
  c.close()
print('OK')
'''
        resultado = subprocess.run([sys.executable, '-B', '-c', codigo, str(self.caminho)],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=30)
        self.assertEqual(resultado.returncode, 0)
        self.assertEqual(resultado.stdout.strip(), 'OK')

    def test_excluir_configuracao_nao_reinicia_senha(self):
        self.iniciar()
        criar_preferencias_legadas(self.cofre.legado)
        self.cofre.legado.unlink()
        self.cofre.fechar()
        with self.assertRaises(ErroSeguranca):
            self.cofre.abrir("1234")
        self.cofre.abrir(SENHA)

    def test_forjar_preferencias_nao_troca_chave(self):
        self.iniciar()
        self.cofre.fechar()
        criar_preferencias_legadas(self.cofre.legado, "senha do invasor")
        with self.assertRaises(ErroSeguranca):
            self.cofre.abrir("senha do invasor")
        self.cofre.abrir(SENHA)

    def test_chamar_liberar_interface_sem_banco_nao_abre(self):
        janela = Mock(_desbloqueado=False, preferencias=self.cofre)
        JanelaPrincipal._liberar_acesso(janela)
        self.assertFalse(janela._desbloqueado)
        janela._construir_barra_lateral.assert_not_called()

    def test_backend_nao_abre_arquivo_sem_chave(self):
        self.iniciar()
        with self.assertRaises(ValueError):
            BancoDados(self.caminho)
        with self.assertRaises(sqlite3.DatabaseError):
            BancoDados(self.caminho, permitir_legado=True)

    def test_alteracao_de_pagina_detectada(self):
        cadastrar(self.iniciar())
        self.cofre.fechar()
        conteudo = bytearray(self.caminho.read_bytes())
        conteudo[4200] ^= 0x80
        self.caminho.write_bytes(conteudo)
        with self.assertRaises(ErroSeguranca):
            self.cofre.abrir(SENHA)
        self.assertIsNone(self.cofre.banco)

    def test_wal_backup_exportacao_sem_texto_puro(self):
        bd = self.iniciar()
        cadastrar(bd)
        backup = bd.criar_backup()
        exportado = ControladorRelatorios(bd).exportar_protegido(self.pasta / "exportacoes")
        for arquivo in self.pasta.rglob("*"):
            if arquivo.is_file() and arquivo.name != ".sessao.lock":
                self.assertNotIn(MARCADOR.encode(), arquivo.read_bytes(), arquivo.name)
        for arquivo in (backup, exportado):
            with closing(conectar(arquivo, SENHA)) as con:
                conferir_integridade(con)
                self.assertEqual(con.execute("SELECT nome FROM Produtos").fetchone()[0], MARCADOR)

    def test_csv_nao_expoe_dados_em_sessao_protegida(self):
        bd = self.iniciar()
        with self.assertRaises(ErroNegocio):
            ControladorRelatorios(bd).exportar_csv(self.pasta / "csv")
        self.assertFalse((self.pasta / "csv").exists())

    def test_segunda_instancia_nao_altera_banco(self):
        self.iniciar()
        segunda = Cofre(self.caminho)
        self.addCleanup(segunda.fechar)
        with self.assertRaises(ErroSeguranca):
            segunda.abrir(SENHA)
        self.cofre.fechar()
        segunda.abrir(SENHA)

    def test_fechar_invalida_conexao_e_libera_trava(self):
        bd = self.iniciar()
        self.cofre.fechar()
        with self.assertRaises(sqlcipher3.ProgrammingError):
            bd.conexao.execute("SELECT * FROM Produtos")
        self.assertIsNone(self.cofre.banco)
        self.assertIsNone(self.cofre.trava)

    def test_troca_senha_recriptografa_banco(self):
        bd = self.iniciar()
        cadastrar(bd)
        self.cofre.alterar_senha(SENHA, NOVA, NOVA)
        self.assertTrue(self.cofre.verificar_senha(NOVA))
        self.assertFalse(self.cofre.verificar_senha(SENHA))
        self.assertEqual(bd.conexao.execute("SELECT nome FROM Produtos").fetchone()[0], MARCADOR)
        self.cofre.fechar()
        self.cofre.abrir(NOVA)

    def test_senha_antiga_errada_nao_modifica_chave(self):
        self.iniciar()
        with self.assertRaises(ValueError):
            self.cofre.alterar_senha("errada", NOVA, NOVA)
        self.assertTrue(self.cofre.verificar_senha(SENHA))
        self.assertFalse(self.cofre.verificar_senha(NOVA))

    def test_troca_preserva_backup_com_senha_da_epoca(self):
        bd = self.iniciar()
        backup = bd.criar_backup()
        self.cofre.alterar_senha(SENHA, NOVA, NOVA)
        recente = bd.criar_backup()
        with closing(conectar(backup, SENHA)) as con:
            conferir_integridade(con)
        with closing(conectar(recente, NOVA)) as con:
            conferir_integridade(con)

    def test_temporal_config_tema_nao_contem_segredos(self):
        self.iniciar()
        self.cofre.definir_tema("light")
        self.assertEqual(self.cofre.obter_tema(), "light")
        self.assertEqual(self.cofre.tema.read_text(), '{"tema": "light"}')
        self.cofre.tema.write_text('{"tema":"../../dados/estoque.db"}')
        self.assertEqual(self.cofre.obter_tema(), "dark")

    def test_nao_ha_extensoes_dinamicas(self):
        bd = self.iniciar()
        with self.assertRaises(sqlcipher3.OperationalError):
            bd.conexao.execute("SELECT load_extension('arquivo_inexistente')")
        self.assertEqual(bd.conexao.execute("PRAGMA temp_store").fetchone()[0], 2)
        self.assertEqual(bd.conexao.execute("PRAGMA trusted_schema").fetchone()[0], 0)

    def test_injecao_na_senha_nao_vira_sql(self):
        self.iniciar()
        self.cofre.fechar()
        with self.assertRaises(ErroSeguranca):
            self.cofre.abrir("'; PRAGMA key=''; DROP TABLE Produtos;--")
        self.cofre.abrir(SENHA)

    def test_caracteres_unicode_e_aspas_sao_preservados(self):
        senha = "Frase açucarada ' óculos ☀ 2026"
        self.cofre.abrir("", senha, senha)
        self.cofre.fechar()
        self.cofre.abrir(senha)
        self.assertFalse(self.cofre.verificar_senha(senha.upper()))

    def test_conexao_criada_com_senha_fraca_nao_novo_cadastro(self):
        for senha in ("1234", "Ab!23", " Ab!2 ", "123456", "abcdef", "1" * 40, " " * 50, "x" * 129, "1234567890123456", "abcdefghijklmnop", "passwordpassword123", "senha\ncom quebra de linha", None, 123):
            with self.subTest(senha_tipo=type(senha).__name__), self.assertRaises(ValueError):
                validar_nova_senha(senha, senha)
        with self.assertRaises(ValueError):
            validar_nova_senha(SENHA, NOVA)

    def test_senha_seis_caracteres_criacao_troca_e_reabertura(self):
        senha = "Lili22"
        nova = "Bia!77"
        self.cofre.abrir("", senha, senha)
        self.cofre.alterar_senha(senha, nova, nova)
        self.cofre.fechar()
        with self.assertRaises(ErroSeguranca):
            self.cofre.abrir(senha)
        self.cofre.abrir(nova)
        self.assertIsNotNone(self.cofre.banco)


class MigracaoSegura(BaseSeguranca):
    def test_migracao_preserva_todos_dados_e_backup(self):
        self.legado()
        self.assertEqual(self.cofre.modo, "legado")
        with closing(sqlite3.connect(self.caminho)) as con:
            antes = {t: con.execute(f"SELECT * FROM {t}").fetchall()
                     for t in ("Produtos", "Codigos_Barras", "Logs_Movimentacao", "sqlite_sequence")}
        bd = self.cofre.abrir("1234", SENHA, SENHA)
        for tabela, linhas in antes.items():
            self.assertEqual([tuple(r) for r in bd.conexao.execute(f"SELECT * FROM {tabela}")], linhas)
        self.assertEqual(self.cofre.modo, "protegido")
        self.assertTrue(list((self.caminho.parent / "backups").glob("*.db")))

    def test_senha_legada_errada_nao_migra(self):
        self.legado()
        antes = self.caminho.read_bytes()
        with self.assertRaises(ValueError):
            self.cofre.abrir("errada", SENHA, SENHA)
        self.assertEqual(self.caminho.read_bytes(), antes)

    def test_apagar_preferencias_antigas_nao_reseta(self):
        self.legado()
        self.cofre.legado.unlink()
        with self.assertRaises(ErroPreferencias):
            self.cofre.abrir("1234", SENHA, SENHA)
        self.assertEqual(self.cofre.modo, "legado")
        self.assertFalse(self.cofre.legado.exists())

    def test_banco_ausente_com_backups_nao_cria_vazio(self):
        self.iniciar().criar_backup()
        self.cofre.fechar()
        self.caminho.unlink()
        with self.assertRaises(ErroSeguranca):
            self.cofre.abrir("", NOVA, NOVA)
        self.assertFalse(self.caminho.exists())

    def test_arquivo_vazio_ou_lixo_nao_recria(self):
        for conteudo in (b"", b"lixo", b"x" * 4096):
            self.caminho.write_bytes(conteudo)
            with self.assertRaises(ErroSeguranca):
                self.cofre.abrir(SENHA)
            self.assertEqual(self.caminho.read_bytes(), conteudo)

    def test_trigger_hostil_legado_nao_e_executado(self):
        self.legado()
        with closing(sqlite3.connect(self.caminho)) as con, con:
            con.execute("CREATE TRIGGER invasor AFTER INSERT ON Produtos BEGIN DELETE FROM Produtos; END")
        with self.assertRaises(ErroSeguranca):
            self.cofre.abrir("1234", SENHA, SENHA)
        self.assertEqual(self.cofre.modo, "legado")

    def test_falha_de_substituicao_preserva_original(self):
        self.legado()
        with patch("models.seguranca.os.replace", side_effect=PermissionError("simulacao")):
            with self.assertRaises(PermissionError):
                self.cofre.abrir("1234", SENHA, SENHA)
        self.assertEqual(self.cofre.modo, "legado")
        with closing(sqlite3.connect(self.caminho)) as con:
            self.assertEqual(con.execute("SELECT nome FROM Produtos").fetchone()[0], MARCADOR)
        self.assertFalse(list(self.caminho.parent.glob(".migracao*")))

    def test_falha_backup_nao_substitui_original(self):
        self.legado()
        with patch.object(BancoDados, "criar_backup", side_effect=OSError("disco cheio")):
            with self.assertRaises(OSError):
                self.cofre.abrir("1234", SENHA, SENHA)
        self.assertEqual(self.cofre.modo, "legado")

    def test_banco_legado_aberto_nao_migra(self):
        self.legado()
        con = sqlite3.connect(self.caminho)
        self.addCleanup(con.close)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("BEGIN")
        con.execute("SELECT * FROM Produtos").fetchall()
        with self.assertRaises(ErroSeguranca):
            self.cofre.abrir("1234", SENHA, SENHA)
        self.assertEqual(self.cofre.modo, "legado")

    def test_protege_backups_e_csv_antigos_com_conteudo_verificado(self):
        self.legado()
        pasta = self.caminho.parent / "backups"
        pasta.mkdir()
        antigo = pasta / "antigo.db"
        original = self.caminho.read_bytes()
        antigo.write_bytes(original)
        self.cofre.exportacoes.mkdir()
        csv = self.cofre.exportacoes / "relatorio.csv"
        csv.write_bytes(MARCADOR.encode())
        self.cofre.abrir("1234", SENHA, SENHA)
        self.assertFalse(antigo.exists())
        self.assertFalse(csv.exists())
        for origem, esperado in ((antigo, original), (csv, MARCADOR.encode())):
            protegidos = list(origem.parent.glob(origem.name + ".*.gsa"))
            self.assertEqual(len(protegidos), 1)
            with closing(conectar(protegidos[0], SENHA)) as con:
                recuperado = b"".join(r[0] for r in con.execute("SELECT dados FROM Conteudo ORDER BY id"))
                self.assertEqual(recuperado, esperado)
            self.assertEqual(ler_arquivo_protegido(protegidos[0], SENHA), (origem.name, esperado))

    def test_retoma_copias_apos_migracao_parcial_sem_perder_nova_senha(self):
        self.legado()
        self.cofre.exportacoes.mkdir()
        csv = self.cofre.exportacoes / "legado.csv"
        csv.write_bytes(MARCADOR.encode())
        with patch("models.seguranca.proteger_arquivo", side_effect=OSError("disco cheio")):
            with self.assertRaises(OSError):
                self.cofre.abrir("1234", SENHA, SENHA)
        self.assertEqual(self.cofre.modo, "protegido")
        self.assertIsNone(self.cofre.banco)
        self.assertTrue(csv.exists())
        self.cofre.abrir(SENHA)
        self.assertFalse(csv.exists())
        self.assertTrue(self.cofre.verificar_senha(SENHA))

    def test_falha_rekey_bloqueia_sessao_sem_perder_senha_atual(self):
        bd = self.iniciar()
        con = bd.conexao
        proxy = Mock(wraps=con)
        proxy.in_transaction = False
        proxy.reset_key.side_effect = OSError("disco cheio")
        bd.conexao = proxy
        with self.assertRaises(OSError):
            self.cofre.alterar_senha(SENHA, NOVA, NOVA)
        self.assertIsNone(self.cofre.banco)
        self.cofre.abrir(SENHA)
        self.assertFalse(self.cofre.verificar_senha(NOVA))

    def test_logs_anteriores_nao_ficam_legiveis(self):
        self.legado()
        log = self.pasta / "erros.log"
        log.write_bytes(MARCADOR.encode())
        self.cofre.abrir("1234", SENHA, SENHA)
        self.assertFalse(log.exists())
        self.assertTrue(list(self.pasta.glob("erros.log.*.gsa")))

    def test_falha_no_arquivo_criptografado_preserva_original(self):
        bd = self.iniciar()
        origem = self.pasta / "original.csv"
        origem.write_bytes(MARCADOR.encode())
        with patch("models.seguranca.conferir_integridade", side_effect=ErroSeguranca("simulacao")):
            with self.assertRaises(ErroSeguranca):
                proteger_arquivo(bd.conexao, origem)
        self.assertEqual(origem.read_bytes(), MARCADOR.encode())
        self.assertFalse(list(self.pasta.glob("*.gsa")))


class QuedaEnergia(BaseSeguranca):
    def interromper(self, commit):
        self.iniciar()
        self.cofre.fechar()
        codigo = '''
import os,sys
from models.seguranca import Cofre
c=Cofre(sys.argv[1]); b=c.abrir(sys.stdin.readline().rstrip('\\n'))
b.conexao.execute('BEGIN IMMEDIATE')
b.conexao.execute("INSERT INTO Produtos(nome,marca,categoria) VALUES ('segredo queda', 'Natura', 'Cabelos')")
if sys.argv[2]=='sim': b.conexao.execute('COMMIT')
os._exit(71)
'''
        resultado = subprocess.run([sys.executable, "-B", "-c", codigo, str(self.caminho), "sim" if commit else "nao"],
                                    input=SENHA + "\n", text=True, capture_output=True,
                                    cwd=Path(__file__).resolve().parents[1], timeout=30)
        self.assertEqual(resultado.returncode, 71, resultado.stderr)
        bd = self.cofre.abrir(SENHA)
        self.assertEqual(bd.conexao.execute("SELECT count(*) FROM Produtos").fetchone()[0], int(commit))
        conferir_integridade(bd.conexao)

    def test_interrupcao_durante_recriptografia_preserva_banco(self):
        import time
        bd = self.iniciar()
        with bd.transacao():
            bd.conexao.executemany("INSERT INTO Produtos(nome,marca,categoria) VALUES (?, 'Natura', 'Cabelos')",
                                  ((str(i) + 'z' * 6000,) for i in range(1200)))
        self.cofre.fechar()
        codigo = """
import sys,time
from models.seguranca import conectar
c=conectar(sys.argv[1],sys.stdin.readline().rstrip('\\n'))
nova=sys.stdin.readline().rstrip('\\n')
c.execute('PRAGMA journal_mode=DELETE')
print('PRONTO',flush=True)
c.reset_key(nova)
c.close()
"""
        processo = subprocess.Popen([sys.executable, '-B', '-c', codigo, str(self.caminho)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, cwd=Path(__file__).resolve().parents[1])
        try:
            processo.stdin.write(SENHA + chr(10) + NOVA + chr(10))
            processo.stdin.flush()
            self.assertEqual(processo.stdout.readline().strip(), 'PRONTO')
            time.sleep(0.015)
            processo.kill()
            processo.communicate(timeout=15)
        finally:
            if processo.poll() is None:
                processo.kill()
                processo.communicate()
        # É válido persistir a chave anterior ou a nova; jamais um banco misto.
        valida = None
        for senha in (SENHA, NOVA):
            try:
                with closing(conectar(self.caminho, senha)) as con:
                    conferir_integridade(con)
                    self.assertEqual(con.execute('SELECT count(*) FROM Produtos').fetchone()[0], 1200)
                valida = senha
                break
            except sqlcipher3.Error:
                continue
        self.assertIsNotNone(valida)

    def test_queda_antes_commit_reverte(self):
        self.interromper(False)

    def test_queda_depois_commit_preserva_e_libera_trava(self):
        self.interromper(True)


if __name__ == "__main__":
    unittest.main()
