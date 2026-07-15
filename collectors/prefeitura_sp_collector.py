"""
Radar Eleitoral IA - Coletor de gestão pública da Prefeitura de São Paulo.

FUNDAÇÃO da camada de auditoria municipal: a EXECUÇÃO ORÇAMENTÁRIA.
É a espinha contra a qual tudo o mais se cruza (contratos, obras, emendas).

Fonte oficial: Portal de Dados Abertos da Prefeitura de SP (CKAN),
Secretaria da Fazenda. Sem chave.
  Dataset: "Execução Orçamentária" (id: base-dados-execucao)
  Arquivos: base de dados por ano em CSV/XLSX (download direto).

Estrutura do CSV (verificada jul/2026; separador ';', encoding latin-1,
decimal ','): órgão, unidade, função, subfunção, programa, projeto/atividade,
categoria/grupo/modalidade/elemento de despesa, fonte de recurso, número da
emenda (Cd_Nro_Emenda_Dotacao) e os valores:
  Vl_Orcado_Ano, Vl_Orcado_Atualizado, Vl_EmpenhadoLiquido, Vl_Liquidado,
  Vl_Pago, Saldo_Dotacao.

PRINCÍPIO DE AUDITORIA RESPONSÁVEL: este coletor apresenta FATOS e
DISCREPÂNCIAS (ex.: baixa execução, gasto por área) sempre com a fonte
oficial. Ele não afirma irregularidade — a conclusão é do humano. Isso é o
que torna a ferramenta séria e citável.
"""

import logging
import sys
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CKAN = "https://dados.prefeitura.sp.gov.br/api/3/action"
DATASET_EXECUCAO = "base-dados-execucao"
TIMEOUT = 180
HEADERS = {"User-Agent": "Mozilla/5.0 RadarEleitoral/1.0"}

# Colunas de valor (R$) na base de execução.
COLS_VALOR = {
    "Vl_Orcado_Ano": "orcado",
    "Vl_Orcado_Atualizado": "orcado_atualizado",
    "Vl_EmpenhadoLiquido": "empenhado",
    "Vl_Liquidado": "liquidado",
    "Vl_Pago": "pago",
    "Saldo_Dotacao": "saldo",
}


def _criar_logger() -> logging.Logger:
    log = logging.getLogger("radar_eleitoral.prefeitura_sp")
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("[PMSP] %(message)s"))
        log.addHandler(h)
    log.setLevel(logging.INFO)
    log.propagate = False
    return log


logger = _criar_logger()


def _url_execucao(ano: int) -> tuple:
    """(url, formato) da execução do ano. Prefere CSV; cai para XLSX.

    Só CSV e XLSX têm o esquema MODERNO (2020+). Anos anteriores (XLS/ZIP)
    usam outro layout (colunas mensais) e não são lidos por este coletor.
    """
    r = requests.get(f"{CKAN}/package_show", params={"id": DATASET_EXECUCAO},
                     headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    recursos = r.json().get("result", {}).get("resources", [])
    alvo = str(ano)
    csv_url = xlsx_url = None
    for rec in recursos:
        nome_url = f"{rec.get('name','')} {rec.get('url','')}"
        if alvo not in nome_url:
            continue
        fmt = str(rec.get("format", "")).upper()
        if fmt == "CSV":
            csv_url = rec.get("url")
        elif fmt == "XLSX":
            xlsx_url = rec.get("url")
    if csv_url:
        return csv_url, "CSV"
    if xlsx_url:
        return xlsx_url, "XLSX"
    return None, None


def _normalizar_valores(df: pd.DataFrame, brasileiro: bool) -> pd.DataFrame:
    """Renomeia/normaliza as colunas de valor. Se o esquema moderno não estiver
    presente (ano antigo, layout diferente), devolve DataFrame vazio.

    `brasileiro=True` (CSV): valores vêm como "1.234.567,89" — remove o ponto
    de milhar e troca a vírgula decimal por ponto.
    `brasileiro=False` (XLSX): valores já usam ponto decimal — converte direto
    (tratar como brasileiro aqui inflaria os números em 100×).
    """
    if "Ds_Funcao" not in df.columns or "Vl_Pago" not in df.columns:
        return pd.DataFrame()  # esquema antigo/incompatível
    for bruto, limpo in COLS_VALOR.items():
        if bruto in df.columns:
            serie = df[bruto].astype(str).str.strip()
            if brasileiro:
                serie = serie.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
            else:
                # XLSX: só remove eventual separador de milhar com vírgula
                serie = serie.str.replace(",", "", regex=False)
            df[limpo] = pd.to_numeric(serie, errors="coerce").fillna(0.0)
    return df


def baixar_execucao(ano: int) -> pd.DataFrame:
    """Baixa e normaliza a base de execução orçamentária do ano (CSV ou XLSX)."""
    url, fmt = _url_execucao(ano)
    if not url:
        logger.info(f"Execução {ano} sem CSV/XLSX no CKAN (formato antigo?).")
        return pd.DataFrame()

    logger.info(f"Baixando execução orçamentária {ano} ({fmt})...")
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()

    if fmt == "CSV":
        texto = resp.content.decode("latin-1", errors="replace")
        df = pd.read_csv(StringIO(texto), sep=";", dtype=str, low_memory=False)
        df = _normalizar_valores(df, brasileiro=True)
    else:  # XLSX
        from io import BytesIO
        df = pd.read_excel(BytesIO(resp.content), dtype=str)
        df = _normalizar_valores(df, brasileiro=False)
    if df.empty:
        logger.info(f"Execução {ano}: esquema incompatível (ano antigo). Ignorado.")
        return df
    df["ano"] = int(ano)
    logger.info(f"{len(df)} dotações carregadas ({ano}).")
    return df


def resumo_por_funcao(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega a execução por FUNÇÃO (área: Saúde, Educação, etc.) com o % pago
    sobre o orçado atualizado — o indicador central de execução."""
    if df.empty or "Ds_Funcao" not in df.columns:
        return pd.DataFrame()
    g = df.groupby("Ds_Funcao").agg(
        orcado_atualizado=("orcado_atualizado", "sum"),
        empenhado=("empenhado", "sum"),
        liquidado=("liquidado", "sum"),
        pago=("pago", "sum"),
    ).reset_index()
    denom = g["orcado_atualizado"].where(g["orcado_atualizado"] != 0)
    g["pct_executado"] = (g["pago"] / denom * 100).round(1)
    return g.sort_values("orcado_atualizado", ascending=False).reset_index(drop=True)


def resumo_por_orgao(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega a execução por ÓRGÃO/secretaria."""
    if df.empty or "Ds_Orgao" not in df.columns:
        return pd.DataFrame()
    g = df.groupby(["Sigla_Orgao", "Ds_Orgao"]).agg(
        orcado_atualizado=("orcado_atualizado", "sum"),
        empenhado=("empenhado", "sum"),
        pago=("pago", "sum"),
    ).reset_index()
    denom = g["orcado_atualizado"].where(g["orcado_atualizado"] != 0)
    g["pct_executado"] = (g["pago"] / denom * 100).round(1)
    return g.sort_values("orcado_atualizado", ascending=False).reset_index(drop=True)


def dotacoes_por_emenda(df: pd.DataFrame) -> pd.DataFrame:
    """Dotações vinculadas a emendas parlamentares (cruzamento emenda × gasto).

    Usa a coluna Cd_Nro_Emenda_Dotacao. É a ponte entre a emenda de um
    vereador e a execução real do recurso.
    """
    col = "Cd_Nro_Emenda_Dotacao"
    if df.empty or col not in df.columns:
        return pd.DataFrame()
    com_emenda = df[df[col].astype(str).str.strip().replace("nan", "").ne("")]
    if com_emenda.empty:
        return pd.DataFrame()
    g = com_emenda.groupby([col, "Ds_Orgao", "Ds_Funcao"]).agg(
        orcado_atualizado=("orcado_atualizado", "sum"),
        empenhado=("empenhado", "sum"),
        pago=("pago", "sum"),
    ).reset_index()
    return g.sort_values("orcado_atualizado", ascending=False).reset_index(drop=True)


# ----------------------------------------------------------------------
# Gestões municipais (mandatos do prefeito) — para comparar administrações
# ----------------------------------------------------------------------

# Cada gestão é um mandato de 4 anos. Dados abertos com esquema moderno
# começam em 2020; os anos disponíveis definem quais gestões aparecem.
GESTOES = [
    ("2025–2028 · Ricardo Nunes", 2025, 2028),
    ("2021–2024 · Bruno Covas / Ricardo Nunes", 2021, 2024),
    ("2017–2020 · João Doria / Bruno Covas", 2017, 2020),
    ("2013–2016 · Fernando Haddad", 2013, 2016),
    ("2009–2012 · Gilberto Kassab", 2009, 2012),
    ("2005–2008 · José Serra / Gilberto Kassab", 2005, 2008),
]


def gestao_do_ano(ano: int) -> str:
    for nome, ini, fim in GESTOES:
        if ini <= int(ano) <= fim:
            return nome
    return f"Gestão {ano}"


def anos_da_gestao(nome_gestao: str) -> list:
    for nome, ini, fim in GESTOES:
        if nome == nome_gestao:
            return list(range(ini, fim + 1))
    return []


# ----------------------------------------------------------------------
# Leitura dos compactos gerados pelo ETL (scripts/etl_prefeitura.py)
# ----------------------------------------------------------------------

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
CACHE_FUNCAO = PROCESSED_DIR / "pmsp_execucao_funcao.csv.gz"
CACHE_ORGAO = PROCESSED_DIR / "pmsp_execucao_orgao.csv.gz"
CACHE_EMENDAS = PROCESSED_DIR / "pmsp_execucao_emendas.csv.gz"


def _ler_compacto(caminho: Path, ano: int) -> pd.DataFrame:
    if not caminho.exists():
        return pd.DataFrame()
    df = pd.read_csv(caminho)
    if "ano" in df.columns:
        df = df[pd.to_numeric(df["ano"], errors="coerce") == int(ano)]
    return df.reset_index(drop=True)


def anos_disponiveis_execucao() -> list:
    """Anos com dados no compacto de função (para o seletor do app)."""
    if not CACHE_FUNCAO.exists():
        return []
    df = pd.read_csv(CACHE_FUNCAO)
    return sorted(pd.to_numeric(df["ano"], errors="coerce").dropna().astype(int).unique().tolist(), reverse=True)


def execucao_por_funcao(ano: int) -> pd.DataFrame:
    """Execução por função no ano: usa o compacto; se ausente, baixa/agrega ao vivo."""
    cache = _ler_compacto(CACHE_FUNCAO, ano)
    if not cache.empty:
        return cache
    return resumo_por_funcao(baixar_execucao(ano))


def execucao_por_orgao(ano: int) -> pd.DataFrame:
    cache = _ler_compacto(CACHE_ORGAO, ano)
    if not cache.empty:
        return cache
    return resumo_por_orgao(baixar_execucao(ano))


def execucao_emendas(ano: int) -> pd.DataFrame:
    cache = _ler_compacto(CACHE_EMENDAS, ano)
    if not cache.empty:
        return cache
    return dotacoes_por_emenda(baixar_execucao(ano))


def gestoes_disponiveis() -> list:
    """Gestões que têm pelo menos um ano com dados processados."""
    anos = set(anos_disponiveis_execucao())
    return [nome for nome, ini, fim in GESTOES if anos & set(range(ini, fim + 1))]


def _ler_compacto_gestao(caminho: Path, nome_gestao: str) -> pd.DataFrame:
    """Lê o compacto e recorta pelos anos da gestão (sem agregar entre anos)."""
    if not caminho.exists():
        return pd.DataFrame()
    df = pd.read_csv(caminho)
    anos = anos_da_gestao(nome_gestao)
    if "ano" in df.columns and anos:
        df = df[pd.to_numeric(df["ano"], errors="coerce").isin(anos)]
    return df.reset_index(drop=True)


def execucao_funcao_gestao(nome_gestao: str) -> pd.DataFrame:
    """Execução por função somada em toda a gestão (todos os anos do mandato)."""
    df = _ler_compacto_gestao(CACHE_FUNCAO, nome_gestao)
    if df.empty or "Ds_Funcao" not in df.columns:
        return df
    g = df.groupby("Ds_Funcao").agg(
        orcado_atualizado=("orcado_atualizado", "sum"),
        empenhado=("empenhado", "sum"),
        pago=("pago", "sum"),
    ).reset_index()
    denom = g["orcado_atualizado"].where(g["orcado_atualizado"] != 0)
    g["pct_executado"] = (g["pago"] / denom * 100).round(1)
    return g.sort_values("pago", ascending=False).reset_index(drop=True)


def totais_por_ano_gestao(nome_gestao: str) -> pd.DataFrame:
    """Totais (orçado, pago) por ano dentro da gestão — para o gráfico anual."""
    df = _ler_compacto_gestao(CACHE_FUNCAO, nome_gestao)
    if df.empty:
        return df
    return df.groupby("ano").agg(
        orcado_atualizado=("orcado_atualizado", "sum"),
        pago=("pago", "sum"),
    ).reset_index()


if __name__ == "__main__":
    df = baixar_execucao(2025)
    if not df.empty:
        print("\n=== POR FUNÇÃO (top 8) ===")
        print(resumo_por_funcao(df).head(8).to_string(index=False))
        print(f"\nTotal orçado atualizado: R$ {df['orcado_atualizado'].sum():,.2f}")
        print(f"Total pago:              R$ {df['pago'].sum():,.2f}")
        emendas = dotacoes_por_emenda(df)
        print(f"\nDotações com emenda: {len(emendas)}")
