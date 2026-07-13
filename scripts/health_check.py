"""
Health check do MVP Radar Eleitoral IA.

Executa validacoes leves, sem rede, para confirmar que o projeto esta
importavel, o banco foi migrado e os metadados de origem dos dados existem.
"""

import importlib
import os
import py_compile
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectors.emendas_collector import normalizar_resposta_portal_transparencia
from collectors.tse_collector import _dados_teste
from database.init_db import DB_PATH, init_database
from reports.pdf_generator import gerar_pdf_relatorio

TEXT_EXTENSIONS = {".py", ".md", ".csv", ".txt"}
MOJIBAKE_MARKERS = ("\u00c3\u00a1", "\u00c3\u00a9", "\u00c3\u00aa", "\u00c3\u00a3", "\u00c3\u00b5", "\u00c3\u00a7", "\u00c3\u00ba", "\u00c3\u00b3", "\u00e2\u20ac\u201d", "\u00e2\u20ac\u201c", "\u00e2\u20ac\u0153", "\u00e2\u20ac", "\u00f0\u0178", "\u00ef\u00b8")
SKIP_PARTS = {".venv", "__pycache__", "raw"}
REQUIRED_REQUIREMENTS = {
    "streamlit", "pandas", "plotly", "requests", "python-dotenv",
    "reportlab", "pytest", "openpyxl", "unidecode", "python-dateutil",
}


def check_encoding() -> list[str]:
    problemas = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            problemas.append(f"{path}: nao esta em UTF-8")
            continue
        if any(marker in text for marker in MOJIBAKE_MARKERS):
            problemas.append(f"{path}: possivel mojibake")
    return problemas


def check_database() -> list[str]:
    problemas = []
    init_database()
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute("PRAGMA table_info(candidatos)")
        columns = {row[1] for row in cur.fetchall()}
        for column in ("origem_dados", "fonte_dados"):
            if column not in columns:
                problemas.append(f"coluna ausente em candidatos: {column}")

        cur = conn.execute("PRAGMA table_info(tse_importacoes)")
        import_columns = {row[1] for row in cur.fetchall()}
        for column in ("ano", "uf", "tipo_arquivo", "status", "hash_arquivo"):
            if column not in import_columns:
                problemas.append(f"coluna ausente em tse_importacoes: {column}")

        cur = conn.execute("PRAGMA table_info(candidaturas_tse)")
        cache_columns = {row[1] for row in cur.fetchall()}
        for column in ("id_tse", "ano", "uf", "cargo", "nome_urna", "votos", "origem_arquivo"):
            if column not in cache_columns:
                problemas.append(f"coluna ausente em candidaturas_tse: {column}")

        cur = conn.execute("SELECT COUNT(*) FROM candidatos")
        if cur.fetchone()[0] == 0:
            problemas.append("tabela candidatos esta vazia")
    finally:
        conn.close()
    return problemas


def check_imports() -> list[str]:
    problemas = []
    for modulo in [
        "commercial_flow",
        "collectors.tse_collector",
        "collectors.emendas_collector",
        "analysis.electoral_analysis",
        "analysis.effort_result_analysis",
        "analysis.tse_aggregations",
        "ai.communication_planner",
        "compliance.electoral_compliance",
        "reports.pdf_generator",
        "database.db_utils",
        "database.init_db",
        "scripts.import_tse_history",
    ]:
        try:
            importlib.import_module(modulo)
        except Exception as exc:
            problemas.append(f"falha ao importar {modulo}: {exc}")
    try:
        py_compile.compile(str(ROOT / "app.py"), doraise=True)
    except Exception as exc:
        problemas.append(f"app.py nao compila: {exc}")
    return problemas


def check_collectors() -> list[str]:
    problemas = []
    df_tse = _dados_teste(2024, "SP")
    for column in ("origem_dados", "fonte_dados"):
        if column not in df_tse.columns:
            problemas.append(f"coletor TSE sem coluna {column}")

    df_portal = normalizar_resposta_portal_transparencia([
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
    expected = {"parlamentar_nome", "municipio_beneficiado", "valor_pago", "fonte", "link_fonte"}
    missing = expected - set(df_portal.columns)
    if missing:
        problemas.append(f"normalizacao Portal sem colunas: {sorted(missing)}")
    if not df_portal.empty and df_portal.iloc[0]["fonte"] != "Portal da Transparencia":
        problemas.append("normalizacao Portal nao marcou a fonte esperada")
    return problemas


def check_requirements() -> list[str]:
    problemas = []
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    normalizados = {
        linha.split("==")[0].split(">=")[0].split("<=")[0].strip().lower()
        for linha in requirements
        if linha.strip() and not linha.strip().startswith("#")
    }
    faltantes = REQUIRED_REQUIREMENTS - normalizados
    if faltantes:
        problemas.append(f"requirements.txt sem dependencias: {sorted(faltantes)}")
    return problemas


def check_streamlit_deprecations() -> list[str]:
    problemas = []
    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    if "use_container_width" in app_text:
        problemas.append("app.py ainda usa use_container_width")
    return problemas


def check_pdf_generation() -> list[str]:
    problemas = []
    init_database()
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT id FROM candidatos ORDER BY id LIMIT 1").fetchone()
    finally:
        conn.close()
    if not row:
        return ["nao ha candidato no banco para testar PDF"]
    try:
        caminho = Path(gerar_pdf_relatorio(int(row[0]), 2016, 2020))
    except Exception as exc:
        return [f"falha ao gerar PDF: {exc}"]
    if not caminho.exists() or caminho.stat().st_size == 0:
        problemas.append(f"PDF gerado invalido ou vazio: {caminho}")
    return problemas


def check_warnings() -> list[str]:
    avisos = []
    if not os.getenv("PORTAL_TRANSPARENCIA_API_KEY") and not (ROOT / "config" / "secrets_local.py").exists():
        avisos.append("PORTAL_TRANSPARENCIA_API_KEY nao configurada; consultas online de emendas serao puladas.")

    tse_dir = ROOT / "data" / "raw" / "tse"
    if not tse_dir.exists() or not any(tse_dir.glob("tse_*")):
        avisos.append("Nenhum arquivo local do TSE encontrado em data/raw/tse; importe pela aba Administracao ou pelo script.")
    return avisos


def main() -> int:
    checks = {
        "encoding": check_encoding(),
        "imports": check_imports(),
        "database": check_database(),
        "collectors": check_collectors(),
        "requirements": check_requirements(),
        "streamlit": check_streamlit_deprecations(),
        "pdf": check_pdf_generation(),
    }
    problemas = [f"[{grupo}] {item}" for grupo, itens in checks.items() for item in itens]
    if problemas:
        print("[FAIL] Health check encontrou problemas:")
        for item in problemas:
            print(f" - {item}")
        return 1
    avisos = check_warnings()
    for aviso in avisos:
        print(f"[WARN] {aviso}")
    print("[OK] Health check concluido sem problemas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
