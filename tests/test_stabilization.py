from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectors.emendas_collector import normalizar_resposta_portal_transparencia
from collectors.tse_collector import _dados_teste
from database.init_db import DB_PATH, init_database


def test_text_files_are_utf8_without_common_mojibake_markers():
    markers = ("\u00c3\u00a1", "\u00c3\u00a9", "\u00c3\u00aa", "\u00c3\u00a3", "\u00c3\u00b5", "\u00c3\u00a7", "\u00c3\u00ba", "\u00c3\u00b3", "\u00e2\u20ac\u201d", "\u00e2\u20ac\u201c", "\u00e2\u20ac\u0153", "\u00e2\u20ac", "\u00f0\u0178", "\u00ef\u00b8")
    skip_parts = {".venv", "__pycache__", "raw"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".py", ".md", ".csv", ".txt"}:
            continue
        if any(part in skip_parts for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        assert not any(marker in text for marker in markers), f"possivel mojibake em {path}"


def test_database_has_data_source_columns():
    init_database()
    conn = sqlite3.connect(DB_PATH)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(candidatos)")}
    finally:
        conn.close()
    assert {"origem_dados", "fonte_dados"}.issubset(columns)


def test_tse_demo_data_marks_demo_source():
    df = _dados_teste(2024, "SP")
    assert set(df["origem_dados"]) == {"demo"}
    assert df["fonte_dados"].str.contains("MVP").all()


def test_portal_transparencia_response_is_normalized_to_internal_contract():
    df = normalizar_resposta_portal_transparencia([
        {
            "codigo": "123",
            "nomeAutor": "Teste Parlamentar",
            "siglaPartido": "TST",
            "siglaUf": "sp",
            "ano": 2024,
            "localidade": {"nomeMunicipio": "Sao Paulo", "codigoIBGE": "3550308"},
            "valorEmpenhado": "1.000,50",
            "valorLiquidado": "500,25",
            "valorPago": "250,10",
        }
    ])

    assert len(df) == 1
    row = df.iloc[0]
    assert row["parlamentar_nome"] == "Teste Parlamentar"
    assert row["uf"] == "SP"
    assert row["municipio_beneficiado"] == "Sao Paulo"
    assert row["valor_empenhado"] == 1000.50
    assert row["valor_liquidado"] == 500.25
    assert row["valor_pago"] == 250.10
    assert row["fonte"] == "Portal da Transparencia"
    assert "codigo=123" in row["link_fonte"]
