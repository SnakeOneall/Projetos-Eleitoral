"""Agregacoes territoriais para mapas e rankings eleitorais."""

from __future__ import annotations

import unicodedata

import pandas as pd

from collectors.geo_collector import buscar_zonas_por_municipio
from analysis.territorial_rules import detectar_escopo_cargo


def _sem_acentos(valor: str) -> str:
    texto = str(valor or "")
    return "".join(
        char for char in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(char)
    )


def _texto_norm(valor) -> str:
    if valor is None or pd.isna(valor):
        return ""
    return _sem_acentos(str(valor)).strip().lower()


def _zona_norm(valor) -> str:
    if valor is None or pd.isna(valor):
        return ""
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    if "-" in texto:
        candidato = texto.rsplit("-", 1)[-1].strip()
        if candidato.isdigit():
            texto = candidato
    return str(int(texto)).zfill(3) if texto.isdigit() else texto


def _uf_norm(valor) -> str:
    if valor is None or pd.isna(valor):
        return ""
    return str(valor).strip().upper()[:2]


def _municipio_norm(valor) -> str:
    if valor is None or pd.isna(valor):
        return ""
    return str(valor).strip()


def _coluna_votos(df: pd.DataFrame) -> str | None:
    for coluna in ("votos", "votos_totais", "qt_votos"):
        if coluna in df.columns:
            return coluna
    return None


def _com_percentual(df: pd.DataFrame) -> pd.DataFrame:
    total = float(df["votos"].sum() or 0)
    df["percentual"] = (df["votos"] / total * 100).round(2) if total else 0.0
    return df.sort_values("votos", ascending=False).reset_index(drop=True)


def _tem_coluna_util(df: pd.DataFrame, coluna: str) -> bool:
    return coluna in df.columns and df[coluna].notna().any() and df[coluna].astype(str).str.strip().ne("").any()


def _base_votos(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    base = df.copy()
    coluna_votos = _coluna_votos(base)
    if not coluna_votos:
        base["votos"] = 0
    elif coluna_votos != "votos":
        base["votos"] = base[coluna_votos]
    base["votos"] = pd.to_numeric(base["votos"], errors="coerce").fillna(0)
    for coluna in [
        "uf", "municipio", "zona", "secao", "local_votacao", "bairro",
        "regiao_administrativa", "latitude", "longitude",
    ]:
        if coluna not in base.columns:
            base[coluna] = None
    base["uf"] = base["uf"].map(_uf_norm)
    base["municipio"] = base["municipio"].map(_municipio_norm)
    base["zona"] = base["zona"].map(_zona_norm)
    base["secao"] = base["secao"].map(_zona_norm)
    return base


def _agrupar_generico(df: pd.DataFrame | None, nivel: str, group_cols: list[str], chave_col: str) -> pd.DataFrame:
    base = _base_votos(df)
    colunas_saida = [
        "nivel", "chave_territorial", "municipio", "zona", "secao",
        "local_votacao", "bairro", "votos", "percentual", "ranking",
    ]
    if base.empty or any(not _tem_coluna_util(base, col) for col in group_cols):
        return pd.DataFrame(columns=colunas_saida)

    agg_spec = {"votos": ("votos", "sum")}
    for coluna in ["municipio", "zona", "secao", "local_votacao", "bairro"]:
        if coluna not in group_cols:
            agg_spec[coluna] = (coluna, "first")
    if "latitude" in base.columns:
        agg_spec["latitude"] = ("latitude", "first")
    if "longitude" in base.columns:
        agg_spec["longitude"] = ("longitude", "first")

    agrupado = base.groupby(group_cols, dropna=False).agg(**agg_spec).reset_index()
    agrupado = agrupado[agrupado[chave_col].notna() & agrupado[chave_col].astype(str).str.strip().ne("")]
    if agrupado.empty:
        return pd.DataFrame(columns=colunas_saida)
    agrupado["nivel"] = nivel
    agrupado["chave_territorial"] = agrupado[chave_col].astype(str)
    agrupado = _com_percentual(agrupado)
    agrupado["ranking"] = range(1, len(agrupado) + 1)
    for coluna in colunas_saida:
        if coluna not in agrupado.columns:
            agrupado[coluna] = None
    extras = [c for c in ["uf", "latitude", "longitude", "regiao_administrativa"] if c in agrupado.columns]
    return agrupado[colunas_saida + extras]


def agrupar_por_zona(df: pd.DataFrame | None) -> pd.DataFrame:
    return _agrupar_generico(df, "zona", ["uf", "municipio", "zona"], "zona")


def agrupar_por_secao(df: pd.DataFrame | None) -> pd.DataFrame:
    return _agrupar_generico(df, "secao", ["uf", "municipio", "zona", "secao"], "secao")


def agrupar_por_local_votacao(df: pd.DataFrame | None) -> pd.DataFrame:
    return _agrupar_generico(df, "local_votacao", ["uf", "municipio", "zona", "local_votacao"], "local_votacao")


def agrupar_por_bairro(df: pd.DataFrame | None) -> pd.DataFrame:
    return _agrupar_generico(df, "bairro", ["uf", "municipio", "bairro"], "bairro")


def agrupar_por_municipio(df: pd.DataFrame | None) -> pd.DataFrame:
    return _agrupar_generico(df, "municipio", ["uf", "municipio"], "municipio")


def agrupar_por_regiao_administrativa(df: pd.DataFrame | None) -> pd.DataFrame:
    return _agrupar_generico(
        df,
        "regiao_administrativa",
        ["uf", "regiao_administrativa"],
        "regiao_administrativa",
    )


def _mensagem_por_nivel(nivel: str, escopo: str) -> str:
    if escopo == "municipal":
        mensagens = {
            "bairro": "Dados territorializados por bairro encontrados.",
            "local_votacao": "Dados detalhados por local de votação encontrados.",
            "secao": "Dados detalhados por seção eleitoral encontrados.",
            "zona": "Dados detalhados por zona eleitoral encontrados.",
            "municipio": (
                "Este é um cargo municipal. Para análise útil, é necessário detalhar por zona, "
                "seção, local de votação ou bairro. No momento, o banco possui apenas dados "
                "consolidados por município para esta consulta."
            ),
        }
        return mensagens.get(nivel, mensagens["municipio"])
    if escopo == "distrital":
        return (
            "Cargo distrital: análise por região administrativa encontrada."
            if nivel == "regiao_administrativa"
            else "Cargo distrital: exibindo melhor granularidade territorial disponível."
        )
    return (
        "Cargo estadual/federal: análise por município encontrada."
        if nivel == "municipio"
        else "Cargo estadual/federal: análise por zona eleitoral encontrada."
    )


def analisar_distribuicao_territorial(
    df: pd.DataFrame | None,
    cargo: str,
    municipio: str | None = None,
    uf: str | None = None,
) -> dict:
    """Escolhe a melhor granularidade disponivel conforme o cargo."""
    regra = detectar_escopo_cargo(cargo)
    base = _base_votos(df)
    if base.empty:
        return {
            "regra": regra,
            "nivel": "vazio",
            "granularidade": "vazio",
            "dados": pd.DataFrame(),
            "total_votos": 0,
            "mensagem": "Nenhum dado territorial encontrado para este recorte.",
            "aviso_importacao": "",
            "titulo": "Distribuição territorial de votos",
            "subtitulo": "sem dados territoriais",
        }

    escopo = regra["nivel_principal"]
    if escopo == "municipal":
        candidatos = [
            ("bairro", agrupar_por_bairro),
            ("local_votacao", agrupar_por_local_votacao),
            ("secao", agrupar_por_secao),
            ("zona", agrupar_por_zona),
            ("municipio", agrupar_por_municipio),
        ]
    elif escopo == "distrital":
        candidatos = [
            ("regiao_administrativa", agrupar_por_regiao_administrativa),
            ("zona", agrupar_por_zona),
            ("municipio", agrupar_por_municipio),
        ]
    else:
        candidatos = [
            ("municipio", agrupar_por_municipio),
            ("zona", agrupar_por_zona),
        ]

    nivel_escolhido = "municipio"
    dados = pd.DataFrame()
    for nivel, func in candidatos:
        tentativa = func(base)
        if not tentativa.empty and not (nivel == "municipio" and escopo == "municipal" and len(tentativa) == 1 and _tem_coluna_util(base, "zona")):
            nivel_escolhido = nivel
            dados = tentativa
            break

    if dados.empty:
        dados = agrupar_por_municipio(base)
        nivel_escolhido = "municipio" if not dados.empty else "vazio"

    total = int(dados["votos"].sum()) if not dados.empty and "votos" in dados.columns else 0
    municipio_ref = municipio or (
        base["municipio"].dropna().iloc[0]
        if "municipio" in base.columns and base["municipio"].notna().any()
        else None
    )
    titulo = (
        f"Distribuição de votos em {municipio_ref}"
        if escopo == "municipal" and municipio_ref
        else "Distribuição territorial de votos"
    )
    subtitulos = {
        "bairro": "por bairro",
        "local_votacao": "por local de votação",
        "secao": "por seção eleitoral",
        "zona": "por zona eleitoral",
        "municipio": "por município",
        "regiao_administrativa": "por região administrativa",
        "vazio": "sem dados territoriais",
    }
    aviso_importacao = ""
    if escopo == "municipal" and nivel_escolhido == "zona":
        aviso_importacao = (
            "Dados disponíveis por zona eleitoral. Para bairro, seção ou local de votação, "
            "importe a base de votação por seção/local de votação."
        )
    elif escopo == "municipal" and nivel_escolhido == "municipio":
        aviso_importacao = _mensagem_por_nivel("municipio", escopo)

    return {
        "regra": regra,
        "nivel": nivel_escolhido,
        "granularidade": nivel_escolhido,
        "dados": dados,
        "total_votos": total,
        "mensagem": _mensagem_por_nivel(nivel_escolhido, escopo),
        "aviso_importacao": aviso_importacao,
        "titulo": titulo,
        "subtitulo": subtitulos.get(nivel_escolhido, "territorial"),
    }


def agregar_votos_por_zona(df_votacao: pd.DataFrame | None) -> pd.DataFrame:
    """Agrupa votos por UF, municipio e zona eleitoral."""
    colunas = ["uf", "municipio", "zona", "votos", "percentual"]
    if df_votacao is None or df_votacao.empty or "zona" not in df_votacao.columns:
        return pd.DataFrame(columns=colunas)

    base = df_votacao.copy()
    coluna_votos = _coluna_votos(base)
    if not coluna_votos:
        base["votos"] = 0
    elif coluna_votos != "votos":
        base["votos"] = base[coluna_votos]

    if "uf" not in base.columns:
        base["uf"] = ""
    if "municipio" not in base.columns:
        base["municipio"] = ""

    base["uf"] = base["uf"].map(_uf_norm)
    base["municipio"] = base["municipio"].map(_municipio_norm)
    base["zona"] = base["zona"].map(_zona_norm)
    base["votos"] = pd.to_numeric(base["votos"], errors="coerce").fillna(0)
    base = base[base["zona"].astype(str).str.strip().ne("")]
    if base.empty:
        return pd.DataFrame(columns=colunas)

    agrupado = (
        base.groupby(["uf", "municipio", "zona"], dropna=False)
        .agg(votos=("votos", "sum"))
        .reset_index()
    )
    return _com_percentual(agrupado)


def agregar_votos_por_municipio(df_votacao: pd.DataFrame | None) -> pd.DataFrame:
    """Agrupa votos por municipio."""
    colunas = ["uf", "municipio", "votos", "percentual"]
    if df_votacao is None or df_votacao.empty or "municipio" not in df_votacao.columns:
        return pd.DataFrame(columns=colunas)

    base = df_votacao.copy()
    coluna_votos = _coluna_votos(base)
    if not coluna_votos:
        base["votos"] = 0
    elif coluna_votos != "votos":
        base["votos"] = base[coluna_votos]

    if "uf" not in base.columns:
        base["uf"] = ""
    base["uf"] = base["uf"].map(_uf_norm)
    base["municipio"] = base["municipio"].map(_municipio_norm)
    base["votos"] = pd.to_numeric(base["votos"], errors="coerce").fillna(0)
    base = base[base["municipio"].astype(str).str.strip().ne("")]
    if base.empty:
        return pd.DataFrame(columns=colunas)

    agrupado = (
        base.groupby(["uf", "municipio"], dropna=False)
        .agg(votos=("votos", "sum"))
        .reset_index()
    )
    return _com_percentual(agrupado)


def cruzar_votos_com_zonas(df_votos: pd.DataFrame | None, df_zonas: pd.DataFrame | None) -> pd.DataFrame:
    """Cruza votos agregados com zonas cadastradas, preservando ranking sem coordenadas."""
    votos = agregar_votos_por_zona(df_votos)
    if votos.empty:
        return votos.assign(latitude=pd.Series(dtype="float"), longitude=pd.Series(dtype="float"))

    if df_zonas is None or df_zonas.empty:
        votos["latitude"] = None
        votos["longitude"] = None
        votos["nome_zona"] = None
        votos["endereco"] = None
        votos["bairro"] = None
        votos["fonte"] = None
        votos["tem_coordenadas"] = False
        return votos

    zonas = df_zonas.copy()
    for coluna in ("uf", "municipio", "zona", "nome_zona", "endereco", "bairro", "latitude", "longitude", "fonte"):
        if coluna not in zonas.columns:
            zonas[coluna] = None
    zonas["uf"] = zonas["uf"].map(_uf_norm)
    zonas["municipio"] = zonas["municipio"].map(_municipio_norm)
    zonas["zona"] = zonas["zona"].map(_zona_norm)
    zonas["latitude"] = pd.to_numeric(zonas["latitude"], errors="coerce")
    zonas["longitude"] = pd.to_numeric(zonas["longitude"], errors="coerce")
    zonas = zonas.drop_duplicates(subset=["uf", "municipio", "zona"], keep="first")

    votos_merge = votos.copy()
    votos_merge["_uf_key"] = votos_merge["uf"].map(_uf_norm)
    votos_merge["_municipio_key"] = votos_merge["municipio"].map(_texto_norm)
    votos_merge["_zona_key"] = votos_merge["zona"].map(_zona_norm)

    zonas_merge = zonas.copy()
    zonas_merge["_uf_key"] = zonas_merge["uf"].map(_uf_norm)
    zonas_merge["_municipio_key"] = zonas_merge["municipio"].map(_texto_norm)
    zonas_merge["_zona_key"] = zonas_merge["zona"].map(_zona_norm)
    zonas_merge = zonas_merge.drop_duplicates(subset=["_uf_key", "_municipio_key", "_zona_key"], keep="first")

    cruzado = votos_merge.merge(
        zonas_merge[[
            "_uf_key", "_municipio_key", "_zona_key",
            "nome_zona", "endereco", "bairro", "latitude", "longitude", "fonte",
        ]],
        on=["_uf_key", "_municipio_key", "_zona_key"],
        how="left",
    )
    cruzado = cruzado.drop(columns=["_uf_key", "_municipio_key", "_zona_key"])
    cruzado["tem_coordenadas"] = cruzado[["latitude", "longitude"]].notna().all(axis=1)
    return cruzado.sort_values("votos", ascending=False).reset_index(drop=True)


def preparar_mapa_vereador_sp(df_votos: pd.DataFrame | None) -> dict:
    """Prepara dados de mapa/ranking para vereador em Sao Paulo por zona eleitoral."""
    votos = agregar_votos_por_zona(df_votos)
    if votos.empty:
        return {
            "tipo": "ranking",
            "tem_mapa": False,
            "dados": votos,
            "mensagem": "Nenhum dado por zona eleitoral encontrado para este recorte.",
        }

    municipios = votos["municipio"].dropna().astype(str)
    eh_sp = votos["uf"].astype(str).str.upper().eq("SP").any()
    tem_sao_paulo = municipios.map(_texto_norm).eq("sao paulo").any()
    if not (eh_sp and tem_sao_paulo):
        return {
            "tipo": "ranking",
            "tem_mapa": False,
            "dados": votos,
            "mensagem": "Recorte nao identificado como Vereador em Sao Paulo; exibindo ranking por zona.",
        }

    if df_votos is not None and not df_votos.empty and {"latitude", "longitude"}.issubset(df_votos.columns):
        dados_com_coords = cruzar_votos_com_zonas(votos, df_votos)
        if not dados_com_coords.empty and dados_com_coords["tem_coordenadas"].any():
            return {
                "tipo": "mapa",
                "tem_mapa": True,
                "dados": dados_com_coords,
                "mensagem": "Votos por zona cruzados com coordenadas presentes no recorte.",
            }

    zonas = pd.DataFrame(buscar_zonas_por_municipio("SP", "Sao Paulo"))
    if zonas.empty:
        zonas = pd.DataFrame(buscar_zonas_por_municipio("SP", "São Paulo"))
    dados = cruzar_votos_com_zonas(votos, zonas)
    tem_mapa = bool(not dados.empty and dados["tem_coordenadas"].any())
    return {
        "tipo": "mapa" if tem_mapa else "ranking",
        "tem_mapa": tem_mapa,
        "dados": dados,
        "mensagem": (
            "Zonas eleitorais cruzadas com coordenadas cadastradas."
            if tem_mapa
            else "Mapa geografico ainda nao disponivel para esta base; exibindo ranking por zona eleitoral."
        ),
    }
