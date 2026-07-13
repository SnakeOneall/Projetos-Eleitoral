"""
Radar Eleitoral IA - Inicialização do banco de dados.

Cria o banco SQLite com as tabelas necessárias para o MVP.
Estrutura pensada para migrar futuramente para PostgreSQL/PostGIS
sem grandes mudanças de modelagem.

Uso:
    python database/init_db.py
"""

import os
import sqlite3
from datetime import datetime

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "radar_eleitoral.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidatos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_tse TEXT,
    nome_civil TEXT NOT NULL,
    nome_urna TEXT NOT NULL,
    numero TEXT,
    cpf_mascarado TEXT,
    partido TEXT,
    sigla_partido TEXT,
    cargo TEXT,
    uf TEXT,
    ano INTEGER,
    situacao TEXT,
    origem_dados TEXT DEFAULT 'demo',
    fonte_dados TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tse_importacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ano INTEGER NOT NULL,
    uf TEXT NOT NULL,
    tipo_arquivo TEXT NOT NULL,
    arquivo_origem TEXT,
    status TEXT NOT NULL,
    quantidade_linhas INTEGER DEFAULT 0,
    data_importacao TEXT DEFAULT (datetime('now')),
    mensagem TEXT,
    hash_arquivo TEXT
);

CREATE TABLE IF NOT EXISTS candidaturas_tse (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_tse TEXT,
    ano INTEGER NOT NULL,
    turno INTEGER,
    uf TEXT,
    municipio TEXT,
    codigo_municipio_tse TEXT,
    zona TEXT,
    cargo TEXT,
    nome_civil TEXT,
    nome_urna TEXT,
    numero TEXT,
    partido TEXT,
    nome_partido TEXT,
    votos INTEGER DEFAULT 0,
    votos_validos INTEGER,
    situacao TEXT,
    origem_arquivo TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_candidaturas_tse_ano ON candidaturas_tse (ano);
CREATE INDEX IF NOT EXISTS idx_candidaturas_tse_uf ON candidaturas_tse (uf);
CREATE INDEX IF NOT EXISTS idx_candidaturas_tse_cargo ON candidaturas_tse (cargo);
CREATE INDEX IF NOT EXISTS idx_candidaturas_tse_nome_urna ON candidaturas_tse (nome_urna);
CREATE INDEX IF NOT EXISTS idx_candidaturas_tse_nome_civil ON candidaturas_tse (nome_civil);
CREATE INDEX IF NOT EXISTS idx_candidaturas_tse_numero ON candidaturas_tse (numero);
CREATE INDEX IF NOT EXISTS idx_candidaturas_tse_partido ON candidaturas_tse (partido);
CREATE INDEX IF NOT EXISTS idx_candidaturas_tse_municipio ON candidaturas_tse (municipio);
CREATE INDEX IF NOT EXISTS idx_candidaturas_tse_id_tse ON candidaturas_tse (id_tse);
CREATE INDEX IF NOT EXISTS idx_tse_importacoes_ano_uf ON tse_importacoes (ano, uf);
CREATE INDEX IF NOT EXISTS idx_tse_importacoes_status ON tse_importacoes (status);

CREATE TABLE IF NOT EXISTS geo_zonas_eleitorais (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uf TEXT,
    municipio TEXT,
    zona TEXT,
    nome_zona TEXT,
    endereco TEXT,
    bairro TEXT,
    latitude REAL,
    longitude REAL,
    fonte TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS geo_importacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT,
    fonte TEXT,
    arquivo_local TEXT,
    status TEXT,
    quantidade_linhas INTEGER DEFAULT 0,
    mensagem TEXT,
    data_importacao TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS geo_municipios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_ibge TEXT,
    codigo_tse TEXT,
    municipio TEXT,
    uf TEXT,
    latitude REAL,
    longitude REAL,
    fonte TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_geo_zonas_uf_municipio ON geo_zonas_eleitorais (uf, municipio);
CREATE INDEX IF NOT EXISTS idx_geo_zonas_chave ON geo_zonas_eleitorais (uf, municipio, zona);
CREATE INDEX IF NOT EXISTS idx_geo_importacoes_tipo_status ON geo_importacoes (tipo, status);
CREATE INDEX IF NOT EXISTS idx_geo_municipios_uf_municipio ON geo_municipios (uf, municipio);
CREATE INDEX IF NOT EXISTS idx_geo_municipios_codigo_ibge ON geo_municipios (codigo_ibge);

CREATE TABLE IF NOT EXISTS eleicoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ano INTEGER NOT NULL,
    tipo_eleicao TEXT,
    turno INTEGER,
    cargo TEXT,
    uf TEXT,
    descricao TEXT
);

CREATE TABLE IF NOT EXISTS municipios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_tse TEXT,
    codigo_ibge TEXT,
    nome TEXT NOT NULL,
    uf TEXT,
    regiao TEXT,
    populacao_estimada INTEGER
);

CREATE TABLE IF NOT EXISTS votacao_municipio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidato_id INTEGER NOT NULL,
    ano INTEGER NOT NULL,
    turno INTEGER,
    uf TEXT,
    codigo_municipio_tse TEXT,
    municipio TEXT,
    cargo TEXT,
    partido TEXT,
    votos INTEGER,
    votos_validos_municipio INTEGER,
    percentual_votos REAL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (candidato_id) REFERENCES candidatos(id)
);

CREATE TABLE IF NOT EXISTS votacao_zona (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidato_id INTEGER NOT NULL,
    ano INTEGER NOT NULL,
    turno INTEGER,
    uf TEXT,
    municipio TEXT,
    zona TEXT,
    votos INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (candidato_id) REFERENCES candidatos(id)
);

CREATE TABLE IF NOT EXISTS votacao_secao_tse (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ano INTEGER,
    turno INTEGER,
    uf TEXT,
    municipio TEXT,
    codigo_municipio_tse TEXT,
    zona TEXT,
    secao TEXT,
    local_votacao TEXT,
    endereco_local TEXT,
    bairro TEXT,
    cargo TEXT,
    id_tse TEXT,
    nome_civil TEXT,
    nome_urna TEXT,
    numero TEXT,
    partido TEXT,
    votos INTEGER DEFAULT 0,
    votos_validos INTEGER,
    origem_arquivo TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS locais_votacao_geo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ano INTEGER,
    uf TEXT,
    municipio TEXT,
    codigo_municipio_tse TEXT,
    zona TEXT,
    secao TEXT,
    local_votacao TEXT,
    endereco TEXT,
    bairro TEXT,
    distrito TEXT,
    subprefeitura TEXT,
    latitude REAL,
    longitude REAL,
    fonte TEXT,
    confianca_geocoding REAL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS territorial_importacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ano INTEGER,
    uf TEXT,
    municipio TEXT,
    tipo TEXT,
    status TEXT,
    quantidade_linhas INTEGER DEFAULT 0,
    mensagem TEXT,
    data_importacao TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_votacao_secao_tse_ano_uf ON votacao_secao_tse (ano, uf);
CREATE INDEX IF NOT EXISTS idx_votacao_secao_tse_candidato ON votacao_secao_tse (id_tse, ano);
CREATE INDEX IF NOT EXISTS idx_votacao_secao_tse_territorio ON votacao_secao_tse (uf, municipio, zona, secao);
CREATE INDEX IF NOT EXISTS idx_locais_votacao_geo_territorio ON locais_votacao_geo (ano, uf, municipio, zona, secao);
CREATE INDEX IF NOT EXISTS idx_territorial_importacoes ON territorial_importacoes (ano, uf, municipio, tipo, status);

CREATE TABLE IF NOT EXISTS emendas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parlamentar_nome TEXT,
    parlamentar_nome_civil TEXT,
    parlamentar_nome_urna TEXT,
    partido TEXT,
    uf TEXT,
    ano INTEGER,
    municipio_beneficiado TEXT,
    codigo_ibge TEXT,
    area TEXT,
    orgao TEXT,
    entidade_beneficiada TEXT,
    valor_empenhado REAL,
    valor_liquidado REAL,
    valor_pago REAL,
    fonte TEXT,
    link_fonte TEXT,
    status_validacao TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS analise_esforco_resultado (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidato_id INTEGER NOT NULL,
    municipio TEXT,
    uf TEXT,
    periodo_inicio INTEGER,
    periodo_fim INTEGER,
    votos_inicio INTEGER,
    votos_fim INTEGER,
    variacao_votos INTEGER,
    percentual_variacao REAL,
    valor_total_destinado REAL,
    valor_total_pago REAL,
    classificacao TEXT,
    leitura_ia TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (candidato_id) REFERENCES candidatos(id)
);

CREATE TABLE IF NOT EXISTS deputados_camara (
    id_camara INTEGER PRIMARY KEY,
    nome_civil TEXT,
    nome_parlamentar TEXT,
    partido TEXT,
    uf TEXT,
    situacao TEXT,
    condicao_eleitoral TEXT,
    url_foto TEXT,
    link_fonte TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS atividade_ceap (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_camara INTEGER NOT NULL,
    ano INTEGER NOT NULL,
    mes INTEGER,
    tipo_despesa TEXT,
    fornecedor TEXT,
    cnpj_cpf_fornecedor TEXT,
    valor_documento REAL DEFAULT 0,
    valor_glosa REAL DEFAULT 0,
    valor_liquido REAL DEFAULT 0,
    url_documento TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS atividade_resumo_anual (
    id_camara INTEGER NOT NULL,
    ano INTEGER NOT NULL,
    sessoes_participadas INTEGER DEFAULT 0,
    eventos_participados INTEGER DEFAULT 0,
    discursos INTEGER DEFAULT 0,
    proposicoes INTEGER DEFAULT 0,
    total_ceap_liquido REAL DEFAULT 0,
    observacao TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (id_camara, ano)
);

CREATE INDEX IF NOT EXISTS idx_atividade_ceap_dep_ano ON atividade_ceap (id_camara, ano);
CREATE INDEX IF NOT EXISTS idx_deputados_camara_uf ON deputados_camara (uf);

CREATE TABLE IF NOT EXISTS relatorios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidato_id INTEGER NOT NULL,
    titulo TEXT,
    periodo_inicio INTEGER,
    periodo_fim INTEGER,
    arquivo_pdf TEXT,
    resumo TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (candidato_id) REFERENCES candidatos(id)
);

CREATE TABLE IF NOT EXISTS planos_comunicacao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidato_id INTEGER NOT NULL,
    municipio TEXT,
    uf TEXT,
    prioridade TEXT,
    tema TEXT,
    objetivo TEXT,
    canais TEXT,
    plano_30_dias TEXT,
    plano_60_dias TEXT,
    plano_90_dias TEXT,
    risco_eleitoral TEXT,
    observacoes_compliance TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (candidato_id) REFERENCES candidatos(id)
);
"""


def get_connection():
    """Retorna uma conexão SQLite com row_factory configurado para dicts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_column(conn, table: str, column: str, definition: str):
    """Adiciona uma coluna quando o banco local foi criado antes da migracao."""
    cur = conn.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cur.fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def init_database():
    """Cria todas as tabelas do schema, se ainda não existirem."""
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        _ensure_column(conn, "candidatos", "origem_dados", "TEXT DEFAULT 'demo'")
        _ensure_column(conn, "candidatos", "fonte_dados", "TEXT")
        conn.execute(
            """UPDATE candidatos
               SET origem_dados = COALESCE(origem_dados, 'demo'),
                   fonte_dados = COALESCE(fonte_dados, 'Dados de demonstracao do MVP')
               WHERE origem_dados IS NULL OR fonte_dados IS NULL"""
        )
        conn.commit()
        print(f"[DB] Banco inicializado em: {DB_PATH}")
    finally:
        conn.close()


def _popular_dados_fake():
    """Insere dados fake para permitir testar o dashboard sem dados reais do TSE."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM candidatos")
    if cur.fetchone()[0] > 0:
        print("[DB] Dados de demonstração já existem, pulando seed.")
        conn.close()
        return

    candidatos_fake = [
        ("12345", "José da Silva Pereira", "Zé Pereira", "45123", "***.123.456-**",
         "Partido Exemplo", "PEX", "Vereador", "SP", 2016, "ELEITO"),
        ("12346", "José da Silva Pereira", "Zé Pereira", "45123", "***.123.456-**",
         "Partido Exemplo", "PEX", "Vereador", "SP", 2020, "ELEITO"),
        ("12347", "José da Silva Pereira", "Zé Pereira", "45123", "***.123.456-**",
         "Partido Exemplo", "PEX", "Deputado Estadual", "SP", 2022, "NÃO ELEITO"),
    ]
    cur.executemany(
        """INSERT INTO candidatos
           (id_tse, nome_civil, nome_urna, numero, cpf_mascarado, partido,
            sigla_partido, cargo, uf, ano, situacao, origem_dados, fonte_dados)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        candidatos_fake,
    )
    conn.commit()

    candidato_id = 1  # primeiro candidato inserido, usado nas votações fake

    municipios_fake = ["São Paulo", "Guarulhos", "Osasco", "Santo André", "Diadema"]
    votos_2016 = [12000, 3000, 2500, 1800, 900]
    votos_2020 = [15500, 2800, 4100, 2200, 1100]

    for muni, v16, v20 in zip(municipios_fake, votos_2016, votos_2020):
        cur.execute(
            """INSERT INTO votacao_municipio
               (candidato_id, ano, turno, uf, codigo_municipio_tse, municipio,
                cargo, partido, votos, votos_validos_municipio, percentual_votos)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (candidato_id, 2016, 1, "SP", "00001", muni, "Vereador", "PEX",
             v16, v16 * 40, round(100 / 40, 2)),
        )
        cur.execute(
            """INSERT INTO votacao_municipio
               (candidato_id, ano, turno, uf, codigo_municipio_tse, municipio,
                cargo, partido, votos, votos_validos_municipio, percentual_votos)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (candidato_id, 2020, 1, "SP", "00001", muni, "Vereador", "PEX",
             v20, v20 * 40, round(100 / 40, 2)),
        )

    emendas_fake = [
        ("Zé Pereira", "José da Silva Pereira", "Zé Pereira", "PEX", "SP", 2019,
         "São Paulo", "3550308", "Saúde", "Ministério da Saúde", "UBS Jardim Exemplo",
         500000, 480000, 450000, "Portal da Transparência", "https://exemplo.gov.br", "validado"),
        ("Zé Pereira", "José da Silva Pereira", "Zé Pereira", "PEX", "SP", 2020,
         "Guarulhos", "3518800", "Infraestrutura", "Ministério das Cidades",
         "Pavimentação Bairro Exemplo", 300000, 300000, 280000,
         "Portal da Transparência", "https://exemplo.gov.br", "validado"),
        ("Zé Pereira", "José da Silva Pereira", "Zé Pereira", "PEX", "SP", 2021,
         "Osasco", "3534401", "Educação", "Ministério da Educação",
         "Reforma Escola Municipal Exemplo", 200000, 200000, 200000,
         "Portal da Transparência", "https://exemplo.gov.br", "validado"),
    ]
    cur.executemany(
        """INSERT INTO emendas
           (parlamentar_nome, parlamentar_nome_civil, parlamentar_nome_urna, partido,
            uf, ano, municipio_beneficiado, codigo_ibge, area, orgao, entidade_beneficiada,
            valor_empenhado, valor_liquidado, valor_pago, fonte, link_fonte, status_validacao)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        emendas_fake,
    )
    conn.commit()
    conn.close()
    print("[DB] Dados de demonstração inseridos para teste do dashboard.")


if __name__ == "__main__":
    init_database()
    _popular_dados_fake()
    print(f"[DB] Concluído em {datetime.now().isoformat(timespec='seconds')}")
