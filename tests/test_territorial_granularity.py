from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.territorial_analysis import analisar_distribuicao_territorial  # noqa: E402
from analysis.territorial_rules import detectar_escopo_cargo  # noqa: E402
from reports.pdf_generator import _preparar_distribuicao_territorial_pdf  # noqa: E402


def test_vereador_agrupa_por_zona_se_so_houver_zona():
    df = pd.DataFrame({
        "uf": ["SP", "SP"],
        "municipio": ["São Paulo", "São Paulo"],
        "zona": ["001", "002"],
        "votos": [100, 50],
    })

    resultado = analisar_distribuicao_territorial(df, "Vereador", municipio="São Paulo", uf="SP")

    assert resultado["nivel"] == "zona"
    assert list(resultado["dados"]["chave_territorial"]) == ["001", "002"]
    assert "zona eleitoral" in resultado["mensagem"]


def test_vereador_agrupa_por_secao_se_houver_secao():
    df = pd.DataFrame({
        "uf": ["SP", "SP"],
        "municipio": ["São Paulo", "São Paulo"],
        "zona": ["001", "001"],
        "secao": ["010", "011"],
        "votos": [70, 30],
    })

    resultado = analisar_distribuicao_territorial(df, "Vereador", municipio="São Paulo", uf="SP")

    assert resultado["nivel"] == "secao"
    assert list(resultado["dados"]["chave_territorial"]) == ["010", "011"]


def test_vereador_agrupa_por_bairro_se_houver_bairro():
    df = pd.DataFrame({
        "uf": ["SP", "SP"],
        "municipio": ["São Paulo", "São Paulo"],
        "zona": ["001", "002"],
        "secao": ["010", "011"],
        "bairro": ["Mooca", "Lapa"],
        "votos": [40, 90],
    })

    resultado = analisar_distribuicao_territorial(df, "Vereador", municipio="São Paulo", uf="SP")

    assert resultado["nivel"] == "bairro"
    assert resultado["dados"].iloc[0]["chave_territorial"] == "Lapa"


def test_prefeito_segue_regra_municipal():
    regra = detectar_escopo_cargo("Prefeito")
    df = pd.DataFrame({
        "uf": ["SP"],
        "municipio": ["São Paulo"],
        "zona": ["376"],
        "votos": [1000],
    })

    resultado = analisar_distribuicao_territorial(df, "Prefeito", municipio="São Paulo", uf="SP")

    assert regra["nivel_principal"] == "municipal"
    assert resultado["nivel"] == "zona"


def test_deputado_estadual_agrupa_por_municipio():
    df = pd.DataFrame({
        "uf": ["SP", "SP"],
        "municipio": ["São Paulo", "Campinas"],
        "zona": ["001", "001"],
        "votos": [100, 80],
    })

    resultado = analisar_distribuicao_territorial(df, "Deputado Estadual", uf="SP")

    assert resultado["nivel"] == "municipio"
    assert list(resultado["dados"]["chave_territorial"]) == ["São Paulo", "Campinas"]


def test_deputado_federal_agrupa_por_municipio():
    df = pd.DataFrame({
        "uf": ["SP", "SP"],
        "municipio": ["São Paulo", "Osasco"],
        "zona": ["001", "001"],
        "votos": [90, 110],
    })

    resultado = analisar_distribuicao_territorial(df, "Deputado Federal", uf="SP")

    assert resultado["nivel"] == "municipio"
    assert resultado["dados"].iloc[0]["chave_territorial"] == "Osasco"


def test_deputado_distrital_tenta_regiao_administrativa_e_zona():
    df_regiao = pd.DataFrame({
        "uf": ["DF", "DF"],
        "regiao_administrativa": ["Ceilândia", "Plano Piloto"],
        "municipio": ["Brasília", "Brasília"],
        "zona": ["001", "002"],
        "votos": [200, 120],
    })
    df_zona = df_regiao.drop(columns=["regiao_administrativa"])

    resultado_regiao = analisar_distribuicao_territorial(df_regiao, "Deputado Distrital", uf="DF")
    resultado_zona = analisar_distribuicao_territorial(df_zona, "Deputado Distrital", uf="DF")

    assert resultado_regiao["nivel"] == "regiao_administrativa"
    assert resultado_zona["nivel"] == "zona"


def test_fallback_avisa_quando_cargo_municipal_so_tem_municipio():
    df = pd.DataFrame({
        "uf": ["SP"],
        "municipio": ["São Paulo"],
        "votos": [1000],
    })

    resultado = analisar_distribuicao_territorial(df, "Vereador", municipio="São Paulo", uf="SP")

    assert resultado["nivel"] == "municipio"
    assert "cargo municipal" in resultado["mensagem"].lower()


def test_pdf_nao_consolida_cargo_municipal_quando_ha_zona(monkeypatch):
    candidato = {
        "id": 123,
        "id_tse": "999",
        "cargo": "Vereador",
        "uf": "SP",
    }
    zonas = [
        {"ano": 2024, "uf": "SP", "municipio": "São Paulo", "zona": "001", "votos": 70},
        {"ano": 2024, "uf": "SP", "municipio": "São Paulo", "zona": "002", "votos": 30},
    ]

    monkeypatch.setattr("reports.pdf_generator.buscar_votacao_secao_por_candidato", lambda candidato_id, ano: [])
    monkeypatch.setattr("reports.pdf_generator.buscar_votacao_zona_por_candidato", lambda candidato_id, ano: zonas)
    monkeypatch.setattr("reports.pdf_generator.buscar_votacao_por_candidato", lambda candidato_id, ano_inicial=None, ano_final=None: [
        {"ano": 2024, "uf": "SP", "municipio": "São Paulo", "votos": 100}
    ])

    resultado = _preparar_distribuicao_territorial_pdf(candidato, 2024)

    assert resultado["nivel"] == "zona"
    assert list(resultado["dados"]["chave_territorial"]) == ["001", "002"]
