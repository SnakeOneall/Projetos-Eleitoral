"""Coleta e normalizacao de bases geograficas eleitorais."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

from config.geo_sources import GEO_SOURCES
from database.init_db import get_connection


GEO_RAW_DIR = Path("data") / "raw" / "geo"
ZONAS_CSV_PATH = GEO_RAW_DIR / "zonas-eleitorais.csv"
FONTE_ZONAS = GEO_SOURCES["zonas_eleitorais_csv"]


def _log(mensagem: str) -> None:
    print(f"[GEO] {mensagem}")


def _sem_acentos(valor: str) -> str:
    texto = str(valor or "")
    return "".join(
        char for char in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(char)
    )


def _normalizar_coluna(coluna: str) -> str:
    texto = _sem_acentos(coluna).strip().lower()
    texto = re.sub(r"[^a-z0-9]+", "_", texto)
    return texto.strip("_")


def _normalizar_texto(valor) -> str | None:
    if valor is None or pd.isna(valor):
        return None
    texto = str(valor).strip()
    return texto or None


def _normalizar_zona(valor) -> str | None:
    texto = _normalizar_texto(valor)
    if not texto:
        return None
    if texto.endswith(".0"):
        texto = texto[:-2]
    if "-" in texto:
        candidato = texto.rsplit("-", 1)[-1].strip()
        if candidato.isdigit():
            texto = candidato
    texto = texto.strip()
    return str(int(texto)).zfill(3) if texto.isdigit() else texto


def _normalizar_municipio(valor) -> str | None:
    texto = _normalizar_texto(valor)
    if not texto:
        return None
    return " ".join(parte.capitalize() for parte in texto.split())


def _texto_comparavel(valor) -> str:
    texto = _sem_acentos(str(valor or "")).lower()
    return re.sub(r"\s+", " ", texto).strip()


def _normalizar_uf(valor) -> str | None:
    texto = _normalizar_texto(valor)
    return texto.upper()[:2] if texto else None


def _coluna_existente(colunas: Iterable[str], candidatos: list[str]) -> str | None:
    disponiveis = list(colunas)
    for candidato in candidatos:
        normalizado = _normalizar_coluna(candidato)
        if normalizado in disponiveis:
            return normalizado
    for coluna in disponiveis:
        if any(candidato in coluna for candidato in candidatos):
            return coluna
    return None


def _serie_ou_vazio(df: pd.DataFrame, coluna: str | None) -> pd.Series:
    if coluna and coluna in df.columns:
        return df[coluna]
    return pd.Series([None] * len(df), index=df.index)


def _normalizar_numero(valor) -> float | None:
    if valor is None or pd.isna(valor):
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    texto = texto.replace(" ", "")
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(",", ".")
    try:
        numero = float(texto)
    except ValueError:
        return None
    return numero


def registrar_importacao_geo(
    tipo: str,
    fonte: str,
    arquivo_local: str | None,
    status: str,
    quantidade_linhas: int = 0,
    mensagem: str = "",
) -> int:
    """Registra importacao geografica para auditoria local."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO geo_importacoes
           (tipo, fonte, arquivo_local, status, quantidade_linhas, mensagem, data_importacao)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            tipo,
            fonte,
            arquivo_local,
            status,
            int(quantidade_linhas or 0),
            mensagem,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
    novo_id = cur.lastrowid
    conn.close()
    return novo_id


def baixar_zonas_eleitorais_csv(force: bool = False) -> Path:
    """Baixa o CSV raw do Mapas Livres ou reutiliza o arquivo local."""
    GEO_RAW_DIR.mkdir(parents=True, exist_ok=True)

    if ZONAS_CSV_PATH.exists() and not force:
        _log(f"Usando CSV local: {ZONAS_CSV_PATH}")
        return ZONAS_CSV_PATH

    _log(f"Baixando zonas eleitorais de {FONTE_ZONAS}")
    try:
        resposta = requests.get(FONTE_ZONAS, timeout=60)
        resposta.raise_for_status()
        ZONAS_CSV_PATH.write_bytes(resposta.content)
        _log(f"CSV salvo em {ZONAS_CSV_PATH}")
        return ZONAS_CSV_PATH
    except Exception as exc:
        if ZONAS_CSV_PATH.exists():
            _log(f"Falha no download ({exc}); usando CSV local existente.")
            return ZONAS_CSV_PATH
        registrar_importacao_geo(
            "zonas_eleitorais",
            FONTE_ZONAS,
            str(ZONAS_CSV_PATH),
            "erro",
            0,
            str(exc),
        )
        raise


def carregar_zonas_eleitorais_csv(caminho: str | Path | None = None) -> pd.DataFrame:
    """Le CSV de zonas eleitorais com deteccao simples de encoding/separador."""
    caminho_csv = Path(caminho) if caminho else baixar_zonas_eleitorais_csv()
    erros = []
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(caminho_csv, sep=None, engine="python", encoding=encoding)
            df.columns = [_normalizar_coluna(coluna) for coluna in df.columns]
            df.attrs["arquivo_local"] = str(caminho_csv)
            df.attrs["encoding"] = encoding
            _log(f"CSV carregado com {len(df)} linha(s), encoding={encoding}")
            return df
        except Exception as exc:
            erros.append(f"{encoding}: {exc}")
    raise ValueError("Nao foi possivel ler CSV de zonas eleitorais: " + " | ".join(erros))


def normalizar_zonas_eleitorais(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza a base externa para o contrato interno da camada geografica."""
    if df is None or df.empty:
        return pd.DataFrame(columns=[
            "uf", "municipio", "zona", "nome_zona", "endereco", "bairro",
            "latitude", "longitude", "fonte",
        ])

    base = df.copy()
    base.columns = [_normalizar_coluna(coluna) for coluna in base.columns]

    col_uf = _coluna_existente(base.columns, ["uf", "estado", "sg_uf", "sigla_uf"])
    col_municipio = _coluna_existente(base.columns, [
        "municipio", "cidade", "nome_municipio", "nm_municipio", "mun",
    ])
    col_zona = _coluna_existente(base.columns, [
        "zona", "nr_zona", "numero_zona", "zona_eleitoral", "ze", "id",
    ])
    col_nome = _coluna_existente(base.columns, [
        "nome_zona", "cartorio", "zona_nome", "local", "nome",
    ])
    col_endereco = _coluna_existente(base.columns, [
        "endereco", "endereco_tse", "logradouro", "address", "endereco_completo",
    ])
    col_bairro = _coluna_existente(base.columns, ["bairro", "district"])
    col_latitude = _coluna_existente(base.columns, ["latitude", "lat", "y"])
    col_longitude = _coluna_existente(base.columns, ["longitude", "lon", "lng", "long", "x"])

    normalizado = pd.DataFrame(index=base.index)
    normalizado["uf"] = _serie_ou_vazio(base, col_uf).map(_normalizar_uf)
    normalizado["municipio"] = _serie_ou_vazio(base, col_municipio).map(_normalizar_municipio)
    normalizado["zona"] = _serie_ou_vazio(base, col_zona).map(_normalizar_zona)
    normalizado["nome_zona"] = _serie_ou_vazio(base, col_nome).map(_normalizar_texto)
    normalizado["endereco"] = _serie_ou_vazio(base, col_endereco).map(_normalizar_texto)
    normalizado["bairro"] = _serie_ou_vazio(base, col_bairro).map(_normalizar_texto)
    normalizado["latitude"] = _serie_ou_vazio(base, col_latitude).map(_normalizar_numero)
    normalizado["longitude"] = _serie_ou_vazio(base, col_longitude).map(_normalizar_numero)
    normalizado["fonte"] = FONTE_ZONAS

    normalizado = normalizado[
        normalizado["uf"].notna()
        & normalizado["municipio"].notna()
        & normalizado["zona"].notna()
    ].copy()
    normalizado = normalizado.drop_duplicates(subset=["uf", "municipio", "zona"], keep="first")
    normalizado = normalizado.reset_index(drop=True)
    normalizado.attrs["colunas_origem"] = list(base.columns)
    return normalizado


def salvar_zonas_eleitorais_no_banco(df: pd.DataFrame) -> int:
    """Salva zonas no SQLite, atualizando duplicatas por uf+municipio+zona."""
    if df is None or df.empty:
        registrar_importacao_geo(
            "zonas_eleitorais",
            FONTE_ZONAS,
            df.attrs.get("arquivo_local") if hasattr(df, "attrs") else None,
            "sem_dados",
            0,
            "DataFrame vazio",
        )
        return 0

    base = normalizar_zonas_eleitorais(df)
    if base.empty:
        registrar_importacao_geo(
            "zonas_eleitorais",
            FONTE_ZONAS,
            df.attrs.get("arquivo_local"),
            "sem_dados",
            0,
            "Nenhuma linha com uf, municipio e zona",
        )
        return 0

    conn = get_connection()
    cur = conn.cursor()
    salvas = 0
    try:
        for _, linha in base.iterrows():
            valores = (
                linha.get("uf"),
                linha.get("municipio"),
                linha.get("zona"),
                linha.get("nome_zona"),
                linha.get("endereco"),
                linha.get("bairro"),
                linha.get("latitude"),
                linha.get("longitude"),
                linha.get("fonte"),
            )
            cur.execute(
                """SELECT id FROM geo_zonas_eleitorais
                   WHERE UPPER(uf) = ? AND municipio = ? AND zona = ?
                   LIMIT 1""",
                (linha.get("uf"), linha.get("municipio"), linha.get("zona")),
            )
            existente = cur.fetchone()
            if existente:
                cur.execute(
                    """UPDATE geo_zonas_eleitorais
                       SET nome_zona = ?, endereco = ?, bairro = ?,
                           latitude = ?, longitude = ?, fonte = ?
                       WHERE id = ?""",
                    valores[3:] + (existente["id"],),
                )
            else:
                cur.execute(
                    """INSERT INTO geo_zonas_eleitorais
                       (uf, municipio, zona, nome_zona, endereco, bairro, latitude, longitude, fonte)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    valores,
                )
            salvas += 1
        conn.commit()
    finally:
        conn.close()

    registrar_importacao_geo(
        "zonas_eleitorais",
        FONTE_ZONAS,
        df.attrs.get("arquivo_local"),
        "importado",
        salvas,
        "Zonas eleitorais salvas/atualizadas",
    )
    _log(f"{salvas} zona(s) salva(s)/atualizada(s) no banco.")
    return salvas


def buscar_zonas_por_municipio(uf: str, municipio: str) -> list[dict]:
    """Retorna zonas eleitorais cadastradas para UF/municipio."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT *
           FROM geo_zonas_eleitorais
           WHERE UPPER(uf) = ?
           ORDER BY CAST(zona AS INTEGER), zona""",
        (str(uf or "").upper().strip(),),
    )
    rows = cur.fetchall()
    conn.close()
    registros = [dict(row) for row in rows]
    municipio_ref = _texto_comparavel(municipio)
    if not municipio_ref:
        return registros
    return [
        row for row in registros
        if municipio_ref in _texto_comparavel(row.get("municipio"))
        or _texto_comparavel(row.get("municipio")) in municipio_ref
    ]


def buscar_zona(uf: str, municipio: str, zona: str) -> dict | None:
    """Busca uma zona especifica por UF, municipio e numero da zona."""
    zona_normalizada = _normalizar_zona(zona)
    for row in buscar_zonas_por_municipio(uf, municipio):
        if row.get("zona") == zona_normalizada:
            return row
    return None
