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


def _url_csv_execucao(ano: int) -> str | None:
    """URL de download do CSV da execução orçamentária do ano (via CKAN)."""
    r = requests.get(f"{CKAN}/package_show", params={"id": DATASET_EXECUCAO},
                     headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    recursos = r.json().get("result", {}).get("resources", [])
    for rec in recursos:
        if str(rec.get("format", "")).upper() == "CSV" and str(ano) in str(rec.get("name", "")):
            return rec.get("url")
    return None


def baixar_execucao(ano: int) -> pd.DataFrame:
    """Baixa e normaliza a base de execução orçamentária do ano.

    Retorna DataFrame com as colunas descritivas + valores numéricos
    normalizados (colunas renomeadas para orcado, empenhado, liquidado, pago...).
    """
    url = _url_csv_execucao(ano)
    if not url:
        logger.info(f"CSV de execução {ano} não encontrado no CKAN.")
        return pd.DataFrame()

    logger.info(f"Baixando execução orçamentária {ano}...")
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    texto = resp.content.decode("latin-1", errors="replace")

    df = pd.read_csv(StringIO(texto), sep=";", dtype=str, low_memory=False)
    for bruto, limpo in COLS_VALOR.items():
        if bruto in df.columns:
            df[limpo] = (
                df[bruto].astype(str)
                .str.replace(".", "", regex=False)
                .str.replace(",", ".", regex=False)
            )
            df[limpo] = pd.to_numeric(df[limpo], errors="coerce").fillna(0.0)
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


if __name__ == "__main__":
    df = baixar_execucao(2025)
    if not df.empty:
        print("\n=== POR FUNÇÃO (top 8) ===")
        print(resumo_por_funcao(df).head(8).to_string(index=False))
        print(f"\nTotal orçado atualizado: R$ {df['orcado_atualizado'].sum():,.2f}")
        print(f"Total pago:              R$ {df['pago'].sum():,.2f}")
        emendas = dotacoes_por_emenda(df)
        print(f"\nDotações com emenda: {len(emendas)}")
