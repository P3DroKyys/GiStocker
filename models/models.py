"""
Camada de Modelo (M do MVC): conexão com o SQLite e acesso a dados.

Estrutura deste módulo:
  * BancoDados ................ abre a conexão, cria as tabelas e controla transações.
  * Produto / CodigoBarras / LogMovimentacao ... dataclasses que representam linhas.
  * RepositorioProdutos ....... CRUD e busca inteligente da tabela Produtos.
  * RepositorioCodigosBarras .. vínculo 1:N (vários códigos -> um único produto).
  * RepositorioLogs ........... histórico de movimentações e suporte ao "desfazer".
  * RepositorioAlteracoes ..... auditoria das edições de cadastro (antes → depois).
  * RepositorioRelatorios ..... consultas agregadas usadas pelo dashboard.

Nenhuma regra de negócio vive aqui: os repositórios apenas leem e gravam.
As regras (custo médio ponderado, bloqueio de estoque negativo, desfazer)
ficam em controllers/controllers.py.

Observação sobre o esquema: além dos campos pedidos, Logs_Movimentacao guarda
``estoque_anterior``, ``custo_anterior`` e ``cancelado``. Os dois primeiros são
um "instantâneo" do produto ANTES da movimentação, o que torna o desfazer
exato para qualquer tipo (inclusive Ajuste). ``cancelado`` marca logs desfeitos
sem apagá-los, preservando a auditoria.
"""
from __future__ import annotations

import sqlite3
import sqlcipher3 as cipher
import math
from datetime import datetime
from uuid import uuid4
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import config
from utils.texto import normalizar_texto
from models.seguranca import (conectar, preparar_conexao, conferir_integridade,
                              copiar_protegido, validar_esquema_legado)

# --------------------------------------------------------------------------- #
# Esquema do banco
# --------------------------------------------------------------------------- #
SQL_CRIAR_TABELAS = """
CREATE TABLE IF NOT EXISTS Produtos (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    nome             TEXT    NOT NULL,
    marca            TEXT    NOT NULL,
    categoria        TEXT    NOT NULL,
    estoque_atual    INTEGER NOT NULL DEFAULT 0,
    preco_venda_base REAL    NOT NULL DEFAULT 0,
    custo_medio      REAL    NOT NULL DEFAULT 0,
    data_cadastro    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Relação 1:N: vários códigos (embalagens promocionais, kits) -> um produto.
CREATE TABLE IF NOT EXISTS Codigos_Barras (
    codigo     TEXT    PRIMARY KEY,
    produto_id INTEGER NOT NULL REFERENCES Produtos(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_codigos_produto ON Codigos_Barras(produto_id);

CREATE TABLE IF NOT EXISTS Logs_Movimentacao (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id       INTEGER NOT NULL REFERENCES Produtos(id),
    tipo             TEXT    NOT NULL CHECK (tipo IN ('Entrada', 'Saída', 'Ajuste')),
    quantidade       INTEGER NOT NULL,
    custo_no_momento REAL    NOT NULL DEFAULT 0,
    data_hora        TEXT    NOT NULL,
    estoque_anterior INTEGER NOT NULL DEFAULT 0,
    custo_anterior   REAL    NOT NULL DEFAULT 0,
    cancelado        INTEGER NOT NULL DEFAULT 0,
    observacao       TEXT
);
CREATE INDEX IF NOT EXISTS idx_logs_produto ON Logs_Movimentacao(produto_id);
CREATE INDEX IF NOT EXISTS idx_logs_data    ON Logs_Movimentacao(data_hora);
"""

# Esquema v4. Sem FK para Produtos: o registro de uma exclusão sobrevive ao produto,
# por isso o nome é guardado como instantâneo. ``operacao`` agrupa os campos de uma edição.
SQL_LOGS_ALTERACAO = """
CREATE TABLE IF NOT EXISTS Logs_Alteracao (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora      TEXT    NOT NULL,
    operacao       TEXT    NOT NULL,
    produto_id     INTEGER NOT NULL,
    produto_nome   TEXT    NOT NULL,
    acao           TEXT    NOT NULL CHECK (acao IN ('Edição', 'Exclusão', 'Código')),
    campo          TEXT    NOT NULL,
    valor_anterior TEXT,
    valor_novo     TEXT,
    descricao      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alteracoes_produto ON Logs_Alteracao(produto_id);
"""


# --------------------------------------------------------------------------- #
# Dataclasses (representam uma linha de cada tabela)
# --------------------------------------------------------------------------- #
@dataclass
class Produto:
    id: int | None
    nome: str
    marca: str
    categoria: str
    estoque_atual: int = 0
    preco_venda_base: float = 0.0
    custo_medio: float = 0.0
    codigos: list[str] = field(default_factory=list)   # preenchido nas consultas
    data_cadastro: str | None = None

    @property
    def valor_investido(self) -> float:
        return self.estoque_atual * self.custo_medio

    @property
    def receita_potencial(self) -> float:
        return self.estoque_atual * self.preco_venda_base


@dataclass
class CodigoBarras:
    codigo: str
    produto_id: int


@dataclass
class LogMovimentacao:
    id: int | None
    produto_id: int
    tipo: str                     # "Entrada", "Saída" ou "Ajuste"
    quantidade: int               # no Ajuste é o delta (novo - anterior), pode ser negativo
    custo_no_momento: float       # Entrada: custo unitário; Saída: custo médio; Ajuste: novo custo
    data_hora: str                # "AAAA-MM-DD HH:MM:SS"
    estoque_anterior: int = 0
    custo_anterior: float = 0.0
    cancelado: bool = False
    observacao: str | None = None

    @property
    def estoque_posterior(self) -> int:
        """Estoque resultante após esta movimentação."""
        if self.tipo == config.TIPO_SAIDA:
            return self.estoque_anterior - self.quantidade
        return self.estoque_anterior + self.quantidade


@dataclass
class LogAlteracao:
    id: int | None
    data_hora: str                # "AAAA-MM-DD HH:MM:SS"
    operacao: str                 # mesmo valor para todos os campos de uma edição/exclusão
    produto_id: int
    produto_nome: str             # nome no momento da alteração
    acao: str                     # "Edição", "Exclusão" ou "Código"
    campo: str
    valor_anterior: str | None
    valor_novo: str | None
    descricao: str                # ex.: "Preço alterado de R$ 50,00 para R$ 55,00"


# --------------------------------------------------------------------------- #
# Conexão
# --------------------------------------------------------------------------- #
class _SomaInteira:
    """Totais não negativos sem overflow; texto preserva todos os dígitos no SQLite."""
    def __init__(self):
        self.total = 0

    def step(self, valor):
        if valor is not None:
            self.total += int(valor)

    def finalize(self):
        return str(self.total)


class BancoDados:
    """Gerencia a conexão SQLite, a criação do esquema e as transações."""

    VERSAO_ESQUEMA = 4

    def __init__(self, caminho: str | Path = config.CAMINHO_BANCO,
                 backup_automatico: bool = True, timeout: float = 5.0,
                 *, senha: str | None = None, criar: bool = False,
                 permitir_legado: bool = False) -> None:
        self.caminho = str(caminho)
        self._em_transacao = False
        self._savepoint = 0
        self.ultimo_backup: Path | None = None
        self.criptografado = senha is not None
        self._fechado = False
        self._indice_pesquisa = None
        self._versao_pesquisa = None
        if not self.criptografado and self.caminho != ":memory:" and not permitir_legado:
            raise ValueError("Um banco em disco exige autenticação e criptografia.")
        existente = self.caminho != ":memory:" and Path(self.caminho).is_file() and Path(self.caminho).stat().st_size > 0
        if self.caminho != ":memory:":
            Path(self.caminho).parent.mkdir(parents=True, exist_ok=True)

        # isolation_level=None => modo autocommit. As transações são abertas
        # explicitamente em transacao(), evitando commits "escondidos".
        self.conexao = (conectar(self.caminho, senha, criar=criar) if self.criptografado else
                        sqlite3.connect(self.caminho, isolation_level=None, timeout=timeout))
        try:
            self.conexao.row_factory = cipher.Row if self.criptografado else sqlite3.Row
            preparar_conexao(self.conexao)
            self.conexao.execute("PRAGMA foreign_keys = ON")
            if self.criptografado and existente:
                validar_esquema_legado(self.conexao)
                conferir_integridade(self.conexao)
            versao = self.conexao.execute("PRAGMA user_version").fetchone()[0]
            if versao > self.VERSAO_ESQUEMA:
                raise RuntimeError("Este banco pertence a uma versão mais recente do GiStocker. Atualize o aplicativo.")
            # Snapshot consistente inclui dados no WAL. Nunca copiar apenas o .db.
            if existente and backup_automatico:
                self.ultimo_backup = self.criar_backup()
            if self.caminho != ":memory:":
                self.conexao.execute("PRAGMA journal_mode = WAL")
            self.conexao.execute("PRAGMA synchronous = FULL")
            self.conexao.create_function("normalizar", 1, normalizar_texto, deterministic=True)
            self.conexao.create_aggregate("soma_inteira", 1, _SomaInteira)
            self.criar_tabelas()
        except BaseException:
            self.conexao.close()
            raise

    def criar_tabelas(self) -> None:
        """Migração inicial não destrutiva; preserva registros dos bancos legados."""
        # Não usar executescript: ele pode confirmar implicitamente a transação.
        with self.transacao():
            versao = self.conexao.execute("PRAGMA user_version").fetchone()[0]
            if versao > self.VERSAO_ESQUEMA:
                raise RuntimeError("Versão de banco não suportada.")
            if versao == 0:
                for instrucao in SQL_CRIAR_TABELAS.split(";"):
                    if instrucao.strip():
                        self.conexao.execute(instrucao)
                self.conexao.execute("PRAGMA user_version = 1")
            if versao < 2:
                from multicanal.esquema import migrar
                # Testes de recuperação podem rebaixar user_version de uma cópia.
                if not self.conexao.execute("SELECT 1 FROM sqlite_master WHERE name='Config_Multicanal'").fetchone():
                    migrar(self.conexao)
                else:
                    self.conexao.execute("PRAGMA user_version = 2")
            if versao < 3:
                from multicanal.esquema import INDICES
                for nome, instrucao in INDICES.items():
                    if not self.conexao.execute('SELECT 1 FROM sqlite_master WHERE name=?', (nome,)).fetchone():
                        self.conexao.execute(instrucao)
                self.conexao.execute('PRAGMA user_version = 3')
            if versao < 4:
                for instrucao in SQL_LOGS_ALTERACAO.split(";"):
                    if instrucao.strip():
                        self.conexao.execute(instrucao)
                self.conexao.execute('PRAGMA user_version = 4')

    def criar_backup(self, pasta: str | Path | None = None) -> Path:
        """Cria snapshot SQLite consistente, único e verificado, sem sobrescrever."""
        if self.conexao.in_transaction:
            raise RuntimeError("Conclua a transação antes de criar um backup.")
        if pasta is None:
            if self.caminho == ":memory:":
                raise ValueError("Informe a pasta de backup para um banco em memória.")
            pasta = Path(self.caminho).resolve().parent / "backups"
        pasta = Path(pasta)
        pasta.mkdir(parents=True, exist_ok=True)
        nome = f"estoque_{datetime.now():%Y%m%d_%H%M%S_%f}_{uuid4().hex}.db"
        destino = pasta / nome
        if self.criptografado:
            return copiar_protegido(self.conexao, destino)
        # Criação exclusiva evita sobrescrever até em chamadas simultâneas.
        with destino.open("xb"):
            pass
        try:
            copia = sqlite3.connect(destino)
            try:
                self.conexao.backup(copia)
                resultado = copia.execute("PRAGMA integrity_check").fetchall()
                if resultado != [("ok",)]:
                    raise RuntimeError("O backup não passou na verificação de integridade.")
            finally:
                copia.close()
        except BaseException:
            # Só remove o arquivo exclusivo criado nesta chamada e ainda inválido.
            destino.unlink(missing_ok=True)
            raise
        return destino

    @contextmanager
    def transacao(self) -> Iterator[sqlite3.Connection]:
        """Agrupa várias gravações em uma única transação atômica.

        Contextos aninhados usam SAVEPOINT e podem reverter isoladamente.
        O contexto externo confirma todas as operações. Exemplo::

            with bd.transacao():
                repositorio_produtos.atualizar_estoque_custo(...)
                repositorio_logs.inserir(...)
        """
        if self._em_transacao:
            self._savepoint += 1
            nome = f"gestor_{self._savepoint}"
            self.conexao.execute(f"SAVEPOINT {nome}")
            try:
                yield self.conexao
            except BaseException:
                self.conexao.execute(f"ROLLBACK TO SAVEPOINT {nome}")
                raise
            finally:
                self.conexao.execute(f"RELEASE SAVEPOINT {nome}")
            return
        self.conexao.execute("BEGIN IMMEDIATE")
        self._em_transacao = True
        try:
            yield self.conexao
            self.conexao.execute("COMMIT")
        except BaseException:
            if self.conexao.in_transaction:
                self.conexao.execute("ROLLBACK")
            raise
        finally:
            self._em_transacao = False

    # Atalhos de consulta -------------------------------------------------- #
    @contextmanager
    def leitura_consistente(self):
        """Um snapshot para várias consultas; em WAL não bloqueia outros escritores."""
        if self.conexao.in_transaction:
            yield
            return
        self.conexao.execute("BEGIN")
        try:
            yield
        finally:
            self.conexao.execute("ROLLBACK")

    def executar(self, sql: str, parametros: tuple | list = ()) -> sqlite3.Cursor:
        return self.conexao.execute(sql, parametros)

    def buscar_um(self, sql: str, parametros: tuple | list = ()) -> sqlite3.Row | None:
        return self.conexao.execute(sql, parametros).fetchone()

    def buscar_todos(self, sql: str, parametros: tuple | list = ()) -> list[sqlite3.Row]:
        return self.conexao.execute(sql, parametros).fetchall()

    def fechar(self) -> None:
        self._indice_pesquisa = None
        self._versao_pesquisa = None
        if not self._fechado:
            self.conexao.close()
            self._fechado = True


# --------------------------------------------------------------------------- #
# Conversores linha -> dataclass
# --------------------------------------------------------------------------- #
def _para_produto(linha: sqlite3.Row) -> Produto:
    chaves = linha.keys()
    codigos_texto = linha["codigos"] if "codigos" in chaves else None
    return Produto(
        id=linha["id"],
        nome=linha["nome"],
        marca=linha["marca"],
        categoria=linha["categoria"],
        estoque_atual=int(linha["estoque_atual"]),
        preco_venda_base=float(linha["preco_venda_base"]),
        custo_medio=float(linha["custo_medio"]),
        codigos=[c for c in (codigos_texto or "").split(";") if c],
        data_cadastro=linha["data_cadastro"] if "data_cadastro" in chaves else None,
    )


def _para_log(linha: sqlite3.Row) -> LogMovimentacao:
    return LogMovimentacao(
        id=linha["id"],
        produto_id=linha["produto_id"],
        tipo=linha["tipo"],
        quantidade=int(linha["quantidade"]),
        custo_no_momento=float(linha["custo_no_momento"]),
        data_hora=linha["data_hora"],
        estoque_anterior=int(linha["estoque_anterior"]),
        custo_anterior=float(linha["custo_anterior"]),
        cancelado=bool(linha["cancelado"]),
        observacao=linha["observacao"],
    )


# Consulta base de produto: já traz os códigos de barras concatenados por ';'.
SQL_PRODUTO_BASE = """
SELECT p.*,
       (SELECT GROUP_CONCAT(c.codigo, ';')
          FROM Codigos_Barras c
         WHERE c.produto_id = p.id) AS codigos
  FROM Produtos p
"""


# --------------------------------------------------------------------------- #
# Repositório: Produtos
# --------------------------------------------------------------------------- #
class RepositorioProdutos:
    def __init__(self, bd: BancoDados) -> None:
        self.bd = bd

    def pesquisar(self, termo):
        """Índice em memória, invalidado por gravações desta ou de outra conexão."""
        from utils.busca import IndiceProdutos
        con = self.bd.conexao
        versao = (con.total_changes, con.execute('PRAGMA data_version').fetchone()[0])
        if con.in_transaction:
            # Um rollback não pode deixar registros não confirmados no cache.
            return IndiceProdutos(self.listar_todos()).pesquisar(termo)
        if self.bd._indice_pesquisa is None or versao != self.bd._versao_pesquisa:
            self.bd._indice_pesquisa = IndiceProdutos(self.listar_todos())
            self.bd._versao_pesquisa = versao
        return self.bd._indice_pesquisa.pesquisar(termo)

    def inserir(self, produto: Produto) -> int:
        cursor = self.bd.executar(
            """INSERT INTO Produtos
                   (nome, marca, categoria, estoque_atual, preco_venda_base, custo_medio)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (produto.nome, produto.marca, produto.categoria, produto.estoque_atual,
             produto.preco_venda_base, produto.custo_medio),
        )
        return int(cursor.lastrowid)

    def buscar_por_id(self, produto_id: int) -> Produto | None:
        linha = self.bd.buscar_um(SQL_PRODUTO_BASE + " WHERE p.id = ?", (produto_id,))
        return _para_produto(linha) if linha else None

    def atualizar_estoque_custo(self, produto_id: int, estoque_atual: int, custo_medio: float) -> None:
        self.bd.executar(
            "UPDATE Produtos SET estoque_atual = ?, custo_medio = ? WHERE id = ?",
            (estoque_atual, custo_medio, produto_id),
        )

    def atualizar_dados(self, produto: Produto) -> None:
        """Atualiza nome/marca/categoria/preço (Admin e importação por planilha)."""
        self.bd.executar(
            "UPDATE Produtos SET nome = ?, marca = ?, categoria = ?, preco_venda_base = ? WHERE id = ?",
            (produto.nome, produto.marca, produto.categoria, produto.preco_venda_base, produto.id),
        )

    def ids_com_vinculos_externos(self, produto_ids: list[int]) -> set[int]:
        """Ids com anúncios, pedidos, reservas, incidentes ou kits, que impedem a exclusão."""
        marcadores = ",".join("?" for _ in produto_ids)
        linhas = self.bd.buscar_todos(
            f"""SELECT produto_id FROM Vinculos_SKU WHERE produto_id IN ({marcadores})
                UNION SELECT produto_id FROM Reservas WHERE produto_id IN ({marcadores})
                UNION SELECT produto_id FROM Itens_Pedido_Externo WHERE produto_id IN ({marcadores})
                UNION SELECT produto_id FROM Incidentes_Sync WHERE produto_id IN ({marcadores})
                UNION SELECT kit FROM Componentes_Kit WHERE kit IN ({marcadores}) OR componente IN ({marcadores})""",
            produto_ids * 6,
        )
        return {int(l[0]) for l in linhas}

    def excluir(self, produto_ids: list[int]) -> dict[int, int]:
        """Remove os produtos com códigos, movimentações e livro de eventos.

        Devolve {produto_id: movimentações removidas}. Deve rodar dentro de
        ``transacao()``: o trigger que torna Eventos_Estoque imutável só é
        suspenso nesta transação (como na restauração de backup) e volta antes
        do COMMIT; qualquer falha o restaura no ROLLBACK.
        """
        from multicanal.esquema import TRIGGERS
        marcadores = ",".join("?" for _ in produto_ids)
        removidas = {int(l[0]): int(l[1]) for l in self.bd.buscar_todos(
            f"SELECT produto_id, count(*) FROM Logs_Movimentacao WHERE produto_id IN ({marcadores}) GROUP BY produto_id",
            produto_ids)}
        self.bd.executar("DROP TRIGGER eventos_sem_delete")
        self.bd.executar(f"DELETE FROM Eventos_Estoque WHERE produto_id IN ({marcadores})", produto_ids)
        self.bd.executar(TRIGGERS["eventos_sem_delete"])
        # Codigos_Barras sai por ON DELETE CASCADE.
        for tabela in ("Logs_Movimentacao", "Politicas_Alocacao", "Cobertura_Produto_Canal",
                       "Estado_Alocacao"):
            self.bd.executar(f"DELETE FROM {tabela} WHERE produto_id IN ({marcadores})", produto_ids)
        self.bd.executar(f"DELETE FROM Produtos WHERE id IN ({marcadores})", produto_ids)
        return {produto_id: removidas.get(produto_id, 0) for produto_id in produto_ids}

    def listar_todos(self, limite=None, offset=0) -> list[Produto]:
        sql = SQL_PRODUTO_BASE + " ORDER BY p.nome COLLATE NOCASE, p.id"
        parametros = ()
        if limite is not None:
            sql += ' LIMIT ? OFFSET ?'
            parametros = (limite, offset)
        linhas = self.bd.buscar_todos(sql, parametros)
        return [_para_produto(l) for l in linhas]

    def buscar(self, termo: str, limite: int | None = None, offset=0) -> list[Produto]:
        """Busca inteligente por "split-string LIKE".

        O termo é normalizado e dividido em palavras; TODAS precisam aparecer
        (em qualquer ordem) no nome, marca, categoria ou em um código de barras.
        Ex.: "refil lily" encontra "Refil Hidratante Lily".
        """
        palavras = normalizar_texto(termo).split()
        sql = SQL_PRODUTO_BASE
        parametros: list[Any] = []
        if palavras:
            condicoes = []
            for palavra in palavras:
                # %, _ e \ digitados são texto, nunca curingas do LIKE.
                literal = palavra.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                curinga = f"%{literal}%"
                condicoes.append(
                    "(normalizar(p.nome) LIKE ? ESCAPE '\\' OR normalizar(p.marca) LIKE ? ESCAPE '\\' "
                    "OR normalizar(p.categoria) LIKE ? ESCAPE '\\' "
                    "OR EXISTS (SELECT 1 FROM Codigos_Barras c "
                    "           WHERE c.produto_id = p.id AND c.codigo LIKE ? ESCAPE '\\'))"
                )
                parametros.extend([curinga] * 4)
            sql += " WHERE " + " AND ".join(condicoes)
        sql += " ORDER BY p.nome COLLATE NOCASE, p.id"
        if limite is not None:
            sql += " LIMIT ? OFFSET ?"
            parametros.extend((limite, offset))
        return [_para_produto(l) for l in self.bd.buscar_todos(sql, parametros)]

    def listar_para_exportacao(self) -> list[dict]:
        """Linhas prontas para virar DataFrame (estoque atual + valores calculados)."""
        linhas = self.bd.buscar_todos(
            """SELECT p.id, p.nome, p.marca, p.categoria,
                      (SELECT GROUP_CONCAT(c.codigo, ';') FROM Codigos_Barras c
                        WHERE c.produto_id = p.id) AS codigos_barras,
                      p.estoque_atual, p.custo_medio, p.preco_venda_base,
                      ROUND(p.estoque_atual * p.custo_medio, 2)      AS valor_investido,
                      ROUND(p.estoque_atual * p.preco_venda_base, 2) AS receita_potencial,
                      p.data_cadastro
                 FROM Produtos p
                ORDER BY p.nome COLLATE NOCASE"""
        )
        return [dict(l) for l in linhas]


# --------------------------------------------------------------------------- #
# Repositório: Códigos de barras (1:N)
# --------------------------------------------------------------------------- #
class RepositorioCodigosBarras:
    def __init__(self, bd: BancoDados) -> None:
        self.bd = bd

    def vincular(self, codigo: str, produto_id: int) -> None:
        self.bd.executar(
            "INSERT INTO Codigos_Barras (codigo, produto_id) VALUES (?, ?)", (codigo, produto_id)
        )

    def desvincular(self, codigo: str) -> None:
        self.bd.executar("DELETE FROM Codigos_Barras WHERE codigo = ?", (codigo,))

    def buscar_produto_id(self, codigo: str) -> int | None:
        """Resolve um código de barras para o id do produto (ou None)."""
        linha = self.bd.buscar_um("SELECT produto_id FROM Codigos_Barras WHERE codigo = ?", (codigo,))
        return int(linha["produto_id"]) if linha else None

    def listar_por_produto(self, produto_id: int) -> list[str]:
        linhas = self.bd.buscar_todos(
            "SELECT codigo FROM Codigos_Barras WHERE produto_id = ? ORDER BY codigo", (produto_id,)
        )
        return [l["codigo"] for l in linhas]


# --------------------------------------------------------------------------- #
# Repositório: Logs de movimentação
# --------------------------------------------------------------------------- #
class RepositorioLogs:
    def __init__(self, bd: BancoDados) -> None:
        self.bd = bd

    def inserir(self, log: LogMovimentacao) -> int:
        cursor = self.bd.executar(
            """INSERT INTO Logs_Movimentacao
                   (produto_id, tipo, quantidade, custo_no_momento, data_hora,
                    estoque_anterior, custo_anterior, cancelado, observacao)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (log.produto_id, log.tipo, log.quantidade, log.custo_no_momento, log.data_hora,
             log.estoque_anterior, log.custo_anterior, int(log.cancelado), log.observacao),
        )
        return int(cursor.lastrowid)

    def buscar_por_id(self, log_id: int) -> LogMovimentacao | None:
        linha = self.bd.buscar_um("SELECT * FROM Logs_Movimentacao WHERE id = ?", (log_id,))
        return _para_log(linha) if linha else None

    def ultimo_nao_cancelado(self) -> LogMovimentacao | None:
        """Último registro ainda válido (é o alvo do botão "Desfazer")."""
        linha = self.bd.buscar_um(
            "SELECT * FROM Logs_Movimentacao WHERE cancelado = 0 ORDER BY id DESC LIMIT 1"
        )
        return _para_log(linha) if linha else None

    def marcar_cancelado(self, log_id: int) -> None:
        self.bd.executar("UPDATE Logs_Movimentacao SET cancelado = 1 WHERE id = ?", (log_id,))

    def listar(self, limite: int | None = None, produto_id: int | None = None,
               incluir_cancelados: bool = True, antes_id=None) -> list[dict]:
        """Histórico (mais recente primeiro) já com nome/marca/categoria do produto."""
        sql = """
            SELECT l.*,
                   CASE WHEN l.tipo = ? THEN l.estoque_anterior - l.quantidade
                        ELSE l.estoque_anterior + l.quantidade END AS estoque_posterior,
                   p.nome AS produto_nome, p.marca AS produto_marca, p.categoria AS produto_categoria,
                   coalesce(e.origem, 'FISICO') AS origem, e.referencia, e.criado AS registrado_utc
              FROM Logs_Movimentacao l
              JOIN Produtos p ON p.id = l.produto_id
              LEFT JOIN Eventos_Estoque e ON e.id = (
                  SELECT id FROM Eventos_Estoque WHERE log_id=l.id ORDER BY id LIMIT 1)
        """
        parametros: list[Any] = [config.TIPO_SAIDA]
        condicoes = []
        if antes_id is not None:
            condicoes.append('l.id < ?')
            parametros.append(antes_id)
        if produto_id is not None:
            condicoes.append("l.produto_id = ?")
            parametros.append(produto_id)
        if not incluir_cancelados:
            condicoes.append("l.cancelado = 0")
        if condicoes:
            sql += " WHERE " + " AND ".join(condicoes)
        sql += " ORDER BY l.id DESC"
        if limite:
            sql += " LIMIT ?"
            parametros.append(limite)
        linhas = self.bd.buscar_todos(sql, parametros)
        resultado = []
        for linha in linhas:
            registro = dict(linha)
            registro["cancelado"] = bool(registro["cancelado"])
            resultado.append(registro)
        return resultado


# --------------------------------------------------------------------------- #
# Repositório: auditoria de alterações de cadastro
# --------------------------------------------------------------------------- #
class RepositorioAlteracoes:
    def __init__(self, bd: BancoDados) -> None:
        self.bd = bd

    def inserir(self, registros: list[LogAlteracao]) -> None:
        self.bd.conexao.executemany(
            """INSERT INTO Logs_Alteracao
                   (data_hora, operacao, produto_id, produto_nome, acao, campo,
                    valor_anterior, valor_novo, descricao)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(r.data_hora, r.operacao, r.produto_id, r.produto_nome, r.acao, r.campo,
              r.valor_anterior, r.valor_novo, r.descricao) for r in registros],
        )

    def listar(self, limite: int, produto_id: int | None = None, antes_id=None) -> list[dict]:
        """Mais recente primeiro; inclui registros de produtos já excluídos."""
        sql = "SELECT * FROM Logs_Alteracao"
        parametros: list[Any] = []
        condicoes = []
        if antes_id is not None:
            condicoes.append("id < ?")
            parametros.append(antes_id)
        if produto_id is not None:
            condicoes.append("produto_id = ?")
            parametros.append(produto_id)
        if condicoes:
            sql += " WHERE " + " AND ".join(condicoes)
        sql += " ORDER BY id DESC LIMIT ?"
        parametros.append(limite)
        return [dict(l) for l in self.bd.buscar_todos(sql, parametros)]


# --------------------------------------------------------------------------- #
# Repositório: consultas agregadas do dashboard
# --------------------------------------------------------------------------- #
class RepositorioRelatorios:
    CAMPOS_AGRUPAMENTO = ("marca", "categoria")   # lista branca (evita injeção)

    def __init__(self, bd: BancoDados) -> None:
        self.bd = bd

    def totais_estoque(self) -> dict:
        linhas = self.bd.buscar_todos('SELECT estoque_atual, custo_medio, preco_venda_base FROM Produtos')
        # Inteiros Python somam sem o overflow de SUM(INTEGER) do SQLite.
        try:
            investido = math.fsum(l['estoque_atual'] * l['custo_medio'] for l in linhas)
            receita = math.fsum(l['estoque_atual'] * l['preco_venda_base'] for l in linhas)
        except OverflowError:
            raise ValueError('Valores cadastrados excedem o limite dos indicadores. Revise os custos e preços.') from None
        if not math.isfinite(investido) or not math.isfinite(receita):
            raise ValueError('Há valores não finitos no estoque. Revise os custos e preços cadastrados.')
        return dict(total_produtos=len(linhas), total_itens=sum(int(l['estoque_atual']) for l in linhas),
                    valor_investido=investido, receita_potencial=receita)

    def volume_por_dia(self, data_inicial: str) -> list[sqlite3.Row]:
        """Soma de Entradas e Saídas por dia (Ajustes não entram)."""
        return self.bd.buscar_todos(
            """SELECT substr(data_hora, 1, 10) AS dia, tipo, soma_inteira(quantidade) AS total
                 FROM Logs_Movimentacao
                WHERE cancelado = 0 AND tipo IN (?, ?) AND data_hora >= ?
                GROUP BY dia, tipo""",
            (config.TIPO_ENTRADA, config.TIPO_SAIDA, data_inicial),
        )

    def saidas_por_campo(self, campo: str) -> list[sqlite3.Row]:
        """Total de unidades vendidas agrupadas por 'marca' ou 'categoria'."""
        if campo not in self.CAMPOS_AGRUPAMENTO:
            raise ValueError(f"Campo de agrupamento inválido: {campo}")
        return self.bd.buscar_todos(
            f"""SELECT p.{campo} AS chave, soma_inteira(l.quantidade) AS total
                  FROM Logs_Movimentacao l
                  JOIN Produtos p ON p.id = l.produto_id
                 WHERE l.cancelado = 0 AND l.tipo = ?
                 GROUP BY chave
                 ORDER BY length(total) DESC, total DESC""",
            (config.TIPO_SAIDA,),
        )

    def ranking_saidas_por_produto(self, limite: int) -> list[sqlite3.Row]:
        return self.bd.buscar_todos(
            """SELECT p.id, p.nome, p.marca, p.estoque_atual,
                      soma_inteira(l.quantidade) AS total_saidas, COUNT(l.id) AS qtd_movimentacoes
                 FROM Logs_Movimentacao l
                 JOIN Produtos p ON p.id = l.produto_id
                WHERE l.cancelado = 0 AND l.tipo = ?
                GROUP BY p.id
                ORDER BY length(total_saidas) DESC, total_saidas DESC, qtd_movimentacoes DESC
                LIMIT ?""",
            (config.TIPO_SAIDA, limite),
        )

    def produtos_sem_saida_desde(self, data_limite: str) -> list[sqlite3.Row]:
        """Produtos com estoque cuja última saída (ou, se nunca vendeu, a primeira
        movimentação / data de cadastro) é anterior a ``data_limite``."""
        return self.bd.buscar_todos(
            """SELECT p.id, p.nome, p.marca, p.categoria, p.estoque_atual, p.data_cadastro,
                      MAX(CASE WHEN l.tipo = ? THEN l.data_hora END) AS ultima_saida,
                      MIN(l.data_hora) AS primeira_movimentacao,
                      COALESCE(MAX(CASE WHEN l.tipo = ? THEN l.data_hora END),
                               MIN(l.data_hora), p.data_cadastro) AS referencia
                 FROM Produtos p
                 LEFT JOIN Logs_Movimentacao l ON l.produto_id = p.id AND l.cancelado = 0
                WHERE p.estoque_atual > 0
                GROUP BY p.id
               HAVING referencia < ?
                ORDER BY referencia ASC""",
            (config.TIPO_SAIDA, config.TIPO_SAIDA, data_limite),
        )
