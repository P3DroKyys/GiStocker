"""Criptografia em repouso: a senha abre o banco, não apenas a interface.

SQLCipher mantém chave, páginas e journals no mecanismo nativo. Nunca criamos
uma cópia descriptografada em disco para trabalhar. Não existe chave de fábrica.
"""
from contextlib import closing
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

import sqlcipher3 as cipher
import config

ERROS_BANCO = (sqlite3.Error, cipher.Error)
ERROS_OPERACIONAIS = (sqlite3.OperationalError, cipher.OperationalError)
CABECALHO_SQLITE = b"SQLite format 3\x00"


class ErroSeguranca(RuntimeError):
    pass


class ErroAutenticacao(ErroSeguranca):
    """A credencial não autenticou o conteúdo protegido."""


class ErroSessao(ErroSeguranca):
    """A sessão expirou ou não pertence à identidade do solicitante."""


@lru_cache(maxsize=1)
def verificar_motor():
    """Evita regressão acidental para uma wheel antiga ou sem as proteções.

    É uma verificação de instalação, não uma defesa contra alteração do código.
    """
    with closing(cipher.connect(":memory:")) as con:
        versao = con.execute("PRAGMA cipher_version").fetchone()
        opcoes = {r[0] for r in con.execute("PRAGMA compile_options")}
        con.execute("PRAGMA writable_schema=ON")
        defensivo = con.execute("PRAGMA writable_schema").fetchone()[0] == 0
    if (not versao or tuple(map(int, versao[0].split()[0].split("."))) < (4, 18, 0)
            or cipher.sqlite_version_info < (3, 53, 4)
            or not {"TEMP_STORE=3", "OMIT_LOAD_EXTENSION"} <= opcoes or not defensivo):
        raise ErroSeguranca("A biblioteca de segurança está desatualizada. Execute 1_preparar_ambiente.bat ou reinstale a build 1.1.0.")


def validar_nova_senha(senha, confirmacao):
    if not isinstance(senha, str) or not config.MINIMO_CARACTERES_SENHA <= len(senha) <= 128:
        raise ValueError(f"Use uma senha com {config.MINIMO_CARACTERES_SENHA} a 128 caracteres.")
    if len(set(senha)) < 3 or len(senha.strip()) < config.MINIMO_CARACTERES_SENHA:
        raise ValueError("Escolha uma senha sem repetições óbvias e sem contar espaços nas extremidades.")
    if any(ord(c) < 32 or ord(c) == 127 for c in senha):
        raise ValueError("A frase de senha não pode conter quebras de linha ou caracteres de controle.")
    simples = senha.casefold().replace(" ", "")
    if (any(simples in sequencia for sequencia in
            ("1234567890" * 13, "abcdefghijklmnopqrstuvwxyz" * 5, "qwertyuiopasdfghjklzxcvbnm" * 6))
            or simples.startswith(("passwordpassword", "senhasenhasenha", "adminadminadmin"))):
        raise ValueError("Essa sequência é previsível. Escolha uma frase de senha pessoal.")
    if senha != confirmacao:
        raise ValueError("A confirmação não corresponde à nova senha.")


def preparar_conexao(conexao):
    if hasattr(conexao, "enable_load_extension"):
        conexao.enable_load_extension(False)
    conexao.execute("PRAGMA trusted_schema=OFF")
    conexao.execute("PRAGMA temp_store=MEMORY")
    conexao.execute("PRAGMA secure_delete=ON")
    conexao.execute("PRAGMA synchronous=FULL")


def conectar(caminho, senha, *, criar=False, somente_leitura=False):
    if not isinstance(senha, str) or not senha or len(senha) > 256:
        raise ValueError("Informe a senha de acesso.")
    caminho = Path(caminho).resolve()
    if criar and somente_leitura:
        raise ValueError("Uma conexão somente de leitura não pode criar arquivos.")
    alvo = str(caminho) if criar else caminho.as_uri() + ("?mode=ro" if somente_leitura else "?mode=rw")
    con = cipher.connect(alvo, uri=not criar, isolation_level=None, timeout=5)
    try:
        con.execute("PRAGMA cipher_log_level=NONE")
        con.set_key(senha)
        con.execute("PRAGMA cipher_memory_security=ON")
        # Falhar antes de criar tabelas, fazer backup ou disponibilizar consultas.
        con.execute("SELECT count(*) FROM sqlite_master").fetchone()
        preparar_conexao(con)
        return con
    except BaseException:
        con.close()
        raise


def conferir_integridade(conexao, esquema="main"):
    if esquema not in ("main", "copia", "arquivo"):
        raise ValueError("Esquema não permitido.")
    if conexao.execute(f"PRAGMA {esquema}.cipher_integrity_check").fetchall():
        raise ErroSeguranca("O arquivo protegido está danificado. Restaure um backup íntegro.")
    if [tuple(r) for r in conexao.execute(f"PRAGMA {esquema}.integrity_check")] != [("ok",)]:
        raise ErroSeguranca("O banco não passou na verificação de integridade.")
    if conexao.execute(f"PRAGMA {esquema}.foreign_key_check").fetchall():
        raise ErroSeguranca("O banco contém referências inconsistentes.")


def copiar_protegido(conexao, destino):
    """ATTACH sem KEY herda a chave da sessão; não retém a senha em Python."""
    destino = Path(destino)
    with destino.open("xb"):
        pass
    anexado = False
    try:
        conexao.execute("ATTACH DATABASE ? AS copia", (str(destino),))
        anexado = True
        conexao.execute("SELECT sqlcipher_export('copia')").fetchone()
        versao = int(conexao.execute("PRAGMA main.user_version").fetchone()[0])
        conexao.execute(f"PRAGMA copia.user_version={versao}")
        conferir_integridade(conexao, "copia")
        conexao.execute("DETACH DATABASE copia")
        anexado = False
        with destino.open("rb") as arquivo:
            if arquivo.read(16) == CABECALHO_SQLITE:
                raise ErroSeguranca("A cópia não foi criptografada.")
    except BaseException:
        if anexado:
            conexao.execute("DETACH DATABASE copia")
        destino.unlink(missing_ok=True)
        raise
    return destino


class TravaSessao:
    """Trava de SO, liberada inclusive após encerramento abrupto do processo."""
    def __init__(self, caminho):
        self.arquivo = None
        caminho.parent.mkdir(parents=True, exist_ok=True)
        arquivo = caminho.open("a+b")
        try:
            if arquivo.seek(0, 2) == 0:
                arquivo.write(b"\0")
                arquivo.flush()
            arquivo.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as erro:
            arquivo.close()
            raise ErroSeguranca("Outra instância está usando estes dados. Feche-a antes de continuar.") from erro
        self.arquivo = arquivo

    def fechar(self):
        if self.arquivo:
            self.arquivo.close()
            self.arquivo = None


def validar_esquema_legado(conexao):
    """Não executar DDL, triggers ou views vindos de arquivos externos."""
    tabelas = {"Produtos", "Codigos_Barras", "Logs_Movimentacao", "sqlite_sequence"}
    indices = {"idx_codigos_produto", "idx_logs_produto", "idx_logs_data",
               "sqlite_autoindex_Codigos_Barras_1"}
    versao = conexao.execute("PRAGMA user_version").fetchone()[0]
    from multicanal.esquema import TABELAS, INDICES, conferir_objeto
    if versao in (2, 3):
        tabelas |= TABELAS
    objetos = conexao.execute("SELECT type, name, sql FROM sqlite_master").fetchall()
    if {r[1] for r in objetos if r[0] == "table"} != tabelas:
        raise ErroSeguranca("Este arquivo não contém um banco de estoque completo.")
    for tipo, nome, sql in objetos:
        if versao in (2, 3) and (nome in TABELAS or versao == 3 and nome in INDICES or tipo == 'trigger' or nome.startswith('sqlite_autoindex_') and nome != 'sqlite_autoindex_Codigos_Barras_1'):
            if conferir_objeto(tipo, nome, sql):
                continue
            raise ErroSeguranca("Estrutura multicanal inesperada. Abertura interrompida.")
        if ((tipo == "table" and nome in tabelas and "VIRTUAL" not in (sql or "").upper())
                or (tipo == "index" and nome in indices)):
            continue
        raise ErroSeguranca("O banco antigo possui uma estrutura inesperada. A migração foi interrompida.")
    if versao not in (0, 1, 2, 3):
        raise ErroSeguranca("Versão do banco antigo não suportada.")


def proteger_arquivo(conexao, origem):
    """Preserva backups/CSVs antigos em um contêiner SQLCipher, por blocos.

    Só remove o original depois de conferir todo o conteúdo recuperável.
    .gsa é um arquivo de preservação; nunca execute SQL armazenado nele.
    """
    origem = Path(origem)
    destino = origem.with_name(origem.name + "." + uuid4().hex[:12] + ".gsa")
    anexado = False
    try:
        with destino.open("xb"):
            pass
        conexao.execute("ATTACH DATABASE ? AS arquivo", (str(destino),))
        anexado = True
        conexao.execute("CREATE TABLE arquivo.Conteudo (id INTEGER PRIMARY KEY, dados BLOB NOT NULL)")
        conexao.execute("CREATE TABLE arquivo.Metadados (nome TEXT, tamanho INTEGER, sha256 TEXT)")
        resumo = hashlib.sha256()
        tamanho = 0
        antes = origem.stat()
        with origem.open("rb") as entrada:
            conexao.execute("BEGIN IMMEDIATE")
            try:
                for indice, bloco in enumerate(iter(lambda: entrada.read(1024 * 1024), b"")):
                    resumo.update(bloco)
                    tamanho += len(bloco)
                    conexao.execute("INSERT INTO arquivo.Conteudo VALUES (?, ?)", (indice, bloco))
                conexao.execute("INSERT INTO arquivo.Metadados VALUES (?, ?, ?)",
                                (origem.name, tamanho, resumo.hexdigest()))
                conexao.execute("COMMIT")
            except BaseException:
                conexao.execute("ROLLBACK")
                raise
        conferir_integridade(conexao, "arquivo")
        recuperado = hashlib.sha256()
        for linha in conexao.execute("SELECT dados FROM arquivo.Conteudo ORDER BY id"):
            recuperado.update(linha[0])
        depois = origem.stat()
        if (recuperado.digest() != resumo.digest() or antes.st_size != depois.st_size
                or antes.st_mtime_ns != depois.st_mtime_ns):
            raise ErroSeguranca("Um arquivo mudou durante a proteção. Feche as outras versões do programa.")
        conexao.execute("DETACH DATABASE arquivo")
        anexado = False
        origem.unlink()
        return destino
    except BaseException:
        if conexao.in_transaction:
            conexao.execute("ROLLBACK")
        if anexado:
            conexao.execute("DETACH DATABASE arquivo")
        # A cópia verificada pode ser a única restante se uma falha ocorrer depois
        # de unlink. Nesse caso conservá-la é obrigatório.
        if origem.exists():
            destino.unlink(missing_ok=True)
        raise


def ler_arquivo_protegido(caminho, senha, limite=128 * 1024 * 1024):
    """Recupera um .gsa em memória, sem produzir arquivo em texto puro.

    Nome é metadado, nunca um caminho a executar/extrair automaticamente.
    O limite explícito evita alocações ilimitadas em arquivos não confiáveis.
    """
    with closing(conectar(caminho, senha, somente_leitura=True)) as con:
        conferir_integridade(con)
        objetos = {(r[0], r[1]) for r in con.execute("SELECT type,name FROM sqlite_master")}
        if objetos != {("table", "Conteudo"), ("table", "Metadados")}:
            raise ErroSeguranca("Este arquivo não é um contêiner de preservação do GiStocker.")
        metadados = con.execute("SELECT nome,tamanho,sha256 FROM Metadados").fetchall()
        if len(metadados) != 1:
            raise ErroSeguranca("Metadados de preservação inválidos.")
        nome, tamanho, digest = metadados[0]
        if not isinstance(tamanho, int) or not 0 <= tamanho <= limite or not isinstance(nome, str):
            raise ErroSeguranca("O arquivo excede o limite permitido para recuperação em memória.")
        resultado = bytearray()
        for indice, (identificador, bloco) in enumerate(con.execute("SELECT id,dados FROM Conteudo ORDER BY id")):
            if identificador != indice or not isinstance(bloco, bytes) or len(resultado) + len(bloco) > tamanho:
                raise ErroSeguranca("Blocos de preservação inválidos.")
            resultado.extend(bloco)
        if len(resultado) != tamanho or hashlib.sha256(resultado).hexdigest() != digest:
            raise ErroSeguranca("O conteúdo recuperado não corresponde ao arquivo original.")
        return nome, bytes(resultado)


class Cofre:
    """Ciclo de vida da sessão e migração. Nenhuma senha é armazenada no objeto."""
    def __init__(self, caminho, preferencias_legadas=None, exportacoes=None):
        verificar_motor()
        self.caminho = Path(caminho).resolve()
        self.legado = Path(preferencias_legadas or self.caminho.with_name("configuracoes.db"))
        self.exportacoes = Path(exportacoes or self.caminho.parent.parent / "exportacoes")
        self.tema = self.caminho.with_name("aparencia.json")
        self.banco = None
        self.trava = None

    @property
    def modo(self):
        if not self.caminho.exists():
            if self.legado.exists() or any(self.caminho.parent.glob("backups/*")):
                raise ErroSeguranca("O banco de estoque está ausente. Restaure-o; um banco vazio não será criado.")
            return "novo"
        with self.caminho.open("rb") as arquivo:
            cabecalho = arquivo.read(16)
        if len(cabecalho) != 16:
            raise ErroSeguranca("O arquivo de estoque está vazio ou incompleto. Restaure um backup.")
        return "legado" if cabecalho == CABECALHO_SQLITE else "protegido"

    def abrir(self, senha, nova=None, confirmacao=None):
        from models.models import BancoDados
        if self.banco is not None:
            raise ErroSeguranca("A sessão já está aberta.")
        if self.trava is not None:
            raise ErroSeguranca("Já existe uma tentativa de abertura em andamento.")
        self.trava = TravaSessao(self.caminho.with_name(".sessao.lock"))
        try:
            modo = self.modo
            if modo in ("novo", "legado"):
                validar_nova_senha(nova, confirmacao)
                if modo == "legado":
                    self._migrar(senha, nova)
                else:
                    temporario = self.caminho.with_name(".criacao_" + uuid4().hex + ".db")
                    try:
                        banco = BancoDados(temporario, senha=nova, criar=True, backup_automatico=False)
                        banco.fechar()
                        # rename, não replace: não sobrescrever um arquivo criado por outra instância.
                        temporario.rename(self.caminho)
                    finally:
                        temporario.unlink(missing_ok=True)
                senha = nova
            self.banco = BancoDados(self.caminho, senha=senha, backup_automatico=True)
            self._proteger_legados()
            return self.banco
        except ERROS_BANCO as erro:
            self.fechar()
            raise ErroSeguranca("Senha incorreta ou banco danificado. Nenhum acesso foi liberado.") from erro
        except BaseException:
            self.fechar()
            raise

    def _migrar(self, antiga, nova):
        from models.preferencias import Preferencias
        from models.models import BancoDados
        if not Preferencias(self.legado).verificar_senha(antiga):
            raise ValueError("A senha atual está incorreta.")
        temporario = self.caminho.with_name(".migracao_" + uuid4().hex + ".db")
        # O driver legado só lê o banco para converter. Nenhuma conexão em texto
        # puro chega aos controladores ou ao painel.
        origem = cipher.connect(self.caminho.as_uri() + "?mode=rw", uri=True,
                                 isolation_level=None, timeout=1)
        novo = None
        try:
            preparar_conexao(origem)
            if origem.execute("PRAGMA journal_mode=DELETE").fetchone()[0] != "delete":
                raise ErroSeguranca("Feche todas as versões antigas antes de proteger o banco.")
            origem.execute("BEGIN EXCLUSIVE")
            validar_esquema_legado(origem)
            if origem.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ErroSeguranca("O banco antigo está danificado. Restaure um backup antes de migrar.")
            novo = BancoDados(temporario, senha=nova, criar=True, backup_automatico=False)
            with novo.transacao():
                for tabela in ("Produtos", "Codigos_Barras", "Logs_Movimentacao"):
                    colunas = [r[1] for r in novo.conexao.execute(f"PRAGMA table_info({tabela})")]
                    antigas = [r[1] for r in origem.execute(f"PRAGMA table_info({tabela})")]
                    if colunas != antigas:
                        raise ErroSeguranca("Colunas do banco antigo incompatíveis; nenhuma substituição foi feita.")
                    campos = ",".join(colunas)  # apenas nomes vindos do esquema compilado acima
                    valores = ",".join("?" for _ in colunas)
                    novo.conexao.executemany(f"INSERT INTO {tabela} ({campos}) VALUES ({valores})",
                                            origem.execute(f"SELECT {campos} FROM {tabela}"))
                novo.conexao.execute("DELETE FROM sqlite_sequence")
                novo.conexao.executemany("INSERT INTO sqlite_sequence(name,seq) VALUES (?,?)",
                                        origem.execute("SELECT name,seq FROM sqlite_sequence"))
            conferir_integridade(novo.conexao)
            novo.criar_backup(self.caminho.parent / "backups")
            novo.fechar()
            novo = None
            # Testa de fato a reabertura com a senha antes de substituir o original.
            with closing(conectar(temporario, nova)) as verificacao:
                conferir_integridade(verificacao)
            origem.execute("ROLLBACK")
            origem.close()
            os.replace(temporario, self.caminho)
        finally:
            origem.close()
            if novo:
                novo.fechar()
            temporario.unlink(missing_ok=True)

    def _proteger_legados(self):
        arquivos = list((self.caminho.parent / "backups").glob("*.db"))
        arquivos += list(self.exportacoes.rglob("*.csv")) if self.exportacoes.is_dir() else []
        if self.legado.exists():
            # Este verificador não é mais necessário depois que o banco foi
            # autenticado. Preservar o tema e proteger também o hash antigo.
            from models.preferencias import Preferencias
            try:
                tema_legado = Preferencias(self.legado).obter_tema()
            except (ErroSeguranca, RuntimeError, *ERROS_BANCO, OSError):
                tema_legado = "dark"
            if not self.tema.exists():
                self.definir_tema(tema_legado)
            arquivos.append(self.legado)
        logs = [self.caminho.parent.parent / nome for nome in ("erros.log", "avisos.log")]
        arquivos += [arquivo for arquivo in logs if arquivo.exists()]
        for arquivo in arquivos:
            base = self.exportacoes if arquivo.suffix == ".csv" else self.caminho.parent
            if arquivo in logs:
                base = self.caminho.parent.parent
            if arquivo.is_symlink() or not arquivo.resolve().is_relative_to(base.resolve()):
                raise ErroSeguranca("Uma pasta de arquivos antigos contém um link inesperado.")
            with arquivo.open("rb") as entrada:
                cabecalho = entrada.read(16)
            if arquivo.suffix in (".csv", ".log") or arquivo == self.legado or cabecalho == CABECALHO_SQLITE:
                if any(arquivo.with_name(arquivo.name + s).exists() for s in ("-wal", "-journal")):
                    raise ErroSeguranca("Um backup antigo está aberto. Feche-o para concluir sua proteção.")
                proteger_arquivo(self.banco.conexao, arquivo)

    def verificar_senha(self, senha):
        try:
            with closing(conectar(self.caminho, senha)) as con:
                con.execute("SELECT count(*) FROM Produtos").fetchone()
            return True
        except (ValueError, *ERROS_BANCO):
            return False

    def alterar_senha(self, antiga, nova, confirmacao):
        if self.banco is None:
            raise ErroSeguranca("Desbloqueie o software primeiro.")
        validar_nova_senha(nova, confirmacao)
        if not self.verificar_senha(antiga):
            raise ValueError("A senha atual está incorreta.")
        if antiga == nova:
            raise ValueError("Escolha uma senha diferente da atual.")
        con = self.banco.conexao
        if con.in_transaction:
            raise ErroSeguranca("Conclua a operação de estoque antes de alterar a senha.")
        # rekey é transacional no SQLCipher. DELETE evita chaves diferentes entre
        # páginas antigas do WAL e o arquivo principal durante a troca.
        if con.execute("PRAGMA journal_mode=DELETE").fetchone()[0] != "delete":
            raise ErroSeguranca("Feche outras conexões antes de alterar a senha.")
        try:
            con.reset_key(nova)
            with closing(conectar(self.caminho, nova)) as teste:
                conferir_integridade(teste)
        except BaseException:
            # Não continuar operando com uma conexão cujo estado da chave ficou
            # incerto. A transação nativa é recuperada na próxima abertura.
            self.fechar()
            raise
        finally:
            if self.banco is not None:
                con.execute("PRAGMA journal_mode=WAL")

    def obter_tema(self):
        try:
            if self.tema.stat().st_size > 128:
                return "dark"
            valor = json.loads(self.tema.read_text(encoding="utf-8")).get("tema")
            return valor if valor in ("light", "dark") else "dark"
        except (OSError, ValueError, AttributeError):
            return "dark"

    def definir_tema(self, tema):
        if self.banco is None or tema not in ("light", "dark"):
            raise ValueError("Desbloqueie o programa e selecione um tema válido.")
        temporario = self.tema.with_name(".tema_" + uuid4().hex + ".json")
        try:
            temporario.write_text(json.dumps({"tema": tema}), encoding="utf-8")
            os.replace(temporario, self.tema)
        finally:
            temporario.unlink(missing_ok=True)

    def fechar(self):
        try:
            if self.banco:
                self.banco.fechar()
        finally:
            self.banco = None
            if self.trava:
                self.trava.fechar()
                self.trava = None
