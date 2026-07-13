from pathlib import Path

import pandas as pd

from collectors.emendas_collector import (
    buscar_emendas_portal_transparencia,
    normalizar_emendas,
)
from collectors.tse_collector import buscar_candidato_tse
from compliance.electoral_compliance import (
    avaliar_risco_texto,
    detectar_ataque_pessoal,
    detectar_impulsionamento_negativo,
    detectar_pedido_explicito_voto,
)
from reports.pdf_generator import gerar_pdf_relatorio
from ui_components import render_kpi_cards, render_quadrant_chart


def test_app_compila_sem_iniciar_servidor_streamlit():
    codigo = Path("app.py").read_text(encoding="utf-8")
    compile(codigo, "app.py", "exec")


def test_ui_components_importa_e_componentes_aceitam_dados_vazios():
    metricas = render_kpi_cards({})
    fig = render_quadrant_chart(pd.DataFrame())

    assert metricas["votos_totais"] == "0"
    assert metricas["indice_retorno"] == "N/D"
    assert len(fig.layout.annotations) == 1


def test_tse_falha_real_nao_usa_demo_silenciosamente(monkeypatch):
    def falhar_download(ano):
        raise FileNotFoundError(f"sem arquivo para {ano}")

    monkeypatch.setattr("collectors.tse_collector.baixar_arquivo_tse", falhar_download)

    df = buscar_candidato_tse(
        nome_urna="Teste",
        uf="SP",
        cargo="Vereador",
        ano=2024,
        usar_demo_quando_falhar=False,
    )

    assert df.empty
    assert df.attrs["anos_consultados"] == [2024]
    assert df.attrs["avisos_tse"]
    assert df.attrs["usou_demo"] is False


def test_tse_demo_explicitamente_sinalizado_quando_habilitado(monkeypatch):
    def falhar_download(ano):
        raise FileNotFoundError(f"sem arquivo para {ano}")

    monkeypatch.setattr("collectors.tse_collector.baixar_arquivo_tse", falhar_download)

    df = buscar_candidato_tse(
        nome_urna="Zé Pereira",
        uf="SP",
        cargo="Vereador",
        ano=2024,
        usar_demo_quando_falhar=True,
    )

    assert not df.empty
    assert set(df["origem_dados"]) == {"demo"}
    assert df["fonte_dados"].str.contains("demonstração", case=False).all()
    assert df.attrs["usou_demo"] is True


def test_conversao_monetaria_preserva_float_e_formato_brasileiro():
    df = normalizar_emendas(pd.DataFrame({
        "valor_empenhado": ["10.000,00", 10000.0, "R$ 1.234,56"],
        "valor_liquidado": ["500,25", 500.25, "1,25"],
        "valor_pago": ["0", 10000.0, "2.000,10"],
    }))

    assert df["valor_empenhado"].tolist() == [10000.0, 10000.0, 1234.56]
    assert df["valor_liquidado"].tolist() == [500.25, 500.25, 1.25]
    assert df["valor_pago"].tolist() == [0.0, 10000.0, 2000.10]


def test_portal_sem_chave_retorna_status_amigavel(monkeypatch):
    monkeypatch.setattr("collectors.emendas_collector._carregar_token_portal", lambda token=None: None)

    df = buscar_emendas_portal_transparencia(ano=2024, uf="SP")

    assert df.empty
    assert df.attrs["status_consulta"] == "sem_chave_api"


def test_pdf_fallback_minimo_valido(monkeypatch, tmp_path):
    candidato = {
        "id": 1,
        "nome_urna": "Teste",
        "cargo": "Vereador",
        "uf": "SP",
        "origem_dados": "demo",
        "fonte_dados": "Dados de demonstração do MVP",
    }

    monkeypatch.setattr("reports.pdf_generator.REPORTLAB_AVAILABLE", False)
    monkeypatch.setattr("reports.pdf_generator.OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr("reports.pdf_generator.buscar_candidato", lambda candidato_id: candidato)
    monkeypatch.setattr("reports.pdf_generator.gerar_resumo_estrategico", lambda candidato_id, periodo: "Resumo teste")
    monkeypatch.setattr("reports.pdf_generator.gerar_alertas", lambda candidato_id: {})
    monkeypatch.setattr("reports.pdf_generator.gerar_plano_30_60_90", lambda candidato, a, b: {
        "plano_30_dias": "30 dias",
        "plano_60_dias": "60 dias",
        "plano_90_dias": "90 dias",
        "compliance_checklist": {"classificacao_geral": "baixo risco"},
    })

    caminho = Path(gerar_pdf_relatorio(1, 2020, 2024))

    assert caminho.exists()
    assert caminho.read_bytes().startswith(b"%PDF-")


def test_pdf_minimo_indica_fonte_dos_dados(monkeypatch, tmp_path):
    candidato = {
        "id": 1,
        "nome_urna": "Teste Fonte",
        "cargo": "Vereador",
        "uf": "SP",
        "origem_dados": "real",
        "fonte_dados": "TSE oficial",
    }

    monkeypatch.setattr("reports.pdf_generator.REPORTLAB_AVAILABLE", False)
    monkeypatch.setattr("reports.pdf_generator.OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr("reports.pdf_generator.buscar_candidato", lambda candidato_id: candidato)
    monkeypatch.setattr("reports.pdf_generator.gerar_resumo_estrategico", lambda candidato_id, periodo: "Resumo teste")
    monkeypatch.setattr("reports.pdf_generator.gerar_alertas", lambda candidato_id: {})
    monkeypatch.setattr("reports.pdf_generator.gerar_resumo_emendas", lambda candidato_id: {})
    monkeypatch.setattr("reports.pdf_generator.calcular_esforco_resultado", lambda candidato_id, inicio, fim: pd.DataFrame())
    monkeypatch.setattr("reports.pdf_generator.ranking_municipios_oportunidade", lambda candidato_id, ano: pd.DataFrame())
    monkeypatch.setattr("reports.pdf_generator.gerar_plano_30_60_90", lambda candidato, a, b: {
        "plano_30_dias": "30 dias",
        "plano_60_dias": "60 dias",
        "plano_90_dias": "90 dias",
        "compliance_checklist": {"classificacao_geral": "baixo risco"},
    })
    monkeypatch.setattr("reports.pdf_generator.gerar_linha_do_tempo", lambda candidato_id: pd.DataFrame())
    monkeypatch.setattr("reports.pdf_generator.ranking_municipios_fortes", lambda candidato_id, ano: pd.DataFrame())
    monkeypatch.setattr("reports.pdf_generator.ranking_municipios_queda", lambda candidato_id, inicio, fim: pd.DataFrame())

    caminho = Path(gerar_pdf_relatorio(1, 2020, 2024))
    conteudo = caminho.read_bytes()

    assert b"TSE oficial" in conteudo
    assert b"Dados reais" in conteudo


def test_compliance_detecta_riscos_principais():
    texto = "Vote em mim e vamos desmascarar o adversário corrupto."

    assert detectar_pedido_explicito_voto(texto) is True
    assert detectar_ataque_pessoal(texto) is True
    assert detectar_impulsionamento_negativo(texto) is True
    assert avaliar_risco_texto(texto) == "alto risco"
