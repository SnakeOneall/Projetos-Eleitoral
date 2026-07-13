"""Importa bases geograficas auxiliares para o SQLite local.

Uso:
    python scripts/import_geo_data.py --zonas-eleitorais
    python scripts/import_geo_data.py --uf SP --municipio "Sao Paulo"
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectors.geo_collector import (  # noqa: E402
    baixar_zonas_eleitorais_csv,
    carregar_zonas_eleitorais_csv,
    normalizar_zonas_eleitorais,
    salvar_zonas_eleitorais_no_banco,
)
from database.init_db import init_database  # noqa: E402


def _sem_acentos(valor: str) -> str:
    texto = str(valor or "")
    return "".join(
        char for char in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(char)
    )


def importar_zonas_eleitorais(
    uf: str | None = None,
    municipio: str | None = None,
    force: bool = False,
    arquivo: str | Path | None = None,
) -> dict:
    """Baixa, normaliza, filtra opcionalmente e salva zonas eleitorais."""
    init_database()
    caminho = Path(arquivo) if arquivo else baixar_zonas_eleitorais_csv(force=force)
    df_bruto = carregar_zonas_eleitorais_csv(caminho)
    df = normalizar_zonas_eleitorais(df_bruto)
    df.attrs["arquivo_local"] = str(caminho)

    if uf:
        df = df[df["uf"].astype(str).str.upper() == str(uf).upper().strip()].copy()
    if municipio:
        termo = _sem_acentos(str(municipio).strip()).lower()
        municipios_norm = df["municipio"].astype(str).map(lambda valor: _sem_acentos(valor).lower())
        df = df[municipios_norm.str.contains(termo, case=False, na=False)].copy()

    salvas = salvar_zonas_eleitorais_no_banco(df)
    com_coordenadas = int(df[["latitude", "longitude"]].notna().all(axis=1).sum()) if not df.empty else 0
    return {
        "arquivo": str(caminho),
        "linhas_normalizadas": int(len(df)),
        "zonas_importadas": int(salvas),
        "zonas_com_lat_lon": com_coordenadas,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Importa bases geograficas eleitorais.")
    parser.add_argument("--zonas-eleitorais", action="store_true", help="Importa o CSV de zonas eleitorais.")
    parser.add_argument("--uf", help="Filtra por UF. Ex: SP")
    parser.add_argument("--municipio", help='Filtra por municipio. Ex: "Sao Paulo"')
    parser.add_argument("--arquivo", help="CSV local com zonas e, se houver, latitude/longitude.")
    parser.add_argument("--forcar-download", action="store_true", help="Baixa novamente mesmo se houver CSV local.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if not args.zonas_eleitorais and not (args.uf or args.municipio):
        print("[GEO] Informe --zonas-eleitorais ou filtros --uf/--municipio.")
        return 2

    resultado = importar_zonas_eleitorais(
        uf=args.uf,
        municipio=args.municipio,
        force=args.forcar_download,
        arquivo=args.arquivo,
    )
    print(f"[GEO] Arquivo: {resultado['arquivo']}")
    print(f"[GEO] Zonas normalizadas no recorte: {resultado['linhas_normalizadas']}")
    print(f"[GEO] Zonas importadas/atualizadas: {resultado['zonas_importadas']}")
    print(f"[GEO] Zonas com latitude/longitude: {resultado['zonas_com_lat_lon']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
