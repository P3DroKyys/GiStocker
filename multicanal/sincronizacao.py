"""Worker recuperável. O único adaptador fornecido é um marketplace fictício."""
import random
import time
from concurrent.futures import ThreadPoolExecutor, wait

from models.models import BancoDados
from multicanal.motor import Motor


class FalhaRemota(Exception):
    def __init__(self, tipo, retry_after=0):
        self.tipo, self.retry_after = tipo, retry_after


class MarketplaceSimulado:
    def __init__(self, banco):
        self.bd = banco
        self.falha = None

    def observar(self, remoto):
        if self.falha in ('SEM_INTERNET','TOKEN_VENCIDO','RATE_LIMIT'):
            raise FalhaRemota(self.falha,30 if self.falha=='RATE_LIMIT' else 0)
        return self.bd.conexao.execute('SELECT quantidade FROM Catalogo_Remoto WHERE id=?',(remoto,)).fetchone()[0]

    def publicar(self, remoto, quantidade):
        self.observar(remoto)
        # Commit externo separado do ack local para testar resultado incerto.
        with self.bd.transacao():
            self.bd.conexao.execute('UPDATE Catalogo_Remoto SET quantidade=? WHERE id=?',(quantidade,remoto))
        if self.falha=='TIMEOUT_APOS_ENVIO':
            raise FalhaRemota('TIMEOUT_APOS_ENVIO')


class Worker:
    def __init__(self, motor, adaptador):
        self.m = motor
        self.api = adaptador
        self.retomar_em = 0
        self.falhas = 0
        self._ciclo = None
        self._encerrando = False
        with self.m.bd.transacao():
            self.m.con.execute("UPDATE Outbox_Comandos SET estado='INCERTO' WHERE estado='ENVIANDO'")
            self.m.con.execute("UPDATE Estado_SKU_Canal SET incerta=1 WHERE remoto IN(SELECT remoto FROM Outbox_Comandos WHERE estado='INCERTO')")
            self.m.con.execute("UPDATE Outbox_Comandos SET proxima=0 WHERE estado='RETENTAR'")

    def passo(self, encerrar=False):
        if time.monotonic()<self.retomar_em:
            return
        if self._ciclo is not None and encerrar != self._encerrando:
            self._ciclo.close()
            self._ciclo = None
        if self._ciclo is None:
            self._encerrando = encerrar
            self._ciclo = self._executar_ciclo(encerrar)
        prazo = time.monotonic() + .080
        try:
            while time.monotonic() < prazo:
                next(self._ciclo)
        except StopIteration:
            self._ciclo = None
        except FalhaRemota as erro:
            self._ciclo = None
            self.falhas += 1
            atraso = max(erro.retry_after,min(300,2**min(self.falhas,8))+random.random())
            self.retomar_em = time.monotonic()+atraso
            with self.m.bd.transacao():
                self.m.incidente(erro.tipo,'conector-simulado')

    def _executar_ciclo(self, encerrar):
        # Cada pausa ocorre fora de transações. Publicação e ack permanecem separados.
        for entrada in self.m.linhas("SELECT chave FROM Inbox_Eventos WHERE estado='PENDENTE' ORDER BY recebido,chave"):
            self.m.processar_inbox(entrada['chave'])
            yield
        # Observação antecede qualquer aumento, inclusive após reinício.
        for remoto in self.m.linhas('SELECT remoto FROM Estado_SKU_Canal ORDER BY remoto'):
            e = self.m.linha('SELECT * FROM Estado_SKU_Canal WHERE remoto=?', (remoto['remoto'],))
            quantidade = self.api.observar(e['remoto'])
            if not e['incerta'] and quantidade == e['confirmada'] == e['observada'] == e['exposta']:
                yield
                continue
            with self.m.bd.transacao():
                if quantidade!=e['confirmada'] and not e['incerta']:
                    pid=self.m.linha('SELECT produto_id FROM Vinculos_SKU WHERE remoto=?',(e['remoto'],))['produto_id']
                    self.m.incidente('ESTOQUE_REMOTO_ALTERADO',e['remoto'],pid)
                self.m.con.execute('UPDATE Estado_SKU_Canal SET observada=?,confirmada=?,exposta=?,incerta=0 WHERE remoto=?',(quantidade,quantidade,quantidade,e['remoto']))
                self.m.con.execute("UPDATE Outbox_Comandos SET estado=CASE WHEN quantidade=? THEN 'CONFIRMADO' ELSE 'SUPERADO' END WHERE remoto=? AND estado='INCERTO'",(quantidade,e['remoto']))
            yield
        for p in self.m.linhas('SELECT id FROM Produtos ORDER BY id'):
            self.m.planejar(p['id'],encerrar)
            yield
        filas = self.m.linhas("SELECT o.id FROM Outbox_Comandos o JOIN Estado_SKU_Canal e ON e.remoto=o.remoto WHERE o.estado IN('PENDENTE','RETENTAR') ORDER BY (o.quantidade>e.confirmada),o.id")
        for item in filas:
            # A interface pode mudar políticas/pedidos entre duas etapas.
            o = self.m.linha("SELECT o.*,e.confirmada FROM Outbox_Comandos o JOIN Estado_SKU_Canal e ON e.remoto=o.remoto WHERE o.id=? AND o.estado IN('PENDENTE','RETENTAR') AND o.geracao=e.geracao", (item['id'],))
            if not o:
                yield
                continue
            pid = self.m.linha('SELECT produto_id FROM Vinculos_SKU WHERE remoto=?',(o['remoto'],))['produto_id']
            s = self.m.saldo(pid)
            if o['quantidade']>o['confirmada'] and (s['exposta']-o['confirmada']+o['quantidade']>s['ecommerce']
                    or self.m.linha("SELECT 1 FROM Inbox_Eventos WHERE estado='PENDENTE'")):
                yield
                continue
            with self.m.bd.transacao():
                self.m.con.execute("UPDATE Outbox_Comandos SET estado='ENVIANDO',tentativas=tentativas+1 WHERE id=?",(o['id'],))
                self.m.con.execute('UPDATE Estado_SKU_Canal SET enviada=?,exposta=max(exposta,?),incerta=1 WHERE remoto=?',(o['quantidade'],o['quantidade'],o['remoto']))
            try:
                self.api.publicar(o['remoto'],o['quantidade'])
                confirmado = self.api.observar(o['remoto'])
                if confirmado != o['quantidade']:
                    raise FalhaRemota('DIVERGENCIA_REMOTA')
            except FalhaRemota:
                with self.m.bd.transacao():
                    self.m.con.execute("UPDATE Outbox_Comandos SET estado='INCERTO' WHERE id=?",(o['id'],))
                raise
            with self.m.bd.transacao():
                self.m.con.execute('UPDATE Estado_SKU_Canal SET confirmada=?,observada=?,exposta=?,incerta=0 WHERE remoto=?',(confirmado,confirmado,confirmado,o['remoto']))
                self.m.con.execute("UPDATE Outbox_Comandos SET estado='CONFIRMADO' WHERE id=?",(o['id'],))
            yield
        self.falhas = 0
        with self.m.bd.transacao():
            self.m.con.execute("UPDATE Incidentes_Sync SET resolvido=1 WHERE referencia='conector-simulado' AND tipo IN('SEM_INTERNET','TOKEN_VENCIDO','RATE_LIMIT','TIMEOUT_APOS_ENVIO')")


class WorkerAssincrono:
    """Executa as etapas com conexão própria; fsync não bloqueia o Named Pipe."""
    def __init__(self, caminho, senha, api):
        self.api = api
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='GiStocker-simulacao')
        self._futuro = None
        self._encerrando = False
        try:
            self._worker = self._executor.submit(self._abrir, caminho, senha).result()
        except BaseException:
            self._executor.shutdown()
            raise

    @staticmethod
    def _abrir(caminho, senha):
        banco = BancoDados(caminho, senha=senha, backup_automatico=False)
        try:
            return Worker(Motor(banco), MarketplaceSimulado(banco))
        except BaseException:
            banco.fechar()
            raise

    @property
    def retomar_em(self):
        return self._worker.retomar_em

    @retomar_em.setter
    def retomar_em(self, valor):
        self._worker.retomar_em = valor

    @property
    def encerramento_concluido(self):
        return self._encerrando and (self._futuro is None or self._futuro.done()) and self._worker._ciclo is None

    def _passo(self, encerrar):
        self._worker.api.falha = self.api.falha
        self._worker.passo(encerrar)

    def passo(self, encerrar=False):
        if self._futuro is not None and self._futuro.done():
            anterior, self._futuro = self._futuro, None
            anterior.result()
        if self._futuro is None:
            self._encerrando = encerrar
            self._futuro = self._executor.submit(self._passo, encerrar)
        concluidos, _ = wait((self._futuro,), timeout=.050)
        if concluidos:
            anterior, self._futuro = self._futuro, None
            anterior.result()  # Falhas são propagadas; a próxima tentativa pode avançar.

    def _fechar(self):
        if self._worker._ciclo is not None:
            self._worker._ciclo.close()
        self._worker.m.bd.fechar()

    def fechar(self):
        try:
            self._executor.submit(self._fechar).result()
        finally:
            self._executor.shutdown()

