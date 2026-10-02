"""Alocação e pedidos transacionais. Rede fica fora das transações do banco."""
import json
import secrets
from functools import wraps
from uuid import uuid4

from controllers.controllers import ControladorEstoque, ErroNegocio

CANAIS = ('SHOPEE', 'TIKTOK')
COBERTURAS = ('PENDENTE_VINCULO', 'VINCULADO', 'NAO_PUBLICADO', 'IGNORADO', 'PAUSADO')


def atomico(fn):
    @wraps(fn)
    def executar(self, *args, **kwargs):
        with self.bd.transacao():
            return fn(self, *args, **kwargs)
    return executar


def inteiro(valor, minimo=0):
    if type(valor) is not int or not minimo <= valor <= 2**63 - 1:
        raise ErroNegocio('Informe uma quantidade inteira válida.')
    return valor


class Motor:
    def __init__(self, banco):
        self.bd = banco
        self.con = banco.conexao
        self.estoque = ControladorEstoque(banco)

    def linha(self, sql, args=()):
        r = self.con.execute(sql, args).fetchone()
        return dict(r) if r else None

    def linhas(self, sql, args=()):
        return [dict(r) for r in self.con.execute(sql, args)]

    def evento(self, chave, pid, delta, origem, natureza, referencia=None, log_id=None):
        self.con.execute('INSERT INTO Eventos_Estoque(chave,produto_id,delta,origem,natureza,referencia,log_id) VALUES(?,?,?,?,?,?,?)',
                         (chave, pid, delta, origem, natureza, referencia, log_id))

    @atomico
    def preparar(self):
        # Saldo de abertura não duplica o histórico: é o ponto inicial do novo livro.
        for p in self.estoque.listar_produtos():
            if not self.linha('SELECT id FROM Eventos_Estoque WHERE produto_id=?', (p.id,)):
                self.evento('abertura:' + str(p.id), p.id, p.estoque_atual, 'FISICO', 'ABERTURA')
            self.con.execute('INSERT OR IGNORE INTO Politicas_Alocacao(produto_id) VALUES(?)', (p.id,))
            for canal in CANAIS:
                self.con.execute("INSERT OR IGNORE INTO Cobertura_Produto_Canal VALUES(?,?,'PENDENTE_VINCULO')", (p.id, canal))

    def saldo(self, pid):
        p = self.estoque.obter_produto(pid)
        politica = self.linha('SELECT * FROM Politicas_Alocacao WHERE produto_id=?', (pid,)) or {'margem': 0, 'quarentena': 0, 'percentual': 50}
        politica.pop('produto_id', None)
        reservado = self.con.execute('SELECT coalesce(sum(quantidade),0) FROM Reservas WHERE produto_id=?', (pid,)).fetchone()[0]
        exposicao = self.con.execute('SELECT coalesce(sum(e.exposta),0) FROM Estado_SKU_Canal e JOIN Vinculos_SKU v ON v.remoto=e.remoto WHERE v.produto_id=?', (pid,)).fetchone()[0]
        livre = max(0, p.estoque_atual - reservado - politica['quarentena'])
        fisico = (livre * politica['percentual'] + 99) // 100
        return dict(produto_id=pid, nome=p.nome, em_maos=p.estoque_atual, comprometido=reservado,
                    livre=livre, reserva_fisica=fisico, ecommerce=max(0, livre-fisico-politica['margem']),
                    exposta=exposicao, disponivel_fisico=max(0,livre-exposicao-politica['margem']), **politica)

    def exigir_saldo(self, pid, novo):
        s = self.saldo(pid)
        if novo < s['comprometido'] + s['quarentena'] + s['exposta'] + s['margem']:
            raise ErroNegocio('Saldo comprometido com pedidos ou anúncios online. Reduza e confirme a exposição antes de retirar estas unidades.')

    @atomico
    def fisico(self, metodo, args, kwargs, chave):
        anteriores = {p.id: p.estoque_atual for p in self.estoque.listar_produtos()}
        maxlog = self.con.execute('SELECT coalesce(max(id),0) FROM Logs_Movimentacao').fetchone()[0]
        if metodo == 'desfazer_ultima_acao':
            ultima = self.estoque.obter_ultima_acao()
            if ultima and self.linha("SELECT 1 FROM Eventos_Estoque WHERE log_id=? AND origem<>'FISICO'", (ultima.log.id,)):
                raise ErroNegocio('Pedidos online devem ser compensados no painel de pedidos.')
        resultado = getattr(self.estoque, metodo)(*args, **kwargs)
        for p in self.estoque.listar_produtos():
            antes = anteriores.get(p.id, 0)
            if p.estoque_atual < antes:
                self.exigir_saldo(p.id, p.estoque_atual)
            logs = self.linhas('SELECT id FROM Logs_Movimentacao WHERE id>? AND produto_id=?', (maxlog,p.id))
            if p.id not in anteriores or p.estoque_atual != antes or logs or metodo == 'desfazer_ultima_acao' and resultado and resultado.produto.id == p.id:
                ref = str(resultado.log.id) if metodo == 'desfazer_ultima_acao' else None
                self.evento(chave + ':' + str(p.id), p.id, p.estoque_atual-antes, 'FISICO',
                            'COMPENSACAO' if ref else metodo, ref, logs[-1]['id'] if logs else None)
        self.preparar()
        return resultado

    @atomico
    def politica(self, produto_id, percentual=50, margem=0):
        inteiro(produto_id,1); inteiro(percentual); inteiro(margem)
        if percentual > 100:
            raise ErroNegocio('Percentual deve ficar entre 0 e 100.')
        self.estoque.obter_produto(produto_id)
        self.con.execute('INSERT INTO Politicas_Alocacao(produto_id,percentual,margem) VALUES(?,?,?) ON CONFLICT(produto_id) DO UPDATE SET percentual=excluded.percentual,margem=excluded.margem', (produto_id,percentual,margem))
        return self.alocar(produto_id)

    @atomico
    def cobertura(self, produto_id, canal, estado):
        if canal not in CANAIS or estado not in COBERTURAS or estado == 'VINCULADO':
            raise ErroNegocio('Use a confirmação do vínculo para marcar um canal vinculado.')
        self.estoque.obter_produto(produto_id)
        if self.linha('SELECT 1 FROM Vinculos_SKU v JOIN Catalogo_Remoto c ON c.id=v.remoto JOIN Lojas_Externas l ON l.id=c.loja WHERE v.produto_id=? AND l.canal=?', (produto_id,canal)):
            raise ErroNegocio('Este canal possui vínculos. Não é possível descartá-los sem encerrar a exposição.')
        self.con.execute('INSERT INTO Cobertura_Produto_Canal VALUES(?,?,?) ON CONFLICT(produto_id,canal) DO UPDATE SET estado=excluded.estado', (produto_id,canal,estado))

    @atomico
    def vincular(self, remoto, produto_id):
        inteiro(produto_id,1)
        self.estoque.obter_produto(produto_id)
        c = self.linha('SELECT c.*,l.canal FROM Catalogo_Remoto c JOIN Lojas_Externas l ON c.loja=l.id WHERE c.id=?', (remoto,))
        if not c:
            raise ErroNegocio('Selecione um anúncio importado.')
        anterior = self.linha('SELECT produto_id FROM Vinculos_SKU WHERE remoto=?', (remoto,))
        if anterior and anterior['produto_id'] != produto_id:
            raise ErroNegocio('Este anúncio já está vinculado a outro produto.')
        self.con.execute('INSERT OR IGNORE INTO Vinculos_SKU VALUES(?,?)', (remoto,produto_id))
        self.con.execute("INSERT INTO Cobertura_Produto_Canal VALUES(?,?,'VINCULADO') ON CONFLICT(produto_id,canal) DO UPDATE SET estado='VINCULADO'", (produto_id,c['canal']))
        # Catálogo importado pode já conter estoque! Nunca assumir zero.
        self.con.execute('INSERT OR IGNORE INTO Estado_SKU_Canal(remoto,observada,confirmada,exposta) VALUES(?,?,?,?)', (remoto,c['quantidade'],c['quantidade'],c['quantidade']))

    @atomico
    def alocar(self, produto_id):
        self.preparar()
        s = self.saldo(produto_id)
        cob = self.linhas('SELECT * FROM Cobertura_Produto_Canal WHERE produto_id=?', (produto_id,))
        pendente = any(c['estado']=='PENDENTE_VINCULO' for c in cob)
        canais = sorted(c['canal'] for c in cob if c['estado']=='VINCULADO')
        anuncios = self.linhas('SELECT c.id,l.canal FROM Vinculos_SKU v JOIN Catalogo_Remoto c ON c.id=v.remoto JOIN Lojas_Externas l ON l.id=c.loja WHERE v.produto_id=? AND l.autorizada=1 ORDER BY c.id', (produto_id,))
        canais = [c for c in canais if any(a['canal']==c for a in anuncios)]
        impeditivo = self.linha('SELECT id FROM Incidentes_Sync WHERE produto_id=? AND resolvido=0', (produto_id,))
        total = 0 if pendente or impeditivo else s['ecommerce']
        n = len(canais)
        base, sobra = divmod(total,n) if n else (0,0)
        assinatura = ','.join(canais)
        anterior = self.linha('SELECT * FROM Estado_Alocacao WHERE produto_id=?',(produto_id,))
        vencedor = anterior['vencedor'] if anterior and anterior['elegiveis']==assinatura and anterior['sobra'] and sobra else None
        if sobra and vencedor not in canais:
            vencedor = secrets.choice(canais)
        geracao = (anterior['geracao'] + 1) if anterior and (anterior['elegiveis']!=assinatura or anterior['sobra']!=sobra or anterior['vencedor']!=vencedor) else anterior['geracao'] if anterior else 1
        self.con.execute('INSERT INTO Estado_Alocacao VALUES(?,?,?,?,?) ON CONFLICT(produto_id) DO UPDATE SET elegiveis=excluded.elegiveis,sobra=excluded.sobra,vencedor=excluded.vencedor,geracao=excluded.geracao', (produto_id,assinatura,sobra,vencedor,geracao))
        cotas = {canal: base + int(sobra and canal==vencedor) for canal in canais}
        return dict(saldo=s, cotas=cotas, vencedor=vencedor, geracao=geracao, bloqueado=bool(pendente or impeditivo), anuncios=anuncios)

    @atomico
    def planejar(self, produto_id, encerrar=False):
        plano = self.alocar(produto_id)
        if plano['bloqueado'] and not encerrar:
            self.con.execute("UPDATE Outbox_Comandos SET estado='SUPERADO' WHERE remoto IN(SELECT remoto FROM Vinculos_SKU WHERE produto_id=?) AND estado IN('PENDENTE','RETENTAR')",(produto_id,))
            return plano
        for canal in CANAIS:
            anuncios = [a for a in plano['anuncios'] if a['canal']==canal]
            cota = 0 if encerrar else plano['cotas'].get(canal,0)
            for i,a in enumerate(anuncios):
                qtd = cota//len(anuncios) + int(i<cota%len(anuncios))
                e = self.linha('SELECT * FROM Estado_SKU_Canal WHERE remoto=?', (a['id'],))
                pendente = self.linha("SELECT id FROM Outbox_Comandos WHERE remoto=? AND estado NOT IN('CONFIRMADO','SUPERADO')", (a['id'],))
                if e['desejada']==qtd and (pendente or e['confirmada']==qtd and not e['incerta']):
                    continue
                # Não substituir uma chamada cujo resultado ainda é incerto.
                if e['incerta']:
                    continue
                self.con.execute("UPDATE Outbox_Comandos SET estado='SUPERADO' WHERE remoto=? AND estado IN('PENDENTE','RETENTAR')", (a['id'],))
                geracao = e['geracao']+1
                self.con.execute('UPDATE Estado_SKU_Canal SET desejada=?,geracao=? WHERE remoto=?',(qtd,geracao,a['id']))
                self.con.execute('INSERT INTO Outbox_Comandos(remoto,quantidade,geracao) VALUES(?,?,?)',(a['id'],qtd,geracao))
        return plano

    @atomico
    def receber(self, evento):
        campos = {'loja','pedido','linha','remoto','quantidade','cancelada','versao','estado'}
        if type(evento) is not dict or set(evento)!=campos:
            raise ErroNegocio('Evento de pedido incompleto.')
        for k in ('quantidade','cancelada','versao'):
            inteiro(evento[k], 1 if k in ('quantidade','versao') else 0)
        if evento['cancelada']>evento['quantidade'] or evento['estado'] not in ('RESERVADO','CANCELADO'):
            raise ErroNegocio('Transição remota inválida.')
        if evento['estado']=='CANCELADO' and evento['cancelada']!=evento['quantidade']:
            raise ErroNegocio('Cancelamento integral exige todas as unidades canceladas.')
        for k in ('loja','pedido','linha','remoto'):
            if type(evento[k]) is not str or not 1<=len(evento[k])<=160:
                raise ErroNegocio('Identificador remoto inválido.')
        chave = json.dumps([evento[k] for k in ('loja','pedido','linha','versao')],ensure_ascii=True)
        conteudo = json.dumps(evento,sort_keys=True)
        anterior = self.linha('SELECT conteudo FROM Inbox_Eventos WHERE chave=?',(chave,))
        if anterior and anterior['conteudo']!=conteudo:
            raise ErroNegocio('Mesma versão com conteúdo divergente; requer conciliação.')
        self.con.execute('INSERT OR IGNORE INTO Inbox_Eventos(chave,conteudo) VALUES(?,?)',(chave,conteudo))
        return chave

    def incidente(self, tipo, referencia, pid=None):
        self.con.execute('INSERT INTO Incidentes_Sync(produto_id,tipo,referencia) VALUES(?,?,?) ON CONFLICT(tipo,referencia) DO UPDATE SET resolvido=0,criado=CURRENT_TIMESTAMP',(pid,tipo,referencia))

    def atualizar_pedido(self, pedido):
        estados={r[0] for r in self.con.execute('SELECT estado FROM Itens_Pedido_Externo WHERE pedido_id=?',(pedido,))}
        if estados:
            self.con.execute('UPDATE Pedidos_Externos SET estado=? WHERE id=?',(next(iter(estados)) if len(estados)==1 else 'MISTO',pedido))

    @atomico
    def processar_inbox(self):
        for entrada in self.linhas("SELECT * FROM Inbox_Eventos WHERE estado='PENDENTE' ORDER BY recebido,chave"):
            e = json.loads(entrada['conteudo'])
            v = self.linha('SELECT v.produto_id,l.canal FROM Vinculos_SKU v JOIN Catalogo_Remoto c ON c.id=v.remoto JOIN Lojas_Externas l ON l.id=c.loja WHERE v.remoto=? AND c.loja=?',(e['remoto'],e['loja']))
            if not v:
                self.incidente('PEDIDO_SEM_VINCULO',entrada['chave'])
                continue
            pedido = json.dumps([e['loja'],e['pedido']])
            item_id = json.dumps([e['loja'],e['pedido'],e['linha']])
            item = self.linha('SELECT * FROM Itens_Pedido_Externo WHERE id=?',(item_id,))
            if item and item['versao']>=e['versao']:
                self.con.execute("UPDATE Inbox_Eventos SET estado='ANTIGO' WHERE chave=?",(entrada['chave'],))
                continue
            if item and (item['quantidade']!=e['quantidade'] or item['remoto']!=e['remoto'] or item['cancelada']>e['cancelada']):
                self.incidente('PEDIDO_DIVERGENTE',entrada['chave'],v['produto_id'])
                continue
            if item and item['estado']=='CANCELADO' and item['cancelada']<e['cancelada'] and self.linha('SELECT id FROM Eventos_Estoque WHERE chave=?',('inspecao:'+item_id,)):
                self.incidente('DEVOLUCAO_ADICIONAL_REQUER_CONCILIACAO',entrada['chave'],v['produto_id'])
                continue
            ativa = e['quantidade']-e['cancelada']
            if not item:
                if ativa > self.saldo(v['produto_id'])['livre']:
                    self.incidente('SALDO_INSUFICIENTE',entrada['chave'],v['produto_id'])
                    continue
                self.con.execute("INSERT OR IGNORE INTO Pedidos_Externos VALUES(?,?,?,'RESERVADO')",(pedido,e['loja'],e['pedido']))
                self.con.execute('INSERT INTO Itens_Pedido_Externo VALUES(?,?,?,?,?,?,?,?,?)',(item_id,pedido,e['linha'],e['remoto'],v['produto_id'],e['quantidade'],0,0,'RESERVADO'))
                self.con.execute('INSERT INTO Reservas VALUES(?,?,?)',(item_id,v['produto_id'],ativa))
                self.evento('reserva:'+item_id,v['produto_id'],0,v['canal'],'RESERVA',pedido)
                # Exposição não é liberada só pela notificação. Observação/ack é indispensável.
                self.con.execute('UPDATE Estado_SKU_Canal SET incerta=1 WHERE remoto=?',(e['remoto'],))
                item = self.linha('SELECT * FROM Itens_Pedido_Externo WHERE id=?',(item_id,))
            estado = item['estado']
            if e['cancelada']>item['cancelada']:
                if estado=='RESERVADO':
                    self.con.execute('UPDATE Reservas SET quantidade=? WHERE item=?',(ativa,item_id))
                    estado = 'CANCELADO' if not ativa else 'RESERVADO'
                elif estado not in ('CANCELADO','DEVOLUCAO_EM_CONFERENCIA'):
                    estado = 'DEVOLUCAO_EM_CONFERENCIA'
                self.evento('cancelamento:'+entrada['chave'],v['produto_id'],0,v['canal'],'CANCELAMENTO',pedido)
            self.con.execute('UPDATE Itens_Pedido_Externo SET cancelada=?,versao=?,estado=? WHERE id=?',(e['cancelada'],e['versao'],estado,item_id))
            self.atualizar_pedido(pedido)
            self.con.execute("UPDATE Inbox_Eventos SET estado='APLICADO' WHERE chave=?",(entrada['chave'],))
            self.con.execute("UPDATE Incidentes_Sync SET resolvido=1 WHERE referencia=? AND tipo IN('PEDIDO_SEM_VINCULO','SALDO_INSUFICIENTE')",(entrada['chave'],))

    @atomico
    def pedido_operar(self, item_id, acao):
        item = self.linha('SELECT i.*,l.canal FROM Itens_Pedido_Externo i JOIN Pedidos_Externos p ON p.id=i.pedido_id JOIN Lojas_Externas l ON l.id=p.loja WHERE i.id=?',(item_id,))
        if not item:
            raise ErroNegocio('Pedido não encontrado.')
        estado = item['estado']
        if acao in ('RECEBER_DEVOLUCAO','APROVAR_DEVOLUCAO','REPROVAR_DEVOLUCAO'):
            if estado!='DEVOLUCAO_EM_CONFERENCIA' or not self.linha('SELECT id FROM Eventos_Estoque WHERE chave=?',('envio:'+item_id,)):
                raise ErroNegocio('Esta conferência é destinada a produtos já enviados e devolvidos.')
            recebida = self.linha('SELECT delta FROM Eventos_Estoque WHERE chave=?',('retorno:'+item_id,))
            if acao=='RECEBER_DEVOLUCAO':
                if recebida:
                    raise ErroNegocio('Devolução já recebida. Faça a inspeção.')
                qtd = item['cancelada']
                res = self.estoque.registrar_entrada(item['produto_id'],qtd)
                self.con.execute('UPDATE Politicas_Alocacao SET quarentena=quarentena+? WHERE produto_id=?',(qtd,item['produto_id']))
                self.evento('retorno:'+item_id,item['produto_id'],qtd,'FISICO','DEVOLUCAO_RECEBIDA',item['pedido_id'],res.log_id)
            else:
                if not recebida:
                    raise ErroNegocio('Confirme primeiro o recebimento físico da devolução.')
                qtd = recebida['delta']
                log_id = None
                if acao=='REPROVAR_DEVOLUCAO':
                    log_id = self.estoque.registrar_saida(item['produto_id'],qtd).log_id
                self.con.execute('UPDATE Politicas_Alocacao SET quarentena=quarentena-? WHERE produto_id=?',(qtd,item['produto_id']))
                self.evento('inspecao:'+item_id,item['produto_id'],-qtd if log_id else 0,'FISICO',acao,item['pedido_id'],log_id)
                self.con.execute("UPDATE Itens_Pedido_Externo SET estado='CANCELADO' WHERE id=?",(item_id,))
            self.atualizar_pedido(item['pedido_id'])
            return
        transicoes = {('RESERVADO','SEPARAR'):'EM_SEPARACAO',('EM_SEPARACAO','EMBALAR'):'EMBALADO',('EMBALADO','ENVIAR'):'ENVIADO'}
        destino = transicoes.get((estado,acao))
        if acao=='CONFERIR_RETORNO' and estado=='DEVOLUCAO_EM_CONFERENCIA':
            reserva = self.linha('SELECT quantidade FROM Reservas WHERE item=?',(item_id,))['quantidade']
            if reserva==0:
                raise ErroNegocio('Produto já enviado: devolução exige recebimento e inspeção em quarentena.')
            self.con.execute('UPDATE Reservas SET quantidade=? WHERE item=?',(item['quantidade']-item['cancelada'],item_id))
            destino = 'CANCELADO' if item['cancelada']==item['quantidade'] else 'RESERVADO'
        if not destino:
            raise ErroNegocio('Ação incompatível com a situação atual do pedido.')
        if destino=='ENVIADO':
            qtd = self.linha('SELECT quantidade FROM Reservas WHERE item=?',(item_id,))['quantidade']
            res = self.estoque.registrar_saida(item['produto_id'],qtd)
            self.con.execute('UPDATE Reservas SET quantidade=0 WHERE item=?',(item_id,))
            self.evento('envio:'+item_id,item['produto_id'],-qtd,item['canal'],'ENVIO',item['pedido_id'],res.log_id)
        else:
            self.evento(uuid4().hex,item['produto_id'],0,item['canal'],acao,item['pedido_id'])
        self.con.execute('UPDATE Itens_Pedido_Externo SET estado=? WHERE id=?',(destino,item_id))
        self.atualizar_pedido(item['pedido_id'])

    def painel(self):
        return dict(produtos=[self.saldo(p.id) for p in self.estoque.listar_produtos()],
                    catalogo=self.linhas('SELECT c.*,l.canal,v.produto_id FROM Catalogo_Remoto c JOIN Lojas_Externas l ON l.id=c.loja LEFT JOIN Vinculos_SKU v ON v.remoto=c.id'),
                    cobertura=self.linhas('SELECT * FROM Cobertura_Produto_Canal'),
                    pedidos=self.linhas('SELECT * FROM Itens_Pedido_Externo'),
                    incidentes=self.linhas('SELECT * FROM Incidentes_Sync WHERE resolvido=0'),
                    exposicao=self.linhas('SELECT * FROM Estado_SKU_Canal'),
                    fila=self.linhas("SELECT * FROM Outbox_Comandos WHERE estado NOT IN('CONFIRMADO','SUPERADO')"),
                    eventos=self.linhas('SELECT * FROM Eventos_Estoque ORDER BY id DESC LIMIT 100'))
