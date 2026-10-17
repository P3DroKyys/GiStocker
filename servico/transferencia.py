"""Cliente de transferência usado em uma thread, sem widgets ou callbacks Tk."""
import base64
import hashlib
from pathlib import Path
from uuid import uuid4

from gestao.arquivos import BLOCO, SaidaAtomica, ler_arquivo, ler_json
from servico.pendencias import Pendencias
from servico.pipe import chamar, ERROS_TRANSPORTE
from servico.protocolo import VERSAO, decodificar


class Transferencia:
    def __init__(self, cliente):
        self.nome, self.producao, self.sessao = cliente.nome, cliente.producao, cliente.sessao
        self.journal = Pendencias(cliente.journal.caminho.parent, False)
        self.journal.caminho = self.journal.caminho.with_name('gestao_pendentes.json')

    def pedir(self, comando, *args):
        pedido = dict(v=VERSAO, id=str(uuid4()), sessao=self.sessao,
                      comando='dados.' + comando, args=list(args), kwargs={})
        for tentativa in range(2):
            try:
                resposta = chamar(self.nome, pedido, self.producao)
                break
            except ERROS_TRANSPORTE:
                if tentativa == 0:
                    continue
                raise OSError('O agente não respondeu. Confira o histórico antes de iniciar outra importação: '
                              'o lote pode ter sido concluído. Uma nova ação terá outro identificador.') from None
        if resposta.get('v') != VERSAO or resposta.get('id') != pedido['id']:
            raise OSError('Resposta incompatível do agente.')
        if not resposta.get('ok'):
            raise ValueError(resposta.get('mensagem', 'Operação não concluída.'))
        return decodificar(resposta['resultado'])

    def executar(self, tipo, caminho, senha, progresso):
        conteudo = b'' if tipo == 'exportar' else ler_arquivo(caminho, progresso)
        resumo = hashlib.sha256(conteudo).hexdigest() if conteudo else ''
        operacao = str(uuid4())
        iniciou = False
        try:
            if tipo != 'exportar':
                operacao = self.journal.iniciar(f'{tipo}:{len(conteudo)}:{resumo}')
            estado = self.pedir('iniciar', operacao, tipo, senha, len(conteudo), resumo)
            iniciou = True
            senha = None
            if not estado['concluido']:
                for offset in range(estado['recebido'], len(conteudo), BLOCO):
                    bloco = base64.b64encode(conteudo[offset:offset + BLOCO]).decode('ascii')
                    estado = self.pedir('enviar', operacao, offset, bloco)
                    progresso(estado['etapa'], estado['feitos'], estado['total'])
            conteudo = b''
            while not estado['concluido']:
                if estado['erro']:
                    if self.journal.trava:
                        self.journal.confirmar()
                    raise ValueError(estado['erro'])
                estado = self.pedir('passo', operacao)
                progresso(estado['etapa'], estado['feitos'], estado['total'])
            total = estado['bytes_saida']
            if tipo == 'exportar':
                with SaidaAtomica(caminho) as arquivo:
                    self._baixar(operacao, total, arquivo.write, progresso)
                resultado = {'arquivo': str(Path(caminho)), 'exportado': True}
            else:
                partes = bytearray()
                self._baixar(operacao, total, partes.extend, progresso)
                resultado = ler_json(bytes(partes))
                self.journal.confirmar()
            return resultado
        finally:
            senha = None
            if iniciou:
                try:
                    self.pedir('liberar', operacao)
                except (OSError, ValueError):
                    pass  # O agente aborta transações abandonadas após um minuto sem contato.
            self.journal.fechar()

    def _baixar(self, operacao, total, gravar, progresso):
        offset = 0
        while offset < total:
            bloco = base64.b64decode(self.pedir('baixar', operacao, offset), validate=True)
            if not bloco or len(bloco) > min(BLOCO, total - offset):
                raise OSError('Download incompleto. O arquivo de destino não foi substituído.')
            gravar(bloco)
            offset += len(bloco)
            progresso('Recebimento do resultado', offset, total)
