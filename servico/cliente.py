"""Fachada MVC. A interface não recebe chave, conexão nem caminho de escrita."""
from functools import partial
import json
from types import SimpleNamespace
from uuid import uuid4

from controllers.controllers import ControladorEstoque, ErroNegocio
from models.seguranca import ErroSeguranca
from servico.nucleo import LEITURAS, ESCRITAS, RELATORIOS
from servico.pipe import chamar, nome_pipe
from servico.protocolo import VERSAO, decodificar
from servico.pendencias import Pendencias


class Proxy:
    def __init__(self, cliente, grupo):
        self.cliente, self.grupo = cliente, grupo

    def __getattr__(self, nome):
        if self.grupo=='estoque' and nome=='calcular_custo_medio_ponderado':
            return ControladorEstoque.calcular_custo_medio_ponderado
        if self.grupo=='relatorios' and nome=='exportar_protegido':
            return lambda: self.cliente.chamar('backup')
        permitidos = LEITURAS|ESCRITAS if self.grupo=='estoque' else RELATORIOS
        if nome not in permitidos:
            raise AttributeError(nome)
        return partial(self.cliente.chamar,self.grupo+'.'+nome)


class Cliente:
    def __init__(self, raiz, producao=False):
        self.nome = nome_pipe(raiz,producao)
        self.producao = producao
        self.sessao = None
        self.banco = None  # apenas sentinela de sessão para compatibilidade visual
        self.pendentes = {}
        self.ao_indisponivel = None
        self.journal = Pendencias(raiz,producao)
        self.ultimo_status = {'modo':'protegido','tema':'dark'}

    def chamar(self, comando, *args, **kwargs):
        assinatura = json.dumps([comando,args,kwargs],sort_keys=True,ensure_ascii=True)
        mutacao = (comando.startswith('estoque.') and comando.split('.',1)[1] in ESCRITAS or
                   comando in ('integracoes.vincular','integracoes.cobertura','integracoes.politica','integracoes.receber','integracoes.pedido_operar','integracoes.catalogo_exemplo'))
        try:
            if mutacao:
                self.pendentes[assinatura] = self.journal.iniciar(assinatura)
            resultado=self._enviar(comando,args,kwargs,assinatura)
            if mutacao:
                self.journal.confirmar()
            return resultado
        except (ErroNegocio,ValueError):
            if mutacao and self.journal.trava:
                self.journal.confirmar()  # erro de negócio é rollback confirmado
            raise
        finally:
            if mutacao:
                self.journal.fechar()

    def _enviar(self, comando, args, kwargs, assinatura):
        chave = self.pendentes.get(assinatura) or str(uuid4())
        pedido = dict(v=VERSAO,id=chave,sessao=self.sessao,comando=comando,args=list(args),kwargs=kwargs)
        try:
            resposta = chamar(self.nome,pedido,self.producao)
        except Exception:
            if (comando.startswith('estoque.') and comando.split('.',1)[1] in ESCRITAS or
                    comando in ('integracoes.vincular','integracoes.cobertura','integracoes.politica','integracoes.receber','integracoes.pedido_operar','integracoes.catalogo_exemplo')):
                self.pendentes[assinatura] = chave
            if self.ao_indisponivel:
                self.ao_indisponivel()
            raise ErroSeguranca('O serviço local não respondeu. Nenhuma gravação direta foi realizada. Ao repetir esta mesma operação, o identificador será preservado.') from None
        if resposta.get('id')!=chave or resposta.get('v')!=VERSAO:
            raise ErroSeguranca('Resposta incompatível do serviço.')
        if not resposta.get('ok'):
            if resposta.get('erro')=='ErroSeguranca' and self.sessao and self.ao_indisponivel:
                self.ao_indisponivel()
            classe = ErroNegocio if resposta.get('erro')=='ErroNegocio' else ValueError if resposta.get('erro') in ('ValueError','TypeError') else ErroSeguranca
            raise classe(resposta.get('mensagem','Operação não concluída.'))
        self.pendentes.pop(assinatura,None)
        resultado=decodificar(resposta['resultado'])
        if comando=='status':
            self.ultimo_status=resultado
        return resultado

    @property
    def modo(self):
        try: return self.chamar('status')['modo']
        except ErroSeguranca: return self.ultimo_status['modo']

    def obter_tema(self):
        try: return self.chamar('status')['tema']
        except ErroSeguranca: return self.ultimo_status['tema']

    def abrir(self, senha, nova=None, confirmacao=None):
        self.sessao = self.chamar('login',senha,nova,confirmacao)
        self.banco = SimpleNamespace(_fechado=False,criptografado=True)

    def criar_controladores(self):
        return Proxy(self,'estoque'),Proxy(self,'relatorios')

    def definir_tema(self, tema):
        return self.chamar('tema',tema)

    def alterar_senha(self, antiga, nova, confirmacao):
        return self.chamar('senha',antiga,nova,confirmacao)

    def atividade(self):
        if self.sessao:
            self.chamar('atividade')

    def fechar(self):
        try:
            if self.sessao:
                self.chamar('logout')
        except ErroSeguranca:
            pass  # bloqueio visual nunca depende de o serviço estar acessível
        finally:
            self.sessao = self.banco = None
