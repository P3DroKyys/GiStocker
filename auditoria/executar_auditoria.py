"""Executa a suíte isolada e grava evidências. Não inicia o aplicativo real."""
from contextlib import closing
from datetime import datetime
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
from time import perf_counter
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DESTINO = ROOT / 'auditoria' / 'resultados_correcao_20261001'
DESTINO.mkdir(exist_ok=True)


def hashes_fontes():
    arquivos = list(ROOT.glob('*.py')) + list(ROOT.glob('*.bat')) + [ROOT / 'requirements.txt']
    for pasta in ('controllers', 'models', 'views', 'utils', 'assets'):
        arquivos.extend(p for p in (ROOT / pasta).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in arquivos}


def main():
    antes = hashes_fontes()
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'auditoria'), pattern='verificar*.py')
    inicio = perf_counter()
    with (DESTINO / 'testes.txt').open('w', encoding='utf-8') as f:
        resultado = unittest.TextTestRunner(stream=f, verbosity=2).run(suite)
    duracao = perf_counter() - inicio
    dados = {
        'executado_em': datetime.now().isoformat(),
        'python': platform.python_version(), 'plataforma': platform.platform(),
        'bibliotecas': {n: version(n) for n in ('customtkinter', 'pandas', 'matplotlib', 'Pillow', 'pyinstaller')},
        'total': resultado.testsRun,
        'aprovados': resultado.testsRun - len(resultado.expectedFailures) - len(resultado.errors) - len(resultado.failures) - len(resultado.skipped) - len(resultado.unexpectedSuccesses),
        'defeitos_reproduzidos': [{'teste': t.id(), 'evidencia': e} for t, e in resultado.expectedFailures],
        'erros_inesperados': [{'teste': t.id(), 'evidencia': e} for t, e in resultado.errors],
        'falhas_inesperadas': [{'teste': t.id(), 'evidencia': e} for t, e in resultado.failures],
        'sucessos_inesperados': [t.id() for t in resultado.unexpectedSuccesses],
        'ignorados': [(t.id(), motivo) for t, motivo in resultado.skipped],
        'segundos_suite': duracao,
    }
    # Carga sintética: banco em memória, sem widgets ou disco de produção.
    from controllers.controllers import ControladorEstoque, ControladorRelatorios
    from models.models import BancoDados
    import config
    bd = BancoDados(':memory:', permitir_legado=True)
    try:
        c, r = ControladorEstoque(bd), ControladorRelatorios(bd)
        inicio = perf_counter()
        with bd.transacao():
            for i in range(5000):
                p = c.cadastrar_produto(f'Produto fictício {i:05}', config.MARCAS[i % len(config.MARCAS)],
                                       config.CATEGORIAS[i % len(config.CATEGORIAS)], 30, 10, 10)
                c.registrar_saida(p.id, 1)
        metricas = {'produtos': 5000, 'movimentacoes': 10000, 'preparacao_s': perf_counter() - inicio}
        for nome, chamada in [('listar_catalogo', c.listar_produtos),
                              ('buscar_texto', lambda: c.buscar_produtos('fictício')),
                              ('listar_historico', c.listar_logs),
                              ('kpis', r.obter_kpis), ('curva_a', r.curva_a)]:
            inicio = perf_counter()
            valor = chamada()
            metricas[nome] = {'segundos': perf_counter() - inicio, 'registros_ou_chaves': len(valor)}
        assert r.obter_kpis()['total_itens'] == 45000
        assert bd.buscar_um('PRAGMA integrity_check')[0] == 'ok'
        dados['carga_sintetica'] = metricas
    finally:
        bd.fechar()
    depois = hashes_fontes()
    dados['fontes_app_inalterados_durante_execucao'] = antes == depois
    dados['hashes_fontes'] = depois
    # Inspeção estática de recursos da build; não equivale a iniciar o .exe.
    from PyInstaller.archive.readers import CArchiveReader
    candidatos = list((ROOT / 'dist').glob('GiStocker_*/GestorEstoque/GestorEstoque.exe'))
    exe = max(candidatos, key=lambda p: p.stat().st_mtime) if candidatos else ROOT / 'dist' / 'GestorEstoque' / 'GestorEstoque.exe'
    if exe.exists():
        arquivo = CArchiveReader(str(exe))
        pyz = arquivo.open_embedded_archive('PYZ.pyz')
        nomes = ['config', 'controllers.controllers', 'models.models', 'utils.gtin',
                 'views.main_view', 'views.view_operacao', 'views.view_cadastro',
                 'views.view_admin', 'views.painel_produtos', 'views.view_dashboard', 'views.view_relatorios']
        dados['build_inspecao_estatica'] = {
            'caminho': str(exe),
            'exe_bytes': exe.stat().st_size,
            'modulos_presentes': {nome: nome in pyz.toc for nome in nomes},
            'recursos_iguais_fonte': {p.name: (exe.parent / '_internal' / 'assets' / p.name).is_file()
                and hashlib.sha256(p.read_bytes()).hexdigest() == hashlib.sha256(
                    (exe.parent / '_internal' / 'assets' / p.name).read_bytes()).hexdigest()
                for p in (ROOT / 'assets').iterdir() if p.is_file()},
        }
    (DESTINO / 'resultados.json').write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in dados.items() if k not in ('hashes_fontes', 'defeitos_reproduzidos')}, ensure_ascii=False, indent=2))
    print('Defeitos reproduzidos:', len(resultado.expectedFailures))
    print('Evidências:', DESTINO)
    return 0 if resultado.wasSuccessful() and antes == depois else 1


if __name__ == '__main__':
    sys.exit(main())
