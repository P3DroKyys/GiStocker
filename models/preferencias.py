"""Leitura restrita das configurações antigas para migrar a instalação."""
from contextlib import closing
import hashlib
import hmac
from pathlib import Path
import secrets
import sqlcipher3 as sqlite3

import config


ITERACOES = 600_000


class ErroPreferencias(RuntimeError):
    """Arquivo de configurações incompleto ou incompatível; nunca libera acesso."""


def _hash_senha(senha: str) -> str:
    sal = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, ITERACOES)
    return f"pbkdf2_sha256${ITERACOES}${sal.hex()}${digest.hex()}"


def _confere_senha(senha: str, registro: str) -> bool:
    try:
        algoritmo, ciclos, sal, digest = registro.split("$")
        ciclos = int(ciclos)
        sal, digest = bytes.fromhex(sal), bytes.fromhex(digest)
        if algoritmo != "pbkdf2_sha256" or ciclos != ITERACOES or len(sal) != 16 or len(digest) != 32:
            raise ValueError
    except (ValueError, TypeError, AttributeError) as falha:
        raise ErroPreferencias("A configuração de acesso está inválida. Restaure o arquivo de configurações.") from falha
    if not isinstance(senha, str) or not senha or len(senha) > 256:
        return False
    calculado = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, ciclos)
    return hmac.compare_digest(calculado, digest)


class Preferencias:
    """Leitor somente para autenticar a migração de instalações anteriores.

    Nunca cria configurações, nunca restaura senha inicial e não controla uma
    sessão protegida. A nova autenticação está em models.seguranca.Cofre.
    """
    def __init__(self, caminho):
        self.caminho = Path(caminho).resolve()
        if not self.caminho.is_file():
            raise ErroPreferencias("As configurações antigas estão ausentes. Restaure-as antes de migrar.")
        with closing(self._conectar()) as con:
            self._ler(con)

    def _conectar(self):
        con = sqlite3.connect(self.caminho.as_uri() + "?mode=ro", uri=True, timeout=2)
        if hasattr(con, "enable_load_extension"):
            con.enable_load_extension(False)
        con.execute("PRAGMA trusted_schema=OFF")
        con.execute("PRAGMA temp_store=MEMORY")
        return con

    @staticmethod
    def _ler(con):
        objetos = con.execute("SELECT type, name FROM sqlite_master").fetchall()
        if objetos != [("table", "Preferencias")]:
            raise ErroPreferencias("A configuração antiga possui uma estrutura inesperada.")
        registro = con.execute("SELECT senha_hash, tema FROM Preferencias WHERE id=1").fetchone()
        if registro is None or registro[1] not in ("light", "dark"):
            raise ErroPreferencias("As configurações antigas estão incompletas.")
        _confere_senha("", registro[0])
        return registro

    def verificar_senha(self, senha):
        with closing(self._conectar()) as con:
            return _confere_senha(senha, self._ler(con)[0])

    def obter_tema(self):
        with closing(self._conectar()) as con:
            return self._ler(con)[1]
