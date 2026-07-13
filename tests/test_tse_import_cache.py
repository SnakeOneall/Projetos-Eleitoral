from pathlib import Path
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import database.init_db as init_db
from analysis.tse_aggregations import agregar_votacao_por_municipio
from database.db_utils import (
    buscar_candidaturas_tse,
    listar_importacoes_tse,
    registrar_importacao_tse,
    salvar_candidaturas_tse,
    verificar_importacao_tse,
)
from scripts import import_tse_history


@pytest.fixture()
def banco_temporario(tmp_path, monkeypatch):
    db_path = tmp_path / "radar_eleitoral_test.db"
    monkeypatch.setattr(init_db, "DB_PATH", str(db_path))
    init_db.init_database()
    return db_path


def _df_candidaturas() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "id_tse": "100",
            "ano": 2024,
            "turno": 1,
            "uf": "SP",
            "municipio": "Sao Paulo",
            "codigo_municipio_tse": "71072",
            "zona": "1",
            "cargo": "VEREADOR",
            "nome_civil": "Maria Teste",
            "nome_urna": "Maria",
            "numero": "12345",
            "partido": "TST",
            "nome_partido": "Partido Teste",
            "votos": 10,
            "votos_validos": 100,
            "situacao": "ELEITO",
            "origem_arquivo": "teste.csv",
        },
        {
            "id_tse": "100",
            "ano": 2024,
            "turno": 1,
            "uf": "SP",
            "municipio": "Sao Paulo",
            "codigo_municipio_tse": "71072",
            "zona": "2",
            "cargo": "VEREADOR",
            "nome_civil": "Maria Teste",
            "nome_urna": "Maria",
            "numero": "12345",
            "partido": "TST",
            "nome_partido": "Partido Teste",
            "votos": 15,
            "votos_validos": 100,
            "situacao": "ELEITO",
            "origem_arquivo": "teste.csv",
        },
        {
            "id_tse": "200",
            "ano": 2024,
            "turno": 1,
            "uf": "SP",
            "municipio": "Osasco",
            "codigo_municipio_tse": "67890",
            "zona": "3",
            "cargo": "PREFEITO",
            "nome_civil": "Joao Exemplo",
            "nome_urna": "Joao",
            "numero": "99",
            "partido": "ABC",
            "nome_partido": "Partido ABC",
            "votos": 50,
            "votos_validos": 200,
            "situacao": "NAO ELEITO",
            "origem_arquivo": "teste.csv",
        },
    ])


def test_registro_de_importacao_tse(banco_temporario):
    importacao_id = registrar_importacao_tse(
        ano=2024,
        uf="SP",
        arquivo_origem="teste.csv",
        status="importado",
        quantidade_linhas=3,
        mensagem="ok",
        hash_arquivo="abc",
    )

    assert importacao_id > 0
    assert verificar_importacao_tse(2024, "sp")["quantidade_linhas"] == 3
    assert listar_importacoes_tse()[0]["hash_arquivo"] == "abc"


def test_busca_por_ano_uf_e_filtros_no_cache_tse(banco_temporario):
    salvar_candidaturas_tse(_df_candidaturas(), ano=2024, uf="SP")

    resultados = buscar_candidaturas_tse(ano=2024, uf="sp", cargo="Vereador", nome_urna="maria")

    assert len(resultados) == 2
    assert {r["zona"] for r in resultados} == {"1", "2"}
    assert all(r["id_tse"] == "100" for r in resultados)


def test_importador_nao_reimporta_quando_ja_existe(banco_temporario, monkeypatch):
    registrar_importacao_tse(
        ano=2024,
        uf="SP",
        arquivo_origem="teste.csv",
        status="importado",
        quantidade_linhas=3,
        mensagem="ok",
        hash_arquivo="abc",
    )

    def falhar_download(*args, **kwargs):
        raise AssertionError("download nao deveria ser chamado")

    monkeypatch.setattr(import_tse_history.tse_collector, "baixar_arquivo_tse", falhar_download)

    resultado = import_tse_history.importar_tse_ano_uf(2024, "SP")

    assert resultado["status"] == "pulado"
    assert len(listar_importacoes_tse()) == 1


def test_busca_local_nao_depende_de_download(banco_temporario, monkeypatch):
    salvar_candidaturas_tse(_df_candidaturas(), ano=2024, uf="SP")

    def falhar_download(*args, **kwargs):
        raise AssertionError("busca local nao pode baixar ZIP")

    monkeypatch.setattr(import_tse_history.tse_collector, "baixar_arquivo_tse", falhar_download)

    resultados = buscar_candidaturas_tse(ano=2024, uf="SP", numero="12345")

    assert len(resultados) == 2


def test_agregacao_por_municipio_soma_zonas(banco_temporario):
    salvar_candidaturas_tse(_df_candidaturas(), ano=2024, uf="SP")
    resultados = buscar_candidaturas_tse(ano=2024, uf="SP", id_tse="100")

    agregado = agregar_votacao_por_municipio(pd.DataFrame(resultados))

    assert len(agregado) == 1
    assert agregado.iloc[0]["municipio"] == "Sao Paulo"
    assert agregado.iloc[0]["votos"] == 25
