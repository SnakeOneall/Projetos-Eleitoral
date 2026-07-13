"""Importa votacao por secao eleitoral para analise territorial granular.

Uso:
    python scripts/import_tse_sections.py --uf SP --ano 2024 --municipio "Sao Paulo"
    python scripts/import_tse_sections.py --uf SP --ano 2024 --municipio "Sao Paulo" --arquivo C:\\dados\\votacao_secao_2024_SP.csv
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectors.tse_collector import detectar_separador_encoding  # noqa: E402
from config.tse_sources import TSE_DOWNLOAD_DIR, get_fonte_dataset  # noqa: E402
from database.init_db import get_connection, init_database  # noqa: E402


TIPO_DATASET = "votacao_secao"
COLUNAS_SAIDA = [
    "ano", "turno", "uf", "municipio", "codigo_municipio_tse", "zona", "secao",
    "local_votacao", "endereco_local", "bairro", "cargo", "id_tse", "nome_civil",
    "nome_urna", "numero", "partido", "votos", "votos_validos", "origem_arquivo",
]


def _sem_acentos(valor: str) -> str:
    texto = str(valor or "")
    return "".join(
        char for char in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(char)
    )


def _texto_key(valor: str) -> str:
    return re.sub(r"\s+", " ", _sem_acentos(valor).lower()).strip()


def _normalizar_coluna(coluna: str) -> str:
    texto = _sem_acentos(coluna).strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", texto).strip("_")


def _coluna(df: pd.DataFrame, candidatos: list[str]) -> str | None:
    normalizados = [_normalizar_coluna(c) for c in candidatos]
    for candidato in normalizados:
        if candidato in df.columns:
            return candidato
    return None


def _serie(df: pd.DataFrame, coluna: str | None) -> pd.Series:
    if coluna and coluna in df.columns:
        return df[coluna]
    return pd.Series([None] * len(df), index=df.index)


def _texto(valor) -> str | None:
    if valor is None or pd.isna(valor):
        return None
    texto = str(valor).strip()
    return texto or None


def _zona_secao(valor) -> str | None:
    texto = _texto(valor)
    if not texto:
        return None
    if texto.endswith(".0"):
        texto = texto[:-2]
    return str(int(texto)).zfill(3) if texto.isdigit() else texto


def _safe_int(valor, default: int | None = None) -> int | None:
    if valor is None or pd.isna(valor) or valor == "":
        return default
    try:
        return int(float(str(valor).replace(",", ".")))
    except (TypeError, ValueError):
        return default


def _registrar_importacao(ano: int, uf: str, municipio: str | None, status: str, quantidade: int, mensagem: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO territorial_importacoes
           (ano, uf, municipio, tipo, status, quantidade_linhas, mensagem, data_importacao)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            int(ano),
            str(uf or "").upper().strip(),
            municipio,
            TIPO_DATASET,
            status,
            int(quantidade or 0),
            mensagem,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
    conn.close()


def _download_zip_secao(ano: int) -> Path:
    fonte = get_fonte_dataset(TIPO_DATASET, ano)
    if not fonte:
        raise ValueError(f"Fonte nao configurada para {TIPO_DATASET}/{ano}.")
    pasta = Path(TSE_DOWNLOAD_DIR)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / fonte["arquivo_local"]
    if destino.exists() and zipfile.is_zipfile(destino):
        print(f"[TSE-SECAO] Usando ZIP local: {destino}")
        return destino

    print(f"[TSE-SECAO] Baixando {fonte['url_zip']}")
    resposta = requests.get(fonte["url_zip"], stream=True, timeout=60)
    resposta.raise_for_status()
    with destino.open("wb") as arquivo:
        for chunk in resposta.iter_content(chunk_size=1024 * 1024):
            if chunk:
                arquivo.write(chunk)
    if not zipfile.is_zipfile(destino):
        raise ValueError(f"Arquivo baixado nao e ZIP valido: {destino}")
    return destino


def _extrair_csv(caminho_zip: Path, ano: int, uf: str) -> Path:
    destino = Path(TSE_DOWNLOAD_DIR) / f"votacao_secao_{int(ano)}"
    destino.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(caminho_zip, "r") as zf:
        zf.extractall(destino)

    uf_ref = str(uf or "").upper().strip()
    arquivos = list(destino.rglob("*.csv"))
    if not arquivos:
        raise FileNotFoundError(f"Nenhum CSV encontrado em {destino}")
    candidatos = [p for p in arquivos if uf_ref in p.name.upper()]
    return (candidatos or arquivos)[0]


def _carregar_csv(caminho: Path) -> pd.DataFrame:
    separador, encoding = detectar_separador_encoding(str(caminho))
    df = pd.read_csv(caminho, sep=separador, encoding=encoding, dtype=str, low_memory=False)
    df.columns = [_normalizar_coluna(c) for c in df.columns]
    df.attrs["origem_arquivo"] = str(caminho)
    return df


def normalizar_votacao_secao(df: pd.DataFrame, ano: int, origem_arquivo: str | None = None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=COLUNAS_SAIDA)

    base = df.copy()
    base.columns = [_normalizar_coluna(c) for c in base.columns]
    origem = origem_arquivo or base.attrs.get("origem_arquivo")

    mapa = {
        "ano": _coluna(base, ["ano", "ano_eleicao"]),
        "turno": _coluna(base, ["turno", "nr_turno"]),
        "uf": _coluna(base, ["uf", "sg_uf"]),
        "municipio": _coluna(base, ["municipio", "nm_municipio", "nm_ue"]),
        "codigo_municipio_tse": _coluna(base, ["codigo_municipio_tse", "cd_municipio", "cd_municipio_tse"]),
        "zona": _coluna(base, ["zona", "nr_zona"]),
        "secao": _coluna(base, ["secao", "nr_secao"]),
        "local_votacao": _coluna(base, ["local_votacao", "nm_local_votacao", "ds_local_votacao"]),
        "endereco_local": _coluna(base, ["endereco_local", "endereco", "ds_endereco", "ds_endereco_local"]),
        "bairro": _coluna(base, ["bairro", "nm_bairro"]),
        "cargo": _coluna(base, ["cargo", "ds_cargo"]),
        "id_tse": _coluna(base, ["id_tse", "sq_candidato"]),
        "nome_civil": _coluna(base, ["nome_civil", "nm_candidato"]),
        "nome_urna": _coluna(base, ["nome_urna", "nm_urna_candidato"]),
        "numero": _coluna(base, ["numero", "nr_candidato"]),
        "partido": _coluna(base, ["partido", "sg_partido"]),
        "votos": _coluna(base, ["votos", "qt_votos_nominais", "qt_votos"]),
        "votos_validos": _coluna(base, ["votos_validos", "qt_votos_nominais_validos"]),
    }

    normalizado = pd.DataFrame(index=base.index)
    normalizado["ano"] = _serie(base, mapa["ano"]).map(lambda v: _safe_int(v, int(ano))).fillna(int(ano)).astype(int)
    normalizado["turno"] = _serie(base, mapa["turno"]).map(lambda v: _safe_int(v, 1))
    normalizado["uf"] = _serie(base, mapa["uf"]).map(lambda v: str(v).upper().strip()[:2] if _texto(v) else None)
    normalizado["municipio"] = _serie(base, mapa["municipio"]).map(_texto)
    normalizado["codigo_municipio_tse"] = _serie(base, mapa["codigo_municipio_tse"]).map(_texto)
    normalizado["zona"] = _serie(base, mapa["zona"]).map(_zona_secao)
    normalizado["secao"] = _serie(base, mapa["secao"]).map(_zona_secao)
    normalizado["local_votacao"] = _serie(base, mapa["local_votacao"]).map(_texto)
    normalizado["endereco_local"] = _serie(base, mapa["endereco_local"]).map(_texto)
    normalizado["bairro"] = _serie(base, mapa["bairro"]).map(_texto)
    normalizado["cargo"] = _serie(base, mapa["cargo"]).map(_texto)
    normalizado["id_tse"] = _serie(base, mapa["id_tse"]).map(_texto)
    normalizado["nome_civil"] = _serie(base, mapa["nome_civil"]).map(_texto)
    normalizado["nome_urna"] = _serie(base, mapa["nome_urna"]).map(_texto)
    normalizado["numero"] = _serie(base, mapa["numero"]).map(_texto)
    normalizado["partido"] = _serie(base, mapa["partido"]).map(_texto)
    normalizado["votos"] = _serie(base, mapa["votos"]).map(lambda v: _safe_int(v, 0)).fillna(0).astype(int)
    normalizado["votos_validos"] = _serie(base, mapa["votos_validos"]).map(_safe_int)
    normalizado["origem_arquivo"] = origem

    return normalizado[
        normalizado["uf"].notna()
        & normalizado["municipio"].notna()
        & normalizado["zona"].notna()
        & normalizado["secao"].notna()
    ][COLUNAS_SAIDA].reset_index(drop=True)


def salvar_votacao_secao(df: pd.DataFrame, ano: int, uf: str, municipio: str | None = None) -> int:
    if df is None or df.empty:
        _registrar_importacao(ano, uf, municipio, "sem_dados", 0, "Nenhuma linha normalizada.")
        return 0

    conn = get_connection()
    cur = conn.cursor()
    params = [int(ano), str(uf).upper().strip()]
    delete = "DELETE FROM votacao_secao_tse WHERE ano = ? AND UPPER(uf) = ?"
    if municipio:
        delete += " AND municipio LIKE ? COLLATE NOCASE"
        params.append(f"%{municipio}%")
    cur.execute(delete, params)
    cur.executemany(
        """INSERT INTO votacao_secao_tse
           (ano, turno, uf, municipio, codigo_municipio_tse, zona, secao,
            local_votacao, endereco_local, bairro, cargo, id_tse, nome_civil,
            nome_urna, numero, partido, votos, votos_validos, origem_arquivo)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [tuple(row[col] for col in COLUNAS_SAIDA) for _, row in df.iterrows()],
    )
    conn.commit()
    conn.close()
    _registrar_importacao(ano, uf, municipio, "importado", len(df), "Votacao por secao importada.")
    return len(df)


def importar_secao(ano: int, uf: str, municipio: str | None = None, arquivo: str | None = None) -> dict:
    init_database()
    uf_ref = str(uf or "").upper().strip()
    if arquivo:
        caminho_csv = Path(arquivo)
    else:
        caminho_zip = _download_zip_secao(ano)
        caminho_csv = _extrair_csv(caminho_zip, ano, uf_ref)

    bruto = _carregar_csv(caminho_csv)
    normalizado = normalizar_votacao_secao(bruto, ano=ano, origem_arquivo=str(caminho_csv))
    normalizado = normalizado[normalizado["uf"].astype(str).str.upper() == uf_ref].copy()
    if municipio:
        municipio_ref = _texto_key(municipio)
        normalizado = normalizado[
            normalizado["municipio"].map(_texto_key).str.contains(municipio_ref, na=False)
        ].copy()

    salvas = salvar_votacao_secao(normalizado, ano=ano, uf=uf_ref, municipio=municipio)
    return {
        "ano": int(ano),
        "uf": uf_ref,
        "municipio": municipio,
        "arquivo": str(caminho_csv),
        "linhas": salvas,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Importa votacao por secao eleitoral do TSE.")
    parser.add_argument("--uf", required=True, help="UF. Ex: SP")
    parser.add_argument("--ano", required=True, type=int, help="Ano eleitoral. Ex: 2024")
    parser.add_argument("--municipio", help='Municipio opcional. Ex: "Sao Paulo"')
    parser.add_argument("--arquivo", help="CSV local opcional de votacao por secao.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        resultado = importar_secao(args.ano, args.uf, municipio=args.municipio, arquivo=args.arquivo)
        print(f"[TSE-SECAO] Arquivo: {resultado['arquivo']}")
        print(f"[TSE-SECAO] Linhas importadas: {resultado['linhas']}")
        return 0
    except Exception as exc:
        _registrar_importacao(args.ano, args.uf, args.municipio, "erro", 0, str(exc))
        print(f"[TSE-SECAO] Erro: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
