"""Extensão v2, exclusivamente aditiva. DDL constante, nunca recebido por IPC."""

SQL = """
CREATE TABLE Canais (id TEXT PRIMARY KEY CHECK(id IN ('SHOPEE','TIKTOK')), nome TEXT NOT NULL);
CREATE TABLE Lojas_Externas (id TEXT PRIMARY KEY, canal TEXT NOT NULL REFERENCES Canais(id),
 nome TEXT NOT NULL, ambiente TEXT NOT NULL CHECK(ambiente='SIMULADO'), autorizada INTEGER NOT NULL DEFAULT 0 CHECK(autorizada IN(0,1)));
CREATE TABLE Catalogo_Remoto (id TEXT PRIMARY KEY, loja TEXT NOT NULL REFERENCES Lojas_Externas(id),
 produto_externo TEXT NOT NULL, sku TEXT NOT NULL, armazem TEXT NOT NULL, titulo TEXT NOT NULL,
 marca TEXT NOT NULL DEFAULT '', gtin TEXT NOT NULL DEFAULT '', variacao TEXT NOT NULL DEFAULT '',
 quantidade INTEGER NOT NULL DEFAULT 0 CHECK(quantidade>=0), UNIQUE(loja,produto_externo,sku,armazem));
CREATE TABLE Vinculos_SKU (remoto TEXT PRIMARY KEY REFERENCES Catalogo_Remoto(id), produto_id INTEGER NOT NULL REFERENCES Produtos(id));
CREATE TABLE Cobertura_Produto_Canal (produto_id INTEGER NOT NULL REFERENCES Produtos(id), canal TEXT NOT NULL REFERENCES Canais(id),
 estado TEXT NOT NULL CHECK(estado IN('PENDENTE_VINCULO','VINCULADO','NAO_PUBLICADO','IGNORADO','PAUSADO')), PRIMARY KEY(produto_id,canal));
CREATE TABLE Politicas_Alocacao (produto_id INTEGER PRIMARY KEY REFERENCES Produtos(id), percentual INTEGER NOT NULL DEFAULT 50 CHECK(percentual BETWEEN 0 AND 100),
 margem INTEGER NOT NULL DEFAULT 0 CHECK(margem>=0), quarentena INTEGER NOT NULL DEFAULT 0 CHECK(quarentena>=0));
CREATE TABLE Estado_Alocacao (produto_id INTEGER PRIMARY KEY REFERENCES Produtos(id), elegiveis TEXT NOT NULL, sobra INTEGER NOT NULL, vencedor TEXT,
 geracao INTEGER NOT NULL DEFAULT 1);
CREATE TABLE Eventos_Estoque (id INTEGER PRIMARY KEY AUTOINCREMENT, chave TEXT UNIQUE NOT NULL,
 produto_id INTEGER NOT NULL REFERENCES Produtos(id), delta INTEGER NOT NULL, origem TEXT NOT NULL,
 natureza TEXT NOT NULL, referencia TEXT, log_id INTEGER REFERENCES Logs_Movimentacao(id),
 criado TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
CREATE TABLE Pedidos_Externos (id TEXT PRIMARY KEY, loja TEXT NOT NULL REFERENCES Lojas_Externas(id), pedido TEXT NOT NULL,
 estado TEXT NOT NULL, UNIQUE(loja,pedido));
CREATE TABLE Itens_Pedido_Externo (id TEXT PRIMARY KEY, pedido_id TEXT NOT NULL REFERENCES Pedidos_Externos(id),
 linha TEXT NOT NULL, remoto TEXT NOT NULL REFERENCES Catalogo_Remoto(id), produto_id INTEGER NOT NULL REFERENCES Produtos(id),
 quantidade INTEGER NOT NULL CHECK(quantidade>0), cancelada INTEGER NOT NULL DEFAULT 0,
 versao INTEGER NOT NULL DEFAULT 0, estado TEXT NOT NULL, UNIQUE(pedido_id,linha), CHECK(cancelada BETWEEN 0 AND quantidade));
CREATE TABLE Reservas (item TEXT PRIMARY KEY REFERENCES Itens_Pedido_Externo(id), produto_id INTEGER NOT NULL REFERENCES Produtos(id),
 quantidade INTEGER NOT NULL CHECK(quantidade>=0));
CREATE TABLE Inbox_Eventos (chave TEXT PRIMARY KEY, conteudo TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'PENDENTE', recebido TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE Outbox_Comandos (id INTEGER PRIMARY KEY AUTOINCREMENT, remoto TEXT NOT NULL REFERENCES Catalogo_Remoto(id),
 quantidade INTEGER NOT NULL CHECK(quantidade>=0), geracao INTEGER NOT NULL, estado TEXT NOT NULL DEFAULT 'PENDENTE',
 tentativas INTEGER NOT NULL DEFAULT 0, proxima REAL NOT NULL DEFAULT 0, UNIQUE(remoto,geracao));
CREATE TABLE Estado_SKU_Canal (remoto TEXT PRIMARY KEY REFERENCES Catalogo_Remoto(id), desejada INTEGER NOT NULL DEFAULT 0,
 enviada INTEGER NOT NULL DEFAULT 0, confirmada INTEGER NOT NULL DEFAULT 0, observada INTEGER NOT NULL DEFAULT 0,
 exposta INTEGER NOT NULL DEFAULT 0, geracao INTEGER NOT NULL DEFAULT 0, incerta INTEGER NOT NULL DEFAULT 0,
 CHECK(min(desejada,enviada,confirmada,observada,exposta)>=0));
CREATE TABLE Cursores_Sincronizacao (loja TEXT PRIMARY KEY REFERENCES Lojas_Externas(id), cursor TEXT, ultima_conciliacao TEXT);
CREATE TABLE Incidentes_Sync (id INTEGER PRIMARY KEY AUTOINCREMENT, produto_id INTEGER REFERENCES Produtos(id),
 tipo TEXT NOT NULL, referencia TEXT NOT NULL, resolvido INTEGER NOT NULL DEFAULT 0, criado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(tipo,referencia));
CREATE TABLE Componentes_Kit (kit INTEGER NOT NULL REFERENCES Produtos(id), componente INTEGER NOT NULL REFERENCES Produtos(id),
 quantidade INTEGER NOT NULL CHECK(quantidade>0), PRIMARY KEY(kit,componente), CHECK(kit<>componente));
CREATE TABLE Comandos_IPC (id TEXT PRIMARY KEY, resumo TEXT NOT NULL, resposta TEXT NOT NULL, criado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE Config_Multicanal (id INTEGER PRIMARY KEY CHECK(id=1), estado TEXT NOT NULL DEFAULT 'FISICO' CHECK(estado IN('FISICO','MULTICANAL_CONFIGURANDO','MULTICANAL_ATIVO','MULTICANAL_PAUSADO','ENCERRANDO_MULTICANAL')));
"""

TRIGGERS = {
    'eventos_sem_update': "CREATE TRIGGER eventos_sem_update BEFORE UPDATE ON Eventos_Estoque BEGIN SELECT RAISE(ABORT,'Eventos imutaveis'); END",
    'eventos_sem_delete': "CREATE TRIGGER eventos_sem_delete BEFORE DELETE ON Eventos_Estoque BEGIN SELECT RAISE(ABORT,'Eventos imutaveis'); END",
}
TABELAS = {s.split()[2] for s in SQL.split(';') if s.strip()}
INDICES = {
    'idx_eventos_produto': 'CREATE INDEX idx_eventos_produto ON Eventos_Estoque(produto_id)',
    'idx_eventos_log': 'CREATE INDEX idx_eventos_log ON Eventos_Estoque(log_id)',
}


def migrar(con):
    for instrucao in SQL.split(';'):
        if instrucao.strip():
            con.execute(instrucao)
    for instrucao in TRIGGERS.values():
        con.execute(instrucao)
    con.executemany('INSERT INTO Canais VALUES (?,?)', [('SHOPEE', 'Shopee'), ('TIKTOK', 'TikTok Shop')])
    con.execute('INSERT INTO Config_Multicanal(id) VALUES(1)')
    con.execute('PRAGMA user_version=2')


def conferir_objeto(tipo, nome, sql):
    if tipo == 'index' and nome in INDICES:
        return ' '.join((sql or '').split()) == INDICES[nome]
    if tipo == 'table' and nome in TABELAS:
        esperado = next(s.strip() for s in SQL.split(';') if s.strip() and s.split()[2] == nome)
        return ' '.join((sql or '').split()) == ' '.join(esperado.split())
    if tipo == 'trigger' and nome in TRIGGERS:
        return sql == TRIGGERS[nome]
    if tipo == 'index' and sql is None:
        return any(nome.startswith('sqlite_autoindex_' + t + '_') for t in TABELAS)
    return False
