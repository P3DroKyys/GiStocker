"""Jobs cooperativos: o mesmo agente mantém a transação entre lotes de linhas.

Uploads/downloads em blocos evitam paths arbitrários sob a conta do serviço.
Senhas e arquivos de entrada nunca são gravados no journal da interface.
"""
import base64
import hashlib
import json
import time
from uuid import UUID

from gestao import backup, planilha
from gestao.arquivos import BLOCO, LIMITE_ARQUIVO, json_bytes
from models.seguranca import ErroSeguranca

SEGUNDOS_ABANDONO = 60


class GestaoDados:
    def __init__(self, cofre):
        self.cofre = cofre
        self.job = None
        self.tentativas = 0
        self.tentar_apos = 0

    @property
    def ocupado(self):
        return self.job is not None

    @property
    def abandonado(self):
        """O cliente ativo conversa sem pausas; o silêncio indica interface encerrada."""
        return self.job is not None and time.monotonic() - self.job['uso'] > SEGUNDOS_ABANDONO

    def fechar(self):
        if self.job and self.job.get('gerador'):
            self.job['gerador'].close()  # GeneratorExit provoca rollback pelo context manager.
        self.job = None

    def manutencao(self):
        if self.abandonado:
            self.fechar()

    def _senha(self, senha):
        if time.monotonic() < self.tentar_apos:
            raise ValueError('Aguarde antes de confirmar a senha novamente.')
        if not self.cofre.verificar_senha(senha):
            self.tentativas += 1
            self.tentar_apos = time.monotonic() + min(300, 2 ** min(self.tentativas, 8))
            raise ValueError('Senha atual incorreta. Nenhum dado foi alterado.')
        self.tentativas = 0

    def iniciar(self, dono, operacao, tipo, senha, tamanho=0, sha256=''):
        UUID(operacao)
        if tipo not in ('exportar', 'restaurar', 'importar'):
            raise ValueError('Operação de dados inválida.')
        if type(tamanho) is not int or not 0 <= tamanho <= LIMITE_ARQUIVO:
            raise ValueError('O arquivo excede 64 MB.')
        if tipo != 'exportar' and (not tamanho or len(sha256) != 64 or any(c not in '0123456789abcdef' for c in sha256)):
            raise ValueError('Identificação do arquivo inválida.')
        self._senha(senha)
        assinatura = hashlib.sha256(json_bytes([tipo, tamanho, sha256])).hexdigest()
        if self.job:
            if (self.job['dono'], self.job['id'], self.job['assinatura']) != (dono, operacao, assinatura):
                raise ValueError('Outra operação de gestão de dados está em andamento.')
            self.job['uso'] = time.monotonic()
            return self.estado()
        if self.cofre.banco.conexao.execute('SELECT estado FROM Config_Multicanal').fetchone()[0] != 'FISICO':
            raise ValueError('Encerre o laboratório de integrações antes de gerenciar os dados do sistema.')
        self.job = dict(dono=dono, id=operacao, tipo=tipo, assinatura=assinatura, tamanho=tamanho,
                        sha256=sha256, entrada=bytearray(), saida=b'', recebido=0, gerador=None,
                        etapa='Aguardando arquivo' if tamanho else 'Preparando exportação', feitos=0, total=1,
                        concluido=False, erro=None, resultado=None, uso=time.monotonic())
        anterior = self.cofre.banco.conexao.execute('SELECT resumo,resposta FROM Comandos_IPC WHERE id=?', ('gestao:' + operacao,)).fetchone()
        if anterior:
            if anterior[0] != assinatura:
                self.job = None
                raise ValueError('Operação já utilizada para outro arquivo.')
            self._concluir(json.loads(anterior[1]))
        return self.estado()

    def estado(self):
        j = self.job
        return {k: j[k] for k in ('id', 'tipo', 'recebido', 'etapa', 'feitos', 'total', 'concluido', 'erro')} | {'bytes_saida': len(j['saida'])}

    def _recibo(self, resultado):
        j = self.job
        self.cofre.banco.conexao.execute(
            'INSERT OR REPLACE INTO Comandos_IPC(id,resumo,resposta) VALUES(?,?,?)',
            ('gestao:' + j['id'], j['assinatura'], json_bytes(resultado).decode('utf-8')))

    def _concluir(self, resultado):
        j = self.job
        j.update(concluido=True, resultado=resultado, etapa='Concluído', feitos=1, total=1,
                 saida=resultado if isinstance(resultado, bytes) else json_bytes(resultado), gerador=None, entrada=bytearray())

    def comando(self, dono, comando, operacao, *args):
        j = self.job
        if not j or (j['dono'], j['id']) != (dono, operacao):
            raise ErroSeguranca('Operação de dados indisponível para esta sessão.')
        j['uso'] = time.monotonic()
        if comando == 'liberar':
            self.fechar()
            return None
        if comando == 'enviar':
            if len(args) != 2 or type(args[0]) is not int or type(args[1]) is not str or len(args[1]) > 4 * BLOCO // 3 + 4:
                raise ValueError('Bloco inválido.')
            offset, texto = args
            try:
                bloco = base64.b64decode(texto, validate=True)
            except ValueError:
                raise ValueError('Bloco inválido.') from None
            if j['gerador'] or j['concluido'] or not bloco or offset < 0 or offset + len(bloco) > j['tamanho']:
                raise ValueError('Transferência fora de sequência.')
            if offset < j['recebido']:
                if bytes(j['entrada'][offset:offset + len(bloco)]) != bloco:
                    raise ValueError('Reenvio de bloco com conteúdo diferente.')
            elif offset == j['recebido']:
                j['entrada'].extend(bloco)
                j['recebido'] = len(j['entrada'])
            else:
                raise ValueError('Transferência incompleta.')
            j.update(etapa='Transferência para o agente', feitos=j['recebido'], total=j['tamanho'])
        elif comando == 'passo':
            if args:
                raise ValueError('Parâmetros inesperados.')
            if not j['concluido'] and not j['erro']:
                try:
                    if j['gerador'] is None:
                        if j['tipo'] == 'exportar':
                            j['gerador'] = backup.exportar(self.cofre.banco)
                        else:
                            if j['recebido'] != j['tamanho'] or hashlib.sha256(j['entrada']).hexdigest() != j['sha256']:
                                raise ValueError('Arquivo incompleto ou alterado durante a transferência.')
                            conteudo = bytes(j['entrada'])
                            j['entrada'].clear()
                            j['gerador'] = (backup.restaurar(self.cofre, conteudo, self._recibo)
                                            if j['tipo'] == 'restaurar' else
                                            planilha.importar(self.cofre.banco, conteudo, j['id'], self._recibo))
                    j['etapa'], j['feitos'], j['total'] = next(j['gerador'])
                except StopIteration as fim:
                    self._concluir(fim.value)
                except Exception as erro:
                    if j['gerador']:
                        j['gerador'].close()
                    if not isinstance(erro, ValueError):   # validação do arquivo não é falha técnica
                        from utils.erros import registrar_falha
                        registrar_falha(erro, pasta=self.cofre.raiz / 'logs')
                    j.update(erro=str(erro) if isinstance(erro, ValueError) else
                             'Falha ao processar o arquivo. Nenhuma alteração deste lote foi confirmada. Confira formato, espaço e permissões.',
                             gerador=None, entrada=bytearray())
            j['uso'] = time.monotonic()   # um passo longo não conta como silêncio do cliente
        elif comando == 'baixar':
            if len(args) != 1 or type(args[0]) is not int or not 0 <= args[0] <= len(j['saida']) or not j['concluido']:
                raise ValueError('Download indisponível.')
            return base64.b64encode(j['saida'][args[0]:args[0] + BLOCO]).decode('ascii')
        elif comando != 'estado' or args:
            raise ValueError('Comando de dados inválido.')
        return self.estado()
