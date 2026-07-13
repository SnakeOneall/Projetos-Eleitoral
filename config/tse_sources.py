"""
Radar Eleitoral IA - Configuração de fontes de dados do TSE.

Os links oficiais dos arquivos de resultados do TSE mudam de formato e
de URL com frequência. Em vez de fixar URLs frágeis no código, este
módulo centraliza a configuração para que ela possa ser atualizada
sem alterar a lógica de coleta.

URLs verificadas individualmente em 22/06/2026, direto nas páginas de
cada dataset do Portal de Dados Abertos do TSE
(https://dadosabertos.tse.jus.br/dataset/resultados-<ano>), recurso
"Votação nominal por município e zona" — arquivo único para todas as
UFs (o filtro por UF é aplicado depois, em memória, pelo collector).
Todos os 5 anos (2016/2018/2020/2022/2024) foram confirmados um a um.

Como atualizar (se o TSE mudar o padrão de URL no futuro):
1. Acesse https://dadosabertos.tse.jus.br/dataset/resultados-<ano>
2. Localize o recurso "Votação nominal por município e zona".
3. Copie o link em "Ir para recurso" e atualize o campo `url_zip` abaixo.
"""

# Estrutura: { ano: { "uf": "SP", "url_zip": "...", "descricao": "..." } }
TSE_SOURCES = {
    2024: {
        "uf": "SP",
        "url_zip": "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2024.zip",
        "descricao": "Votação nominal por município e zona - Todas as UFs - 2024",
    },
    2022: {
        "uf": "SP",
        "url_zip": "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2022.zip",
        "descricao": "Votação nominal por município e zona - Todas as UFs - 1º e 2º turnos - 2022",
    },
    2020: {
        "uf": "SP",
        "url_zip": "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2020.zip",
        "descricao": "Votação nominal por município e zona - Todas as UFs - 2020",
    },
    2018: {
        "uf": "SP",
        "url_zip": "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2018.zip",
        "descricao": "Votação nominal por município e zona - Todas as UFs - 2018",
    },
    2016: {
        "uf": "SP",
        "url_zip": "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2016.zip",
        "descricao": "Votação nominal por município e zona - Todas as UFs - 2016",
    },
}

TSE_DATASET_TYPES = {
    "votacao_candidato_munzona": {
        "descricao": "Votação nominal por município e zona",
        "url_template": "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_{ano}.zip",
        "arquivo_local": "tse_{ano}.zip",
    },
    "votacao_secao": {
        "descricao": "Votação nominal por seção eleitoral",
        "url_template": "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_secao/votacao_secao_{ano}.zip",
        "arquivo_local": "votacao_secao_{ano}.zip",
    },
    "locais_votacao": {
        "descricao": "Locais de votação",
        "url_template": "https://cdn.tse.jus.br/estatistica/sead/odsele/local_votacao/local_votacao_{ano}.zip",
        "arquivo_local": "locais_votacao_{ano}.zip",
    },
}

# Pasta local onde os arquivos baixados/extraídos do TSE serão armazenados.
TSE_DOWNLOAD_DIR = "data/raw/tse"

# Encoding mais comum nos arquivos de resultados do TSE (varia por ano).
TSE_ENCODINGS_TENTATIVAS = ["latin-1", "utf-8", "cp1252"]

# Mapeamento de nomes de colunas oficiais do TSE -> nome interno padronizado.
# Os arquivos do TSE variam nomenclatura de colunas entre anos/arquivos
# (ex: NM_UE em vez de NM_MUNICIPIO em alguns pacotes). Múltiplas colunas
# de origem podem mapear para o mesmo nome interno; normalizar_colunas_tse()
# usa este dicionário e ignora colunas que não aparecerem nele.
COLUNAS_PADRONIZADAS = {
    "SG_UF": "uf",
    "NM_UE": "municipio",
    "NM_MUNICIPIO": "municipio",
    "CD_MUNICIPIO": "codigo_municipio_tse",
    "DS_CARGO": "cargo",
    "NM_CANDIDATO": "nome_civil",
    "NM_URNA_CANDIDATO": "nome_urna",
    "NR_CANDIDATO": "numero",
    "SG_PARTIDO": "partido",
    "NM_PARTIDO": "nome_partido",
    "QT_VOTOS_NOMINAIS": "votos",
    "QT_VOTOS_NOMINAIS_VALIDOS": "votos_validos",
    "DS_SIT_TOT_TURNO": "situacao",
    "NR_TURNO": "turno",
    "ANO_ELEICAO": "ano",
    "SQ_CANDIDATO": "id_tse",
    "NR_ZONA": "zona",
}

# Colunas-chave usadas no diagnóstico (debug_tse_dataset / logs de carregamento)
# para mostrar valores únicos relevantes, quando existirem no arquivo.
COLUNAS_CHAVE_DIAGNOSTICO = ["uf", "cargo", "partido", "nome_urna", "numero"]


def anos_disponiveis() -> list:
    """Retorna a lista de anos eleitorais configurados, do mais recente ao mais antigo."""
    return sorted(TSE_SOURCES.keys(), reverse=True)


def ultimas_n_eleicoes(n: int = 5) -> list:
    """Retorna os N anos eleitorais mais recentes configurados."""
    return anos_disponiveis()[:n]


def get_fonte(ano: int) -> dict:
    """Retorna a configuração de fonte para um ano específico, ou None."""
    return TSE_SOURCES.get(ano)


def get_fonte_dataset(tipo: str, ano: int) -> dict | None:
    """Retorna fonte configuravel para um tipo de dataset do TSE."""
    config = TSE_DATASET_TYPES.get(tipo)
    if not config:
        return None
    return {
        **config,
        "tipo": tipo,
        "ano": int(ano),
        "url_zip": config["url_template"].format(ano=int(ano)),
        "arquivo_local": config["arquivo_local"].format(ano=int(ano)),
    }
