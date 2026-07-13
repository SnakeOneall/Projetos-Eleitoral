"""Agregacoes sobre o cache tratado do TSE."""

from __future__ import annotations

import pandas as pd

from database.db_utils import buscar_candidaturas_tse


def _df_normalizado(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    normalizado = df.copy()
    if "votos" in normalizado.columns:
        normalizado["votos"] = pd.to_numeric(normalizado["votos"], errors="coerce").fillna(0)
    if "votos_validos" in normalizado.columns:
        normalizado["votos_validos"] = pd.to_numeric(normalizado["votos_validos"], errors="coerce").fillna(0)
    return normalizado


def agregar_votacao_por_municipio(df: pd.DataFrame) -> pd.DataFrame:
    """Soma votos por municipio a partir das linhas por zona."""
    df = _df_normalizado(df)
    if df.empty:
        return pd.DataFrame(columns=["ano", "uf", "municipio", "codigo_municipio_tse", "votos", "votos_validos"])

    chaves = [c for c in ["ano", "uf", "municipio", "codigo_municipio_tse"] if c in df.columns]
    colunas_agg = {"votos": "sum"}
    if "votos_validos" in df.columns:
        colunas_agg["votos_validos"] = "sum"

    return (
        df.groupby(chaves, dropna=False)
        .agg(colunas_agg)
        .reset_index()
        .sort_values("votos", ascending=False)
    )


def agregar_votacao_por_candidato(df: pd.DataFrame) -> pd.DataFrame:
    """Soma votos por candidatura TSE."""
    df = _df_normalizado(df)
    if df.empty:
        return pd.DataFrame(columns=["id_tse", "ano", "uf", "nome_urna", "votos"])

    chaves = [
        c for c in [
            "id_tse", "ano", "uf", "cargo", "nome_civil", "nome_urna",
            "numero", "partido", "nome_partido", "situacao",
        ] if c in df.columns
    ]
    colunas_agg = {"votos": "sum"}
    if "votos_validos" in df.columns:
        colunas_agg["votos_validos"] = "sum"

    return (
        df.groupby(chaves, dropna=False)
        .agg(colunas_agg)
        .reset_index()
        .sort_values("votos", ascending=False)
    )


def calcular_total_votos_candidato(id_tse: str, ano: int, uf: str) -> int:
    """Retorna o total de votos de uma candidatura no cache local."""
    registros = buscar_candidaturas_tse(id_tse=id_tse, ano=ano, uf=uf)
    if not registros:
        return 0
    df = _df_normalizado(pd.DataFrame(registros))
    return int(df["votos"].sum()) if "votos" in df.columns else 0


def listar_municipios_por_votos(id_tse: str, ano: int, uf: str) -> pd.DataFrame:
    """Lista municipios de uma candidatura ordenados por votos."""
    registros = buscar_candidaturas_tse(id_tse=id_tse, ano=ano, uf=uf)
    if not registros:
        return pd.DataFrame(columns=["municipio", "votos"])
    return agregar_votacao_por_municipio(pd.DataFrame(registros))
