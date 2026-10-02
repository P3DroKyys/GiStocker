"""Recebe uma build, copia para diretório descartável e testa seu agente compilado."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from servico.cliente import Cliente


def testar(exe):
    exe=Path(exe).resolve()
    with tempfile.TemporaryDirectory(prefix='gistocker_build_teste_') as tmp:
        pasta=Path(tmp)/'aplicativo'
        shutil.copytree(exe.parent,pasta)
        processo=subprocess.Popen([str(pasta/exe.name),'--agente'],stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        cliente=Cliente(pasta/'dados')
        try:
            for _ in range(100):
                if processo.poll() is not None:
                    raise RuntimeError('O agente compilado encerrou durante a inicialização.')
                try: cliente.chamar('status'); break
                except Exception: time.sleep(.2)
            else: raise RuntimeError('Agente compilado indisponível.')
            assert cliente.modo=='novo'
            cliente.abrir('','senha-build-teste-739','senha-build-teste-739')
            estoque,relatorios=cliente.criar_controladores()
            p=estoque.cadastrar_produto('Teste da build','O Boticário','Perfumaria',quantidade_inicial=8,codigos=['7891000100103'])
            estoque.registrar_saida(p.id,2)
            assert estoque.obter_produto(p.id).estoque_atual==6
            assert relatorios.exportar_protegido().is_file()
            cliente.chamar('integracoes.ativar_simulacao')
            cliente.chamar('integracoes.catalogo_exemplo')
            for remoto in ('SHOPEE:1','TIKTOK:1'): cliente.chamar('integracoes.vincular',remoto,p.id)
            cliente.chamar('integracoes.iniciar_ensaio')
            cliente.chamar('integracoes.passo')
            painel=cliente.chamar('integracoes.painel')
            assert painel['simulacao']['produtos'][0]['exposta']==3
            cliente.chamar('integracoes.encerrar')
            cliente.fechar()
            cliente.abrir('senha-build-teste-739')
            assert estoque.obter_produto(p.id).estoque_atual==6
            print('OK: executável compilado, IPC, login, cadastro, baixa, backup, simulação, encerramento e reabertura.')
        finally:
            cliente.fechar()
            processo.terminate()
            processo.wait(timeout=15)


if __name__=='__main__': testar(sys.argv[1])
