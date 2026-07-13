from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from commercial_flow import criar_status_fluxo, filtrar_emendas_localidade, montar_auditoria_dados
from collectors.emendas_collector import normalizar_resposta_portal_transparencia
from reports.pdf_generator import gerar_pdf_relatorio


def test_fluxo_status_indicators():
    status = criar_status_fluxo(
        tse_registros=10,
        candidato={"id": 1},
        emendas_count=2,
        analise_count=5,
        plano={"objetivo_geral": "teste"},
        pdf_path="relatorio.pdf",
    )

    assert status["tse_carregado"] is True
    assert status["candidato_salvo"] is True
    assert status["emendas_carregadas"] is True
    assert status["analise_calculada"] is True
    assert status["plano_gerado"] is True
    assert status["pdf_gerado"] is True


def test_auditoria_dados_contem_origem_quantidades_e_filtros():
    auditoria = montar_auditoria_dados(
        candidato={"origem_dados": "real", "fonte_dados": "TSE"},
        tse_registros=8,
        emendas_count=3,
        filtros={"uf": "SP"},
        origem_emendas="Banco local",
    )

    assert auditoria["origem_dados_eleitorais"] == "real"
    assert auditoria["quantidade_registros_tse"] == 8
    assert auditoria["quantidade_emendas"] == 3
    assert auditoria["filtros_usados"] == {"uf": "SP"}
    assert auditoria["data_hora_coleta"]


def test_filtros_localidade_de_emendas_por_ano_uf_municipio_codigo_e_autor():
    emendas = [
        {
            "ano": 2024,
            "codigo_ibge": "3550308",
            "municipio_beneficiado": "Sao Paulo",
            "uf": "SP",
            "parlamentar_nome": "Maria Teste",
            "valor_pago": 100,
        },
        {
            "ano": 2024,
            "codigo_ibge": "3304557",
            "municipio_beneficiado": "Rio de Janeiro",
            "uf": "RJ",
            "parlamentar_nome": "Outro Autor",
            "valor_pago": 200,
        },
    ]

    df = filtrar_emendas_localidade(
        emendas,
        ano=2024,
        codigo_ibge="3550308",
        municipio="sao",
        uf="SP",
        autor="maria",
        niveis=["municipal"],
    )

    assert len(df) == 1
    assert df.iloc[0]["municipio_beneficiado"] == "Sao Paulo"


def test_normalizacao_de_emendas_portal_com_filtros_multinivel():
    df = normalizar_resposta_portal_transparencia([
        {
            "codigo": "999",
            "nomeAutor": "Autor Nacional",
            "siglaUf": "br",
            "anoEmenda": 2025,
            "municipioBeneficiado": "",
            "valorEmpenhado": "2.000,00",
            "valorLiquidado": "1.500,00",
            "valorPago": "1.000,00",
        }
    ])

    assert len(df) == 1
    assert df.iloc[0]["ano"] == 2025
    assert df.iloc[0]["valor_pago"] == 1000.0
    assert df.iloc[0]["link_fonte"].endswith("codigo=999")


def test_pdf_gerado_com_fonte_demo_e_real(monkeypatch, tmp_path):
    candidato_base = {
        "id": 1,
        "nome_urna": "Teste",
        "cargo": "Vereador",
        "uf": "SP",
        "origem_dados": "real",
        "fonte_dados": "TSE oficial",
    }

    monkeypatch.setattr("reports.pdf_generator.OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr("reports.pdf_generator.buscar_candidato", lambda candidato_id: candidato_base)
    monkeypatch.setattr("reports.pdf_generator.gerar_resumo_estrategico", lambda candidato_id, periodo: "Resumo teste")
    monkeypatch.setattr("reports.pdf_generator.gerar_alertas", lambda candidato_id: {})
    monkeypatch.setattr("reports.pdf_generator.gerar_linha_do_tempo", lambda candidato_id: pd.DataFrame())
    monkeypatch.setattr("reports.pdf_generator.ranking_municipios_fortes", lambda candidato_id, ano: pd.DataFrame({"municipio": ["Sao Paulo"], "votos": [100]}))
    monkeypatch.setattr("reports.pdf_generator.ranking_municipios_queda", lambda candidato_id, inicio, fim: pd.DataFrame({"municipio": ["Osasco"], "variacao_absoluta": [-10], "variacao_percentual": [-5.0]}))
    monkeypatch.setattr("reports.pdf_generator.ranking_municipios_oportunidade", lambda candidato_id, ano: pd.DataFrame({"municipio": ["Guarulhos"], "votos": [50], "potencial_comunicacao": ["oportunidade"]}))
    monkeypatch.setattr("reports.pdf_generator.gerar_resumo_emendas", lambda candidato_id: {"total_pago": 0, "total_empenhado": 0, "municipios_beneficiados": []})
    monkeypatch.setattr("reports.pdf_generator.calcular_esforco_resultado", lambda candidato_id, inicio, fim: pd.DataFrame({"municipio": ["Sao Paulo"], "valor_total_pago": [1000], "variacao_percentual": [10.0], "classificacao": ["Baixo esforco / Alto resultado"]}))
    monkeypatch.setattr("reports.pdf_generator.gerar_plano_30_60_90", lambda candidato, a, b: {
        "objetivo_geral": "Objetivo",
        "temas_prioritarios": ["Tema"],
        "canais_recomendados": ["Instagram"],
        "plano_30_dias": "30",
        "plano_60_dias": "60",
        "plano_90_dias": "90",
        "compliance_checklist": {
            "existe_pedido_explicito_de_voto": False,
            "existe_ataque_pessoal": False,
            "existe_promessa_exagerada": False,
            "existem_dados_sem_fonte": False,
            "existe_risco_de_impulsionamento_irregular": False,
            "existe_uso_de_ia_que_precisa_ser_identificado": False,
            "classificacao_geral": "baixo risco",
            "recomenda_revisao_juridica": False,
        },
    })

    caminho_real = gerar_pdf_relatorio(1, 2020, 2024)
    assert Path(caminho_real).exists()
    assert Path(caminho_real).stat().st_size > 0

    candidato_base["origem_dados"] = "demo"
    candidato_base["fonte_dados"] = "Dados de demonstracao do MVP"
    caminho_demo = gerar_pdf_relatorio(1, 2020, 2024)
    assert Path(caminho_demo).exists()
