"""Importa historico do TSE para o cache local tratado.

Uso:
    python scripts/import_tse_history.py --uf SP --anos 2024
    python scripts/import_tse_history.py --uf SP --anos 2024 2020
    python scripts/import_tse_history.py --uf SP --anos 2022 --somente-baixados
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import collectors.tse_collector as tse_collector
from database.db_utils import (
    TIPO_ARQUIVO_TSE_PADRAO,
    registrar_importacao_tse,
    salvar_candidaturas_tse,
    verificar_importacao_tse,
)
from database.init_db import init_database

TSE_DIR = ROOT / "data" / "raw" / "tse"
tse_collector.TSE_DOWNLOAD_DIR = str(TSE_DIR)


def _zip_local(ano: int) -> Path:
    return TSE_DIR / f"tse_{int(ano)}.zip"


def _zip_valido(caminho: Path) -> bool:
    return caminho.exists() and zipfile.is_zipfile(caminho)


def _hash_arquivo(caminho: Path) -> str | None:
    if not caminho.exists():
        return None
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def importar_tse_ano_uf(
    ano: int,
    uf: str,
    forcar: bool = False,
    somente_baixados: bool = False,
) -> dict:
    """Importa um ano/UF do TSE para candidaturas_tse.

    A funcao baixa apenas quando o ZIP local nao existe. Com
    somente_baixados=True, falha de forma controlada se o ZIP local nao
    estiver presente e valido.
    """
    init_database()
    ano = int(ano)
    uf = str(uf).upper().strip()
    zip_path = _zip_local(ano)

    existente = verificar_importacao_tse(ano, uf)
    if existente and not forcar:
        mensagem = f"{uf}/{ano} ja importado; use --forcar para reimportar."
        return {
            "ano": ano,
            "uf": uf,
            "status": "pulado",
            "quantidade_linhas": existente.get("quantidade_linhas", 0),
            "mensagem": mensagem,
            "arquivo_origem": existente.get("arquivo_origem"),
            "hash_arquivo": existente.get("hash_arquivo"),
        }

    if somente_baixados and not _zip_valido(zip_path):
        mensagem = (
            f"ZIP local nao encontrado ou invalido para {uf}/{ano}: {zip_path}. "
            "Modo --somente-baixados nao permite download."
        )
        registrar_importacao_tse(
            ano=ano,
            uf=uf,
            tipo_arquivo=TIPO_ARQUIVO_TSE_PADRAO,
            arquivo_origem=str(zip_path),
            status="erro",
            quantidade_linhas=0,
            mensagem=mensagem,
            hash_arquivo=None,
        )
        return {
            "ano": ano,
            "uf": uf,
            "status": "erro",
            "quantidade_linhas": 0,
            "mensagem": mensagem,
            "arquivo_origem": str(zip_path),
            "hash_arquivo": None,
        }

    try:
        TSE_DIR.mkdir(parents=True, exist_ok=True)
        if _zip_valido(zip_path):
            caminho_zip = str(zip_path)
            print(f"[TSE-IMPORT] Usando ZIP local valido: {caminho_zip}")
        else:
            caminho_zip = tse_collector.baixar_arquivo_tse(ano, destino=str(TSE_DIR))

        caminho_zip_path = Path(caminho_zip)
        hash_zip = _hash_arquivo(caminho_zip_path)
        tse_collector.extrair_zip(caminho_zip)
        csv_path = tse_collector.localizar_csv_tse(ano, uf)
        df = tse_collector.carregar_dados_tse(ano=ano, uf=uf)
        df["origem_arquivo"] = str(csv_path)
        quantidade = salvar_candidaturas_tse(df, ano=ano, uf=uf)

        mensagem = f"Importacao concluida para {uf}/{ano}: {quantidade} linha(s)."
        registrar_importacao_tse(
            ano=ano,
            uf=uf,
            tipo_arquivo=TIPO_ARQUIVO_TSE_PADRAO,
            arquivo_origem=str(csv_path),
            status="importado",
            quantidade_linhas=quantidade,
            mensagem=mensagem,
            hash_arquivo=hash_zip,
        )
        return {
            "ano": ano,
            "uf": uf,
            "status": "importado",
            "quantidade_linhas": quantidade,
            "mensagem": mensagem,
            "arquivo_origem": str(csv_path),
            "hash_arquivo": hash_zip,
        }
    except Exception as exc:
        mensagem = f"Erro ao importar {uf}/{ano}: {exc}"
        hash_zip = _hash_arquivo(zip_path) if zip_path.exists() else None
        registrar_importacao_tse(
            ano=ano,
            uf=uf,
            tipo_arquivo=TIPO_ARQUIVO_TSE_PADRAO,
            arquivo_origem=str(zip_path),
            status="erro",
            quantidade_linhas=0,
            mensagem=mensagem,
            hash_arquivo=hash_zip,
        )
        return {
            "ano": ano,
            "uf": uf,
            "status": "erro",
            "quantidade_linhas": 0,
            "mensagem": mensagem,
            "arquivo_origem": str(zip_path),
            "hash_arquivo": hash_zip,
        }


def importar_tse_historico(
    anos: list[int],
    uf: str,
    forcar: bool = False,
    somente_baixados: bool = False,
) -> list[dict]:
    return [
        importar_tse_ano_uf(
            ano=ano,
            uf=uf,
            forcar=forcar,
            somente_baixados=somente_baixados,
        )
        for ano in anos
    ]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Importa dados historicos do TSE para SQLite.")
    parser.add_argument("--uf", required=True, help="UF a importar. Ex: SP")
    parser.add_argument("--anos", required=True, nargs="+", type=int, help="Anos eleitorais. Ex: 2024 2020")
    parser.add_argument("--forcar", action="store_true", help="Reimporta mesmo que ano/UF ja exista.")
    parser.add_argument(
        "--somente-baixados",
        action="store_true",
        help="Usa apenas ZIPs locais ja baixados; nao tenta download.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    resultados = importar_tse_historico(
        anos=args.anos,
        uf=args.uf,
        forcar=args.forcar,
        somente_baixados=args.somente_baixados,
    )
    for resultado in resultados:
        print(
            "[TSE-IMPORT] "
            f"{resultado['uf']}/{resultado['ano']} - {resultado['status']} - "
            f"{resultado['mensagem']}"
        )
    return 1 if any(r["status"] == "erro" for r in resultados) else 0


if __name__ == "__main__":
    raise SystemExit(main())
