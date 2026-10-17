"""Empacota em um destino exclusivo; nunca limpa uma distribuição anterior."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import importlib.metadata
from uuid import uuid4


def gerar_build(projeto=None, executar=subprocess.run):
    import customtkinter
    import rapidfuzz
    from models.seguranca import verificar_motor
    verificar_motor()
    projeto = Path(projeto or Path(__file__).resolve().parent).resolve()
    dist = projeto / 'dist'
    dist.mkdir(exist_ok=True)
    # Diretório de distribuição, não temporário: herda as permissões de dist.
    # No Python 3.13+ / Windows, mkdtemp cria ACL privada ao usuário compilador,
    # que pode ser uma conta de automação diferente da conta que abrirá a build.
    while True:
        destino = dist / f'GiStocker_{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:12]}'
        try:
            destino.mkdir()
        except FileExistsError:
            continue
        break
    trabalho = projeto / 'build' / destino.name
    trabalho.mkdir(parents=True)
    comando = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--windowed',
               '--collect-all', 'sqlcipher3', '--collect-all', 'rapidfuzz',
               '--name', 'GestorEstoque', '--icon', str(projeto / 'assets' / 'icone_gistocker.ico'),
               '--add-data', f'{Path(customtkinter.__file__).parent};customtkinter',
               '--add-data', f'{projeto / "assets"};assets',
               '--distpath', str(destino), '--workpath', str(trabalho),
               '--specpath', str(trabalho), str(projeto / 'main.py')]
    # Wheels Windows usam delvewheel: a DLL MSVC renomeada fica em uma pasta
    # irmã, fora de rapidfuzz. collect-all sozinho não a inclui.
    libs_busca = Path(rapidfuzz.__file__).parent.parent / 'rapidfuzz.libs'
    for biblioteca in sorted(libs_busca.glob('*.dll')):
        comando.extend(['--add-binary', f'{biblioteca};rapidfuzz.libs'])
    executar(comando, cwd=projeto, check=True)
    exe = destino / 'GestorEstoque' / 'GestorEstoque.exe'
    if not exe.is_file():
        raise RuntimeError('A geração terminou sem produzir o executável esperado.')
    # Documentação e avisos de licença acompanham a distribuição. O manifesto
    # permite conferir cópias; não substitui assinatura digital por certificado.
    for nome in ('SEGURANCA.md', 'GUIA_MULTICANAL.md', 'RELATORIO_MULTICANAL.md', 'GESTAO_DADOS.md'):
        origem = projeto / nome
        if origem.is_file():
            shutil.copy2(origem, exe.parent / nome)
    licencas = projeto / 'licencas'
    if licencas.is_dir():
        shutil.copytree(licencas, exe.parent / 'licencas')
    componentes = sorted([{'name': d.metadata['Name'], 'version': d.version} for d in importlib.metadata.distributions()],key=lambda d:d['name'].lower())
    (exe.parent / 'SBOM.json').write_text(json.dumps({'formato':'inventario-dependencias-python','componentes':componentes},indent=2),encoding='utf-8')
    proibidos = {'estoque.db','configuracoes.db','acesso.json','operadores.json','simulacao.db','.env'}
    if any(f.name.lower() in proibidos or f.suffix.lower() in ('.gsbackup','.gsa','.pfx') for f in exe.parent.rglob('*') if f.is_file()):
        raise RuntimeError('A distribuição contém arquivo de dados ou credencial proibido.')
    for arquivo in exe.parent.rglob('*'):
        if arquivo.is_file() and arquivo.suffix.lower() in ('.pem','.key') and b'PRIVATE KEY-----' in arquivo.read_bytes():
            raise RuntimeError('A distribuição contém uma chave privada.')
    hashes = {}
    for arquivo in sorted(exe.parent.rglob('*')):
        if arquivo.is_file():
            with arquivo.open('rb') as conteudo:
                hashes[arquivo.relative_to(exe.parent).as_posix()] = hashlib.file_digest(conteudo, 'sha256').hexdigest()
    (exe.parent / 'SHA256.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    return exe


def gerar_instalador(exe, projeto=None):
    """Compilação opcional, sem instalar/ativar nada na máquina de desenvolvimento."""
    import config
    projeto=Path(projeto or Path(__file__).resolve().parent)
    compilador=projeto/'ferramentas'/'inno'/'ISCC.exe'
    if not compilador.exists():
        encontrado=shutil.which('ISCC.exe')
        if not encontrado:
            return None
        compilador=Path(encontrado)
    release=config.VERSAO_APP+'_'+exe.parent.parent.name.removeprefix('GiStocker_')
    subprocess.run([str(compilador),'/Qp','/DBuildDir='+str(exe.parent),'/DRelease='+release,str(projeto/'instalador'/'GiStocker.iss')],check=True,cwd=projeto)
    instalador=exe.parent.parent/'Instalador'/('GiStocker-Setup-'+release+'.exe')
    if not instalador.is_file():
        raise RuntimeError('Instalador não foi produzido.')
    with instalador.open('rb') as f:
        resumo=hashlib.file_digest(f,'sha256').hexdigest()
    instalador.with_suffix('.sha256').write_text(resumo+'  '+instalador.name+'\n',encoding='ascii')
    return instalador


if __name__ == '__main__':
    try:
        exe = gerar_build()
        instalador = gerar_instalador(exe)
    except Exception as falha:
        print(f'ERRO ao gerar: {falha}', file=sys.stderr)
        sys.exit(1)
    print(f'\nPronto! Executável: {exe}\nPara distribuir, copie a pasta inteira: {exe.parent}')
    print('Versões anteriores e seus dados foram preservados.')
    print(f'Instalador: {instalador}' if instalador else 'Instalador não gerado: instale o compilador Inno Setup. A build portátil está pronta.')
