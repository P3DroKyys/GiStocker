"""Worker recuperável. O único adaptador fornecido é um marketplace fictício."""
import random
import time


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
        with self.m.bd.transacao():
            self.m.con.execute("UPDATE Outbox_Comandos SET estado='INCERTO' WHERE estado='ENVIANDO'")
            self.m.con.execute("UPDATE Estado_SKU_Canal SET incerta=1 WHERE remoto IN(SELECT remoto FROM Outbox_Comandos WHERE estado='INCERTO')")
            self.m.con.execute("UPDATE Outbox_Comandos SET proxima=0 WHERE estado='RETENTAR'")

    def passo(self, encerrar=False):
        if time.monotonic()<self.retomar_em:
            return
        self.m.processar_inbox()
        try:
            # Observação antecede qualquer aumento, inclusive após reinício.
            for e in self.m.linhas('SELECT * FROM Estado_SKU_Canal'):
                quantidade = self.api.observar(e['remoto'])
                with self.m.bd.transacao():
                    if quantidade!=e['confirmada'] and not e['incerta']:
                        pid=self.m.linha('SELECT produto_id FROM Vinculos_SKU WHERE remoto=?',(e['remoto'],))['produto_id']
                        self.m.incidente('ESTOQUE_REMOTO_ALTERADO',e['remoto'],pid)
                    self.m.con.execute('UPDATE Estado_SKU_Canal SET observada=?,confirmada=?,exposta=?,incerta=0 WHERE remoto=?',(quantidade,quantidade,quantidade,e['remoto']))
                    self.m.con.execute("UPDATE Outbox_Comandos SET estado=CASE WHEN quantidade=? THEN 'CONFIRMADO' ELSE 'SUPERADO' END WHERE remoto=? AND estado='INCERTO'",(quantidade,e['remoto']))
            for p in self.m.estoque.listar_produtos():
                self.m.planejar(p.id,encerrar)
            filas = self.m.linhas("SELECT o.*,e.confirmada FROM Outbox_Comandos o JOIN Estado_SKU_Canal e ON e.remoto=o.remoto WHERE o.estado IN('PENDENTE','RETENTAR') ORDER BY (o.quantidade>e.confirmada),o.id")
            for o in filas:
                pid = self.m.linha('SELECT produto_id FROM Vinculos_SKU WHERE remoto=?',(o['remoto'],))['produto_id']
                s = self.m.saldo(pid)
                if o['quantidade']>o['confirmada'] and s['exposta']-o['confirmada']+o['quantidade']>s['ecommerce']:
                    continue
                if self.m.linha("SELECT 1 FROM Inbox_Eventos WHERE estado='PENDENTE'") and o['quantidade']>o['confirmada']:
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
            self.falhas = 0
            with self.m.bd.transacao():
                self.m.con.execute("UPDATE Incidentes_Sync SET resolvido=1 WHERE referencia='conector-simulado' AND tipo IN('SEM_INTERNET','TOKEN_VENCIDO','RATE_LIMIT','TIMEOUT_APOS_ENVIO')")
        except FalhaRemota as erro:
            self.falhas += 1
            atraso = max(erro.retry_after,min(300,2**min(self.falhas,8))+random.random())
            self.retomar_em = time.monotonic()+atraso
            with self.m.bd.transacao():
                self.m.incidente(erro.tipo,'conector-simulado')

