from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.territorial_analysis import (  # noqa: E402
    agregar_votos_por_zona,
    cruzar_votos_com_zonas,
)
from collectors.geo_collector import (  # noqa: E402
    buscar_zona,
    normalizar_zonas_eleitorais,
    salvar_zonas_eleitorais_no_banco,
)
import database.init_db as init_db_module  # noqa: E402
from database.init_db import init_database  # noqa: E402
from ui_components import render_territorial_map_or_ranking  # noqa: E402


class FakeStreamlit:
    def __init__(self):
        self.warnings = []
        self.figures = []
        self.tables = []

    def markdown(self, *args, **kwargs):
        return None

    def metric(self, *args, **kwargs):
        return None

    def warning(self, mensagem, *args, **kwargs):
        self.warnings.append(mensagem)

    def info(self, *args, **kwargs):
        return None

    def success(self, *args, **kwargs):
        return None

    def caption(self, *args, **kwargs):
        return None

    def dataframe(self, dados, *args, **kwargs):
        self.tables.append(dados)

    def plotly_chart(self, fig, *args, **kwargs):
        self.figures.append(fig)


def test_normalizacao_de_zonas_eleitorais_detecta_colunas_e_coordenadas():
    raw = pd.DataFrame({
        "SG_UF": ["sp"],
        "Município": ["são paulo"],
        "id": ["26-0001"],
        "Nome Zona": ["Cartório Central"],
        "endereco_tse": ["Rua Teste, 100"],
        "Bairro": ["Centro"],
        "Latitude": ["-23,5500"],
        "Longitude": ["-46.6300"],
    })

    df = normalizar_zonas_eleitorais(raw)

    assert len(df) == 1
    assert df.iloc[0]["uf"] == "SP"
    assert df.iloc[0]["municipio"] == "São Paulo"
    assert df.iloc[0]["zona"] == "001"
    assert df.iloc[0]["latitude"] == -23.55
    assert df.iloc[0]["longitude"] == -46.63


def test_importacao_fake_de_zona_no_banco(monkeypatch, tmp_path):
    monkeypatch.setattr(init_db_module, "DB_PATH", str(tmp_path / "geo_teste.db"))
    init_database()
    raw = pd.DataFrame({
        "uf": ["TT"],
        "municipio": ["Cidade Geo Teste"],
        "zona": ["999"],
        "nome_zona": ["Zona Teste"],
        "endereco": ["Rua Teste"],
        "bairro": ["Centro"],
        "latitude": [-10.0],
        "longitude": [-40.0],
    })

    salvas = salvar_zonas_eleitorais_no_banco(raw)
    zona = buscar_zona("TT", "Cidade Geo Teste", "999")

    assert salvas == 1
    assert zona is not None
    assert zona["zona"] == "999"


def test_agregacao_de_votos_por_zona():
    votos = pd.DataFrame({
        "uf": ["SP", "SP", "SP"],
        "municipio": ["São Paulo", "São Paulo", "São Paulo"],
        "zona": [1, "001", 2],
        "votos": [10, 5, 5],
    })

    agregado = agregar_votos_por_zona(votos)

    assert agregado.iloc[0]["zona"] == "001"
    assert agregado.iloc[0]["votos"] == 15
    assert round(float(agregado.iloc[0]["percentual"]), 2) == 75.0


def test_cruzamento_votos_com_zonas_preserva_ranking_e_coordenadas():
    votos = pd.DataFrame({
        "uf": ["SP", "SP"],
        "municipio": ["São Paulo", "São Paulo"],
        "zona": ["001", "002"],
        "votos": [100, 50],
    })
    zonas = pd.DataFrame({
        "uf": ["SP", "SP"],
        "municipio": ["São Paulo", "São Paulo"],
        "zona": ["001", "002"],
        "latitude": [-23.55, None],
        "longitude": [-46.63, None],
        "fonte": ["teste", "teste"],
    })

    cruzado = cruzar_votos_com_zonas(votos, zonas)

    assert list(cruzado["votos"]) == [100, 50]
    assert bool(cruzado.iloc[0]["tem_coordenadas"]) is True
    assert bool(cruzado.iloc[1]["tem_coordenadas"]) is False


def test_renderer_sem_lat_lon_nao_quebra_e_usa_ranking(monkeypatch):
    fake_st = FakeStreamlit()
    monkeypatch.setattr("ui_components.st", fake_st)
    df = pd.DataFrame({
        "uf": ["SP", "SP"],
        "municipio": ["São Paulo", "Campinas"],
        "cargo": ["Deputado Federal", "Deputado Federal"],
        "votos": [120, 80],
    })

    resultado = render_territorial_map_or_ranking(
        df,
        cargo="Deputado Federal",
        uf="SP",
        key_prefix="teste_geo_sem_latlon",
    )

    assert resultado["tipo_visualizacao"] == "ranking"
    assert resultado["tem_mapa"] is False
    assert fake_st.warnings
    assert fake_st.figures


def test_renderer_nao_mostra_mapa_azul_vazio_sem_geodata(monkeypatch):
    fake_st = FakeStreamlit()
    monkeypatch.setattr("ui_components.st", fake_st)
    df = pd.DataFrame({
        "uf": ["SP", "SP"],
        "municipio": ["São Paulo", "São Paulo"],
        "cargo": ["Vereador", "Vereador"],
        "zona": ["001", "002"],
        "votos": [100, 50],
    })
    monkeypatch.setattr(
        "ui_components.preparar_mapa_vereador_sp",
        lambda _: {
            "tipo": "ranking",
            "tem_mapa": False,
            "dados": agregar_votos_por_zona(df),
            "mensagem": "sem geodata",
        },
    )

    resultado = render_territorial_map_or_ranking(
        df,
        cargo="Vereador",
        municipio="São Paulo",
        uf="SP",
        key_prefix="teste_geo_ranking_zona",
    )

    assert resultado["tipo_visualizacao"] == "ranking"
    assert resultado["tem_mapa"] is False
    assert fake_st.figures[0].data[0].type == "bar"
