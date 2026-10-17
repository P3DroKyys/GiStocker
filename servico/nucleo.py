"""Único dono da conexão. Executado na thread do agente, inclusive no Windows SCM."""
import hashlib
import inspect
import json
import secrets
import time
from uuid import UUID

import config
from controllers.controllers import ControladorRelatorios, ErroNegocio
from models.models import BancoDados
from models.seguranca import ErroSeguranca, ErroAutenticacao, ErroSessao, copiar_protegido
from multicanal.motor import Motor
from multicanal.sincronizacao import MarketplaceSimulado, WorkerAssincrono
from servico.cofre import CofreServico
from servico.gestao import GestaoDados
from servico.protocolo import VERSAO, codificar, serializar

LEITURAS = {'resolver_codigo_barras','obter_produto','listar_produtos','buscar_produtos','pesquisar_produtos','listar_codigos','listar_logs','obter_ultima_acao','validar_codigo_barras'}
ESCRITAS = {'cadastrar_produto','vincular_codigo_barras','desvincular_codigo_barras','registrar_entrada','registrar_saida','ajustar_produto','desfazer_ultima_acao'}
RELATORIOS = {'obter_kpis','movimentacao_ultimos_dias','ranking_marcas','ranking_categorias','curva_a','estoque_parado'}
# comando -> (estado de destino, estados de origem permitidos). ENCERRANDO só termina em FISICO.
TRANSICOES = {
    'ativar_simulacao': ('MULTICANAL_CONFIGURANDO', ('FISICO', 'MULTICANAL_CONFIGURANDO')),
    'iniciar_ensaio': ('MULTICANAL_ATIVO', ('MULTICANAL_CONFIGURANDO', 'MULTICANAL_PAUSADO', 'MULTICANAL_ATIVO')),
    'pausar': ('MULTICANAL_PAUSADO', ('MULTICANAL_ATIVO', 'MULTICANAL_PAUSADO')),
    'encerrar': ('ENCERRANDO_MULTICANAL', ('MULTICANAL_CONFIGURANDO', 'MULTICANAL_ATIVO',
                                           'MULTICANAL_PAUSADO', 'ENCERRANDO_MULTICANAL')),
}


class Nucleo:
    def __init__(self, raiz, producao=False):
        from servico.executar import revisao_codigo
        self.revisao = revisao_codigo()
        self.producao = producao
        self.encerrar_solicitado = False
        self._ocioso_desde = time.monotonic()
        self.cofre = CofreServico(raiz)
        self.gestao = GestaoDados(self.cofre)
        self.sessoes = {}
        self.tentativas = {}   # identidade Windows -> (falhas seguidas, liberado em)
        self.motor = self.simulacao = self.worker = None
        self.falha_inicio = None
        self.falha_manutencao = None
        try:
            if self.cofre.abrir_segundo_plano():
                self._preparar()
        except ErroSeguranca:
            self.falha_inicio = 'Desbloqueie para reautorizar a proteção desta máquina.'

    def _preparar(self):
        self.motor = Motor(self.cofre.banco)
        self.motor.preparar()
        estado = self.cofre.banco.conexao.execute('SELECT estado FROM Config_Multicanal').fetchone()[0]
        if estado!='FISICO':
            self._abrir_simulacao()
        elif self.cofre.ler_envelope().get('servico'):
            self.cofre.permitir_segundo_plano(False)

    def _abrir_simulacao(self):
        if self.simulacao:
            return
        caminho = self.cofre.pasta/'simulacao.db'
        if not caminho.exists():
            copiar_protegido(self.cofre.banco.conexao,caminho)
        self.simulacao = Motor(BancoDados(caminho,senha=self.cofre.chave,backup_automatico=False))
        self.worker = WorkerAssincrono(caminho,self.cofre.chave,MarketplaceSimulado(self.simulacao.bd))

    def manutencao(self):
        self.gestao.manutencao()
        if self.gestao.ocupado:
            return
        agora = time.monotonic()
        self.sessoes = {k:v for k,v in self.sessoes.items() if agora-v['uso']<config.MINUTOS_BLOQUEIO_INATIVIDADE*60}
        if self.worker:
            estado=self.cofre.banco.conexao.execute('SELECT estado FROM Config_Multicanal').fetchone()[0]
            if estado=='MULTICANAL_ATIVO':
                self.worker.passo()
            elif estado=='ENCERRANDO_MULTICANAL':
                self.worker.passo(encerrar=True)
                self._concluir_encerramento()
        if not self.sessoes and self.cofre.banco and not self.cofre.ler_envelope().get('servico'):
            self._fechar_dados()

    def _fechar_dados(self):
        self.gestao.fechar()
        if self.worker:
            self.worker.fechar()
        if self.simulacao:
            self.simulacao.bd.fechar()
        self.simulacao = self.worker = self.motor = None
        self.cofre.fechar()

    def fechar(self):
        self.sessoes.clear()
        self._fechar_dados()

    def deve_encerrar(self):
        if self.producao:
            return False
        if self.sessoes or self.simulacao or self.gestao.ocupado:
            self._ocioso_desde = None
            return False
        if self._ocioso_desde is None:
            self._ocioso_desde = time.monotonic()
        return self.encerrar_solicitado or time.monotonic() - self._ocioso_desde >= config.SEGUNDOS_OCIOSIDADE_AGENTE

    def executar(self, pedido, identidade):
        request_id = pedido.get('id') if isinstance(pedido,dict) else None
        try:
            resultado = self._executar(pedido,identidade)
            return {'v':VERSAO,'id':request_id,'ok':True,'resultado':codificar(resultado),
                    'aviso':self.cofre.aviso_backup}
        except (ErroNegocio,ErroSeguranca,ValueError,TypeError) as erro:
            texto = str(erro) if not isinstance(erro,TypeError) else 'Parâmetros incompatíveis com esta operação.'
            return {'v':VERSAO,'id':request_id,'ok':False,'erro':type(erro).__name__,'mensagem':texto,
                    'codigo':'SESSAO' if isinstance(erro,ErroSessao) else None}
        except Exception:
            return {'v':VERSAO,'id':request_id,'ok':False,'erro':'Operacional','mensagem':'Operação não concluída. Confira o serviço, a integridade e o espaço disponível. Não repita com outro identificador sem conferir o resultado.'}

    def _executar(self, p, identidade):
        if type(p) is not dict or set(p)!={'v','id','sessao','comando','args','kwargs'} or type(p['v']) is not int or p['v']!=VERSAO:
            raise ValueError('Protocolo incompatível.')
        UUID(p['id'])
        if type(p['args']) is not list or type(p['kwargs']) is not dict or type(p['comando']) is not str or len(p['args'])>16 or len(p['kwargs'])>16:
            raise ValueError('Parâmetros inválidos.')
        comando,args,kwargs = p['comando'],p['args'],p['kwargs']
        if comando=='status':
            if args or kwargs:
                raise ValueError('Status não aceita parâmetros.')
            return {'modo':self.cofre.modo,'tema':self.cofre.obter_tema(),'servico':'online',
                    'versao':config.VERSAO_APP,'revisao':self.revisao,
                    'aviso':self.falha_manutencao or self.cofre.aviso_backup or self.falha_inicio}
        if comando == 'encerrar_agente':
            if args or kwargs:
                raise ValueError('Encerramento não aceita parâmetros.')
            self.encerrar_solicitado = not (self.producao or self.sessoes or self.simulacao or self.gestao.ocupado)
            return self.encerrar_solicitado
        if comando=='login':
            if self.gestao.ocupado and not self.gestao.abandonado:
                raise ValueError('Gestão de dados em andamento. Aguarde a conclusão.')
            self._exigir_intervalo(identidade)
            if len(args)!=3 or kwargs:
                raise ValueError('Login inválido.')
            try:
                self.cofre.abrir(*args)
            except ErroAutenticacao:
                self._registrar_tentativa(identidade)
                raise ErroAutenticacao('Senha incorreta ou envelope danificado. Nenhum acesso foi liberado.') from None
            self.tentativas.pop(identidade, None)
            self.gestao.fechar()   # só resta job aqui se ele foi abandonado: reverte o lote órfão
            self._preparar()
            token = secrets.token_urlsafe(32)
            self.sessoes[token] = {'identidade':identidade,'uso':time.monotonic()}
            return token
        sessao = self.sessoes.get(p['sessao']) if isinstance(p['sessao'],str) else None
        if not sessao or sessao['identidade']!=identidade or time.monotonic()-sessao['uso']>=config.MINUTOS_BLOQUEIO_INATIVIDADE*60:
            raise ErroSessao('Sessão bloqueada. Desbloqueie o software novamente.')
        if comando.startswith('dados.'):
            sessao['uso'] = time.monotonic()
            metodo = comando.split('.', 1)[1]
            if metodo == 'iniciar':
                return self.gestao.iniciar(p['sessao'], *args, **kwargs)
            if kwargs:
                raise ValueError('Parâmetros inesperados.')
            resultado = self.gestao.comando(p['sessao'], metodo, *args)
            job = self.gestao.job
            if job and job['concluido'] and job['tipo'] != 'exportar':
                self.sessoes = {p['sessao']: sessao}
            return resultado
        if self.gestao.ocupado and comando != 'atividade':
            raise ValueError('Gestão de dados em andamento. Aguarde a conclusão.')
        if comando in ('atividade','senha','tema') or comando.startswith('estoque.') and comando.split('.',1)[1] in ESCRITAS:
            sessao['uso'] = time.monotonic()
        if comando=='logout':
            self.sessoes.pop(p['sessao'],None)
            self.manutencao()
            return None
        if comando=='atividade':
            return None
        if comando=='tema':
            return self.cofre.definir_tema(*args,**kwargs)
        if comando=='senha':
            self._exigir_intervalo(identidade)
            try:
                resultado = self.cofre.alterar_senha(*args,**kwargs)
            except ErroAutenticacao:
                self._registrar_tentativa(identidade)
                raise ValueError('A senha atual está incorreta.') from None
            self.tentativas.pop(identidade, None)
            self.sessoes = {p['sessao']:sessao}
            return resultado
        if comando=='backup':
            if args or kwargs:
                raise ValueError('A pasta de backup é definida pelo serviço.')
            return self.cofre.exportar()
        if comando=='integracoes.painel':
            return self.painel()
        if comando.startswith('integracoes.'):
            return self.integracoes(comando.split('.',1)[1],args,kwargs,p['id'])
        grupo,sep,metodo = comando.partition('.')
        if not sep:
            raise ValueError('Comando desconhecido.')
        alvo = self.motor.estoque if grupo=='estoque' else ControladorRelatorios(self.cofre.banco) if grupo=='relatorios' else None
        permitidos = LEITURAS|ESCRITAS if grupo=='estoque' else RELATORIOS if grupo=='relatorios' else set()
        if alvo is None or metodo not in permitidos:
            raise ValueError('Comando não permitido.')
        inspect.signature(getattr(alvo,metodo)).bind(*args,**kwargs)
        if metodo in ESCRITAS:
            return self._idempotente(self.cofre.banco,p['id'],[comando,args,kwargs],lambda:self.motor.fisico(metodo,args,kwargs,p['id']))
        return getattr(alvo,metodo)(*args,**kwargs)

    def _exigir_intervalo(self, identidade):
        # Por identidade: uma conta errando a senha não atrasa as demais.
        if time.monotonic() < self.tentativas.get(identidade, (0, 0))[1]:
            raise ErroSeguranca('Aguarde antes de tentar novamente.')

    def _registrar_tentativa(self, identidade):
        falhas = self.tentativas.get(identidade, (0, 0))[0] + 1
        self.tentativas[identidade] = (falhas, time.monotonic() + min(300, 2 ** min(falhas, 8)))

    def _idempotente(self, banco, chave, parametros, funcao):
        from servico.protocolo import decodificar
        resumo = hashlib.sha256(serializar(parametros)).hexdigest()
        with banco.transacao():
            anterior = banco.conexao.execute('SELECT resumo,resposta FROM Comandos_IPC WHERE id=?',(chave,)).fetchone()
            if anterior:
                if anterior[0]!=resumo:
                    raise ErroNegocio('Identificador repetido com parâmetros diferentes.')
                return decodificar(json.loads(anterior[1]))
            resultado = funcao()
            resposta = serializar(codificar(resultado)).decode('utf-8')
            banco.conexao.execute('INSERT INTO Comandos_IPC(id,resumo,resposta) VALUES(?,?,?)',(chave,resumo,resposta))
            return resultado

    def painel(self):
        estado = self.cofre.banco.conexao.execute('SELECT estado FROM Config_Multicanal').fetchone()[0]
        return {'estado':estado,'ambiente':'SIMULAÇÃO — nenhum acesso a lojas reais',
                'local':[self.motor.saldo(p.id) for p in self.motor.estoque.listar_produtos()],
                'simulacao':self.simulacao.painel() if self.simulacao else None}

    def _exigir_origem(self, comando):
        """Estado atual, desde que ``comando`` seja permitido a partir dele."""
        estado = self.cofre.banco.conexao.execute('SELECT estado FROM Config_Multicanal').fetchone()[0]
        if estado not in TRANSICOES[comando][1]:
            raise ErroNegocio(f'Ação indisponível com a simulação no estado {estado}.')
        return estado

    def _definir_estado(self, comando):
        with self.cofre.banco.transacao():
            self.cofre.banco.conexao.execute('UPDATE Config_Multicanal SET estado=?', (TRANSICOES[comando][0],))

    def _descartar_simulacao(self):
        # Só ocorre no modo físico: a cópia anterior não está aberta nem em uso.
        caminho = self.cofre.pasta/'simulacao.db'
        for arquivo in (caminho, *(caminho.with_name(caminho.name + s) for s in ('-wal', '-shm', '-journal'))):
            arquivo.unlink(missing_ok=True)

    def integracoes(self, comando, args, kwargs, chave):
        if comando=='ativar_simulacao':
            if self._exigir_origem(comando) == 'FISICO' and not self.simulacao:
                self._descartar_simulacao()   # um novo ensaio parte do estoque atual
            self._abrir_simulacao()
            self.cofre.permitir_segundo_plano(True)
            self._definir_estado(comando)
            return self.painel()
        if not self.simulacao:
            raise ErroNegocio('Ative o ambiente de simulação primeiro.')
        if comando in ('iniciar_ensaio', 'pausar'):
            self._exigir_origem(comando)
            self._definir_estado(comando)
            return None
        if comando=='encerrar':
            self._exigir_origem(comando)
            self._definir_estado(comando)
            self.worker.retomar_em = 0
            self.worker.passo(encerrar=True)
            if not self._concluir_encerramento():
                raise ErroNegocio('Ainda há exposição, pedidos ou resultados incertos. Resolva as pendências antes de encerrar.')
            return None
        if comando=='falha':
            if len(args)!=1 or args[0] not in (None,'SEM_INTERNET','TOKEN_VENCIDO','RATE_LIMIT','TIMEOUT_APOS_ENVIO'):
                raise ValueError('Cenário desconhecido.')
            self.worker.api.falha = args[0]
            self.worker.retomar_em = 0
            return None
        if comando=='sugerir':
            if len(args)!=1:
                raise ValueError('Selecione um anúncio.')
            c = self.simulacao.linha('SELECT * FROM Catalogo_Remoto WHERE id=?',(args[0],))
            if not c:
                raise ErroNegocio('Anúncio não encontrado.')
            produto = self.simulacao.estoque.resolver_codigo_barras(c['gtin']) if c['gtin'] else None
            return {'criterio':'GTIN exato' if produto else 'Nome e marca — confirme a variação',
                    'produtos':[produto] if produto else self.simulacao.estoque.pesquisar_produtos(c['titulo']+' '+c['marca']).produtos[:10]}
        if comando=='reconciliar':
            # Confirmação explícita na interface: usa novamente a política local.
            for e in self.simulacao.linhas('SELECT * FROM Estado_SKU_Canal'):
                observado=self.worker.api.observar(e['remoto'])
                if observado!=e['observada']:
                    raise ErroNegocio('Estoque remoto mudou novamente. Aguarde a próxima observação.')
            with self.simulacao.bd.transacao():
                self.simulacao.con.execute("UPDATE Incidentes_Sync SET resolvido=1 WHERE tipo='ESTOQUE_REMOTO_ALTERADO'")
            self.worker.retomar_em=0
            return None
        if comando=='catalogo_exemplo':
            def criar():
                for canal in ('SHOPEE','TIKTOK'):
                    self.simulacao.con.execute('INSERT OR IGNORE INTO Lojas_Externas VALUES(?,?,?,?,1)',(canal,canal,'Loja de demonstração '+canal,'SIMULADO'))
                    for prod in self.simulacao.estoque.listar_produtos():
                        self.simulacao.con.execute('INSERT OR IGNORE INTO Catalogo_Remoto(id,loja,produto_externo,sku,armazem,titulo,marca,gtin) VALUES(?,?,?,?,?,?,?,?)',(canal+':'+str(prod.id),canal,str(prod.id),str(prod.id),'PADRAO',prod.nome,prod.marca,prod.codigos[0] if prod.codigos else ''))
            return self._idempotente(self.simulacao.bd,chave,[comando],criar)
        if comando in ('vincular','cobertura','politica','receber','pedido_operar'):
            fn = getattr(self.simulacao,comando)
            inspect.signature(fn).bind(*args,**kwargs)
            return self._idempotente(self.simulacao.bd,chave,[comando,args,kwargs],lambda:fn(*args,**kwargs))
        if comando=='passo':
            self.worker.passo()
            return self.painel()
        raise ValueError('Operação de integração não disponível.')

    def _concluir_encerramento(self):
        if not self.worker.encerramento_concluido:
            return False
        pendente = self.simulacao.linha("SELECT 1 FROM Estado_SKU_Canal WHERE exposta>0 OR incerta=1") or self.simulacao.linha("SELECT 1 FROM Inbox_Eventos WHERE estado='PENDENTE'") or self.simulacao.linha('SELECT 1 FROM Reservas WHERE quantidade>0') or self.simulacao.linha("SELECT 1 FROM Itens_Pedido_Externo WHERE estado='DEVOLUCAO_EM_CONFERENCIA'")
        if pendente:
            return False
        with self.cofre.banco.transacao():
            self.cofre.banco.conexao.execute("UPDATE Config_Multicanal SET estado='FISICO'")
        self.cofre.permitir_segundo_plano(False)
        self.worker.fechar()
        self.simulacao.bd.fechar()
        self.simulacao = self.worker = None
        return True
