<div align="center">
  <img src="assets/gistocker.png" alt="GiStocker" width="240">
  <h1>GiStocker</h1>
  <p>Gestão de estoque para lojas de cosméticos, com rastreabilidade e proteção de dados locais.</p>
  <p><strong>Python · CustomTkinter · SQLCipher/SQLite · Windows</strong></p>
</div>

## O projeto

O GiStocker nasceu da necessidade de organizar o estoque de uma loja de cosméticos: cadastrar produtos, controlar entradas e saídas, consultar indicadores e entender quem alterou cada cadastro. É uma aplicação desktop local, pensada para uso com leitor de código de barras USB e para uma rotina que exige consulta rápida e histórico confiável.

Projeto pessoal de **[P3DroKyys](https://github.com/P3DroKyys)**, responsável pela concepção, definição dos requisitos, organização dos fluxos e evolução do sistema. O desenvolvimento contou com apoio de ferramentas de inteligência artificial na implementação, revisão e documentação. Este repositório apresenta o código, as decisões técnicas e as verificações registradas ao longo dessa evolução.

## Funcionalidades

| Área | O que oferece |
| --- | --- |
| Cadastro | Produtos com nome, marca, categoria, preço, custo e múltiplos códigos GTIN com validação do dígito verificador. |
| Estoque | Entrada, saída, ajuste e cálculo de custo médio ponderado, com registro de movimentações. |
| Administração | Edição completa, seleção em intervalo com Shift+Clique e exclusão em lote mediante confirmação de senha. |
| Auditoria | Histórico de alterações com os valores anteriores e posteriores, separado dos relatórios de movimentação. |
| Cadastro em massa | Importação de Excel e CSV; modelo `.xlsx` com listas suspensas de marca e categoria. |
| Indicadores | Dashboard com gráficos e informações de estoque, custos e valores de venda. |
| Pesquisa | Busca por nome, marca, categoria, ID e códigos, com normalização de acentos e sugestões aproximadas. |
| Proteção de dados | Banco SQLCipher, bloqueio de sessão, validação de senha no serviço e cópias de segurança. |
| Interface | Temas claro e escuro, navegação por áreas e diálogos próprios. |

## Decisões de engenharia

- **Separação de responsabilidades:** interface, regras de negócio, persistência e serviço local em módulos próprios.
- **Integridade do estoque:** transações, validação de GTIN e testes de rollback e recuperação.
- **Auditoria de cadastro:** alterações preservam o antes e o depois para permitir investigação.
- **Importação reaproveitada:** Configurações e Cadastro utilizam o mesmo fluxo de processamento de planilhas.
- **Dependências reproduzíveis:** versões e hashes registrados em `requirements.lock`, incluindo componentes nativos para Windows.
- **Dados de demonstração isolados:** prévias e testes usam bancos temporários, separados do estoque da instalação.

## Arquitetura

```text
views/          Interface desktop e componentes reutilizáveis
controllers/    Operações de estoque, validações e relatórios
models/         Persistência, modelos e proteção do banco
servico/        Agente local, autenticação e comunicação com a interface
multicanal/     Motor de eventos e laboratório local de integrações
gestao/        Backup, restauração e importação de planilhas
utils/          GTIN, pesquisa e conversão de valores
assets/         Identidade visual, ícones e tema
auditoria/     Testes, prévias e evidências técnicas
```

A interface se comunica com um agente local responsável pelo acesso ao banco protegido. Os detalhes e limites dessa proteção estão em [Segurança](SEGURANCA.md).

## Executar localmente

**Ambiente de desenvolvimento:** Windows x64 e Python **3.14 de 64 bits**. As wheels nativas incluídas em `vendor/` são específicas desse ambiente.

```powershell
git clone https://github.com/P3DroKyys/GiStocker.git
cd GiStocker
.\1_preparar_ambiente.bat
.\2_executar.bat
```

Uma instalação vazia solicita a criação de senha. Para gerar uma distribuição do aplicativo, use `3_gerar_exe.bat`. O [guia de desenvolvimento](GUIA_DESENVOLVIMENTO.md) descreve os procedimentos e o histórico de versões.

### Explorar com dados fictícios

Depois de preparar o ambiente:

```powershell
.\.venv\Scripts\python.exe -B auditoria/preview_visual.py --tema dark --tela dashboard
```

A prévia utiliza uma base temporária e pode ser aberta também em outras telas; consulte `--help` para as opções.

## Testes

A pasta `auditoria/` contém testes de regras de negócio, segurança, importação, interface e comunicação entre processos. Para executar a descoberta das suítes:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s auditoria -p "verificar*.py"
```

Alguns testes dependem de widgets reais e de uma sessão gráfica no Windows. Relatórios históricos em `auditoria/` descrevem verificações de versões específicas; não representam certificação do estado atual.

## Estado e limites

O foco funcional é o **estoque local**. O módulo multicanal é uma **prévia com simulação**: não representa integração homologada com lojas reais da Shopee ou TikTok Shop. O estado e o roteiro de validação estão no [guia multicanal](GUIA_MULTICANAL.md).

A distribuição empacotada precisa ser validada em Windows limpo antes de uso por terceiros. Exportações JSON de backup contêm dados sem criptografia e devem ser protegidas pelo usuário. Este repositório não distribui o banco da loja nem credenciais de operação.

## Documentação

- [Guia de desenvolvimento e histórico](GUIA_DESENVOLVIMENTO.md)
- [Importação de produtos e backup](GESTAO_DADOS.md)
- [Segurança e recuperação de dados](SEGURANCA.md)
- [Prévia multicanal e roteiro de validação](GUIA_MULTICANAL.md)
- [Contexto técnico e arquitetura](CONTEXTO_CODIGO.md)
- [Licenças dos componentes de terceiros](licencas/)

---

**Portfólio:** [github.com/P3DroKyys](https://github.com/P3DroKyys)
