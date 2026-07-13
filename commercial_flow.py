"""Helpers do fluxo comercial guiado do MVP.

Mantem regras pequenas e testaveis fora do Streamlit: status do funil,
auditoria da coleta e filtros locais de emendas ja normalizadas/importadas.
"""

from datetime import datetime
import unicodedata

import pandas as pd


def normalizar_texto(valor) -> str:
    texto = str(valor or "").strip().lower()
    texto = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return texto


def criar_status_fluxo(
    tse_registros: int = 0,
    candidato=None,
    emendas_count: int = 0,
    analise_count: int = 0,
    plano=None,
    pdf_path: str | None = None,
) -> dict:
    """Retorna os indicadores principais do fluxo comercial."""
    return {
        "tse_carregado": int(tse_registros or 0) > 0,
        "candidato_salvo": bool(candidato),
        "emendas_carregadas": int(emendas_count or 0) > 0,
        "analise_calculada": int(analise_count or 0) > 0,
        "plano_gerado": bool(plano),
        "pdf_gerado": bool(pdf_path),
    }


def montar_auditoria_dados(
    candidato=None,
    tse_registros: int = 0,
    emendas_count: int = 0,
    filtros: dict | None = None,
    origem_emendas: str = "CSV/API",
    pdf_path: str | None = None,
) -> dict:
    """Monta uma linha de auditoria para exibicao na UI."""
    candidato = candidato or {}
    return {
        "origem_dados_eleitorais": candidato.get("origem_dados") or "nao_selecionado",
        "fonte_dados_eleitorais": candidato.get("fonte_dados") or "",
        "quantidade_registros_tse": int(tse_registros or 0),
        "quantidade_emendas": int(emendas_count or 0),
        "origem_emendas": origem_emendas,
        "pdf_gerado": "sim" if pdf_path else "nao",
        "data_hora_coleta": datetime.now().isoformat(timespec="seconds"),
        "filtros_usados": filtros or {},
    }


def filtrar_emendas_localidade(
    emendas,
    ano: int | None = None,
    codigo_ibge: str | None = None,
    municipio: str | None = None,
    uf: str | None = None,
    autor: str | None = None,
    niveis: list[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Filtra emendas normalizadas por escopo territorial e autor.

    niveis aceita municipal, estadual, nacional e multiplo. O nivel atua como
    classificacao de escopo; os filtros concretos informados sempre sao
    aplicados para permitir combinacoes praticas na UI.
    """
    df = pd.DataFrame(emendas).copy()
    if df.empty:
        return df

    for coluna in [
        "ano", "codigo_ibge", "municipio_beneficiado", "uf", "parlamentar_nome",
        "parlamentar_nome_civil", "parlamentar_nome_urna",
    ]:
        if coluna not in df.columns:
            df[coluna] = ""

    niveis_norm = {normalizar_texto(n) for n in (niveis or ["multiplo"])}

    if ano:
        df = df[pd.to_numeric(df["ano"], errors="coerce") == int(ano)]
    if codigo_ibge:
        df = df[df["codigo_ibge"].astype(str).str.strip() == str(codigo_ibge).strip()]
    if municipio:
        alvo = normalizar_texto(municipio)
        df = df[df["municipio_beneficiado"].map(normalizar_texto).str.contains(alvo, na=False)]
    if uf:
        df = df[df["uf"].astype(str).str.upper().str.strip() == str(uf).upper().strip()]
    if autor:
        alvo = normalizar_texto(autor)
        nomes = (
            df["parlamentar_nome"].map(normalizar_texto) + " "
            + df["parlamentar_nome_civil"].map(normalizar_texto) + " "
            + df["parlamentar_nome_urna"].map(normalizar_texto)
        )
        df = df[nomes.str.contains(alvo, na=False)]

    if "multiplo" not in niveis_norm:
        masks = []
        if "municipal" in niveis_norm:
            masks.append(df["municipio_beneficiado"].astype(str).str.strip().ne("") | df["codigo_ibge"].astype(str).str.strip().ne(""))
        if "estadual" in niveis_norm:
            masks.append(df["uf"].astype(str).str.strip().ne("") & df["municipio_beneficiado"].astype(str).str.strip().eq(""))
        if "nacional" in niveis_norm:
            masks.append(df["uf"].astype(str).str.strip().eq("") & df["municipio_beneficiado"].astype(str).str.strip().eq(""))
        if masks:
            mask_final = masks[0]
            for mask in masks[1:]:
                mask_final = mask_final | mask
            df = df[mask_final]

    return df.reset_index(drop=True)
