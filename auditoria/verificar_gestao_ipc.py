"""Transferências e interrupções contra agente Windows real, em pasta temporária."""
import base64
import hashlib
import json
import multiprocessing
from pathlib import Path
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from auditoria import verificar_ipc
from auditoria.verificar_gestao_dados import csv_bytes, linha
from servico.cliente import Cliente
from servico.executar import executar
from servico.pipe import chamar
from servico.transferencia import Transferencia


class Transferencias(unittest.TestCase):
    setUp = verificar_ipc.PipeWindows.setUp
    tearDown = verificar_ipc.PipeWindows.tearDown

    def preparar(self):
        self.cliente.abrir('', 'senha-transferencia', 'senha-transferencia')
        arq = Path(self.tmp.name) / 'produtos.csv'
        arq.write_bytes(csv_bytes([linha(), linha(2)]))
        return arq

    def test_exportar_importar_restaurar_via_blocos_reais(self):
        entrada = self.preparar()
        progresso = []
        informar = lambda *p: progresso.append(p)
        t = Transferencia(self.cliente)
        resultado = t.executar('importar', entrada, 'senha-transferencia', informar)
        self.assertEqual(resultado['novos'], 2)
        destino = Path(self.tmp.name) / 'copia.gsdados.json'
        t.executar('exportar', destino, 'senha-transferencia', informar)
        self.assertTrue(destino.exists())
        self.assertEqual(len(json.loads(destino.read_bytes())['tabelas']['Produtos']['linhas']), 2)
        t.executar('importar', entrada, 'senha-transferencia', informar)
        self.assertEqual(self.cliente.chamar('estoque.obter_produto', 1).estoque_atual, 6)
        resultado = t.executar('restaurar', destino, 'senha-transferencia', informar)
        self.assertTrue(resultado['restaurado'])
        self.assertEqual(self.cliente.chamar('estoque.obter_produto', 1).estoque_atual, 3)
        self.assertTrue(any(p[0] == 'Recebimento do resultado' and p[1] == p[2] for p in progresso))

    def test_resposta_perdida_depois_commit_nao_soma_duas_vezes(self):
        entrada = self.preparar()
        def perder(nome, pedido, producao):
            resposta = chamar(nome, pedido, producao)
            if pedido['comando'] == 'dados.passo' and resposta.get('resultado', {}).get('concluido'):
                raise OSError('resposta perdida após commit')
            return resposta
        with patch('servico.transferencia.chamar', side_effect=perder):
            with self.assertRaises(OSError):
                Transferencia(self.cliente).executar('importar', entrada, 'senha-transferencia', lambda *p: None)
        self.assertEqual(self.cliente.chamar('estoque.obter_produto', 1).estoque_atual, 3)
        self.assertNotEqual(json.loads((self.raiz / 'gestao_pendentes.json').read_text()), {})
        resultado = Transferencia(self.cliente).executar('importar', entrada, 'senha-transferencia', lambda *p: None)
        self.assertEqual(resultado['novos'], 2)
        self.assertEqual(self.cliente.chamar('estoque.obter_produto', 1).estoque_atual, 3)
        self.assertEqual(json.loads((self.raiz / 'gestao_pendentes.json').read_text()), {})

    def test_encerramento_brusco_rollback_sqlcipher(self):
        self.preparar()
        conteudo = csv_bytes([linha(n) for n in range(1, 202)])
        op = str(uuid4())
        self.cliente.chamar('dados.iniciar', op, 'importar', 'senha-transferencia', len(conteudo), hashlib.sha256(conteudo).hexdigest())
        self.cliente.chamar('dados.enviar', op, 0, base64.b64encode(conteudo).decode('ascii'))
        self.assertEqual(self.cliente.chamar('dados.passo', op)['feitos'], 100)
        self.reiniciar_bruscamente()
        self.assertEqual(self.cliente.chamar('estoque.listar_produtos'), [])

    def test_encerramento_brusco_durante_restore_preserva_base_atual(self):
        entrada = self.preparar()
        entrada.write_bytes(csv_bytes([linha(n) for n in range(1, 122)]))
        t = Transferencia(self.cliente)
        t.executar('importar', entrada, 'senha-transferencia', lambda *p: None)
        copia = Path(self.tmp.name) / 'backup.gsdados.json'
        t.executar('exportar', copia, 'senha-transferencia', lambda *p: None)
        self.cliente.chamar('estoque.registrar_entrada', 1, 7)
        conteudo = copia.read_bytes()
        op = str(uuid4())
        self.cliente.chamar('dados.iniciar', op, 'restaurar', 'senha-transferencia', len(conteudo), hashlib.sha256(conteudo).hexdigest())
        from gestao.arquivos import BLOCO
        for offset in range(0, len(conteudo), BLOCO):
            self.cliente.chamar('dados.enviar', op, offset, base64.b64encode(conteudo[offset:offset + BLOCO]).decode('ascii'))
        for _ in range(100):
            estado = self.cliente.chamar('dados.passo', op)
            self.assertIsNone(estado['erro'])
            if estado['etapa'] == 'Restauração de registros':
                break
        else:
            self.fail('Restauração não iniciou')
        self.reiniciar_bruscamente()
        self.assertEqual(self.cliente.chamar('estoque.obter_produto', 1).estoque_atual, 10)
        self.assertEqual(len(self.cliente.chamar('estoque.listar_produtos')), 121)
        # O agente continua apto a gravar eventos protegidos por triggers.
        self.cliente.chamar('estoque.registrar_saida', 1, 1)
        self.assertEqual(self.cliente.chamar('estoque.obter_produto', 1).estoque_atual, 9)

    def reiniciar_bruscamente(self):
        self.processo.terminate()
        self.processo.join(10)
        # terminate pode interromper Event.wait segurando o lock do Event antigo.
        self.parar = multiprocessing.Event()
        self.processo = multiprocessing.Process(target=executar, args=(self.raiz, self.parar))
        self.processo.start()
        self.cliente = Cliente(self.raiz)
        for _ in range(60):
            try:
                self.cliente.chamar('status')
                break
            except Exception:
                time.sleep(.1)
        self.cliente.abrir('senha-transferencia')


if __name__ == '__main__':
    unittest.main()
