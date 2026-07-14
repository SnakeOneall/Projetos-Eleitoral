"""
Radar Eleitoral IA - Conector de Emendas Estaduais SP (Portal da
Transparência do Estado de São Paulo).

RESULTADO DA INVESTIGAÇÃO TÉCNICA (jul/2026) — Cenário A: existe API HTTP
reutilizável, sem necessidade de scraping de HTML ou navegador.

Endpoints descobertos (mesmos usados pelo frontend oficial):

  1. POST https://www.transparencia.sp.gov.br/EmendasParlamentares/Buscar
     - Content-Type: application/json (form-urlencoded retorna HTTP 415)
     - Payload: {"orgao": "", "origemRecurso": "", "numeroEmenda": "",
                 "autoria": "", "partido": "", "beneficiario": "",
                 "tipoEmenda": "", "localizacaoGasto": "",
                 "anoReferencia": "2025", "pagina": 1}
       (strings vazias = "Todos"; filtros de texto são por conteúdo parcial)
     - Resposta JSON: {items[], page, pageSize(=20), totalItems,
                       totalPages, hasNext, ultimaAtualizacao, ...}
     - Campos de cada item: seqID, orgaoEntidadeExecutora, origemRecursos,
       numeroEmenda, autoria, partidoPolitico, numeroInstrumentoJuridico,
       beneficiario, objeto, tipoEmenda, tipoDespesa, funcaoGoverno,
       localizacaoGasto, valorEmpenhado, valorLiquidado, valorPago
     - Paginação fixa em 20 itens/página (ex.: 2025 = 32.421 emendas,
       1.622 páginas).

  2. POST https://www.transparencia.sp.gov.br/EmendasParlamentares/ExportarCsv
     - Mesmo payload JSON; retorna o CSV COMPLETO do filtro em uma única
       resposta (sem paginação) — ideal para ETL.
     - CSV: separador ';', aspas duplas, encoding latin-1/windows-1252.

  3. Consulta equivalente de emendas CONCEDIDAS em
     /EmendasParlamentares/Concedidas (mesma família de endpoints).

Autenticação: nenhuma chave/token. Recomenda-se abrir a página de consulta
uma vez na sessão HTTP (cookies de sessão) antes dos POSTs, e enviar um
User-Agent de navegador.

Cobertura: anos de referência a partir de 2022 (anteriores só em PDF).

COMPLIANCE (Resolução TSE 23.755/2026): dados exibidos de forma factual,
sem ranking, nota ou recomendação de candidatos.
"""

import logging
import sys
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "https://www.transparencia.sp.gov.br"
PAGINA_CONSULTA = f"{BASE}/EmendasParlamentares/Realizadas"
API_BUSCAR = f"{BASE}/EmendasParlamentares/Buscar"
API_CSV = f"{BASE}/EmendasParlamentares/ExportarCsv"
TIMEOUT = 120

HEADERS_NAVEGADOR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RadarEleitoral/1.0",
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
}


def _criar_logger() -> logging.Logger:
    logger_sp = logging.getLogger("radar_eleitoral.sp_transparencia")
    if not logger_sp.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[SP-TRANSP] %(message)s"))
        logger_sp.addHandler(handler)
    logger_sp.setLevel(logging.INFO)
    logger_sp.propagate = False
    return logger_sp


logger = _criar_logger()


def _montar_payload(
    autoria: str = "",
    ano_referencia: str = "",
    partido: str = "",
    beneficiario: str = "",
    localizacao_gasto: str = "",
    tipo_emenda: str = "",
    orgao: str = "",
    origem_recurso: str = "",
    numero_emenda: str = "",
    pagina: int = 1,
) -> dict:
    return {
        "orgao": orgao or "",
        "origemRecurso": origem_recurso or "",
        "numeroEmenda": numero_emenda or "",
        "autoria": autoria or "",
        "partido": partido or "",
        "beneficiario": beneficiario or "",
        "tipoEmenda": tipo_emenda or "",
        "localizacaoGasto": localizacao_gasto or "",
        "anoReferencia": str(ano_referencia or ""),
        "pagina": int(pagina),
    }


def _nova_sessao() -> requests.Session:
    """Sessão HTTP com cookies do portal (basta um GET na página de consulta)."""
    sessao = requests.Session()
    sessao.headers.update(HEADERS_NAVEGADOR)
    sessao.get(PAGINA_CONSULTA, timeout=TIMEOUT)
    return sessao


def buscar_emendas_sp_json(
    autoria: str = "",
    ano_referencia: str = "",
    max_paginas: int = 200,
    sessao: requests.Session = None,
    **filtros,
) -> pd.DataFrame:
    """Consulta paginada via endpoint JSON (20 itens/página).

    Para volumes grandes, prefira baixar_emendas_sp_csv (uma requisição).
    """
    sessao = sessao or _nova_sessao()
    registros = []
    pagina = 1
    while pagina <= max_paginas:
        payload = _montar_payload(autoria=autoria, ano_referencia=ano_referencia,
                                  pagina=pagina, **filtros)
        resposta = sessao.post(API_BUSCAR, json=payload, timeout=TIMEOUT)
        resposta.raise_for_status()
        dados = resposta.json()
        registros.extend(dados.get("items") or [])
        if not dados.get("hasNext"):
            break
        pagina += 1
    df = pd.DataFrame(registros)
    logger.info(f"{len(df)} emenda(s) estaduais via JSON (autoria='{autoria}', ano='{ano_referencia}').")
    return df


def baixar_emendas_sp_csv(
    autoria: str = "",
    ano_referencia: str = "",
    sessao: requests.Session = None,
    **filtros,
) -> pd.DataFrame:
    """Baixa o CSV oficial completo do filtro (uma única requisição).

    Retorna DataFrame com colunas normalizadas e valores numéricos.
    """
    sessao = sessao or _nova_sessao()
    payload = _montar_payload(autoria=autoria, ano_referencia=ano_referencia, **filtros)
    resposta = sessao.post(API_CSV, json=payload, timeout=TIMEOUT)
    resposta.raise_for_status()

    texto = resposta.content.decode("latin-1", errors="replace")
    if not texto.strip():
        return pd.DataFrame()

    df = pd.read_csv(StringIO(texto), sep=";", quotechar='"')
    df.columns = [c.strip().upper() for c in df.columns]

    # ATENÇÃO: o portal entrega os valores multiplicados por 100 (centavos
    # formatados como reais). Verificado empiricamente em jul/2026: a soma
    # de 2025 sem a correção daria R$ 179 bi — o orçamento real de emendas
    # de SP é ~R$ 3,3 bi/ano. Por isso a divisão por 100 abaixo.
    for col in ("VALOR EMPENHADO", "VALOR LIQUIDADO", "VALOR PAGO"):
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace(".", "", regex=False)
                .str.replace(",", ".", regex=False)
            )
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0) / 100.0

    logger.info(f"{len(df)} emenda(s) estaduais via CSV (autoria='{autoria}', ano='{ano_referencia}').")
    return df


def buscar_emendas_estaduais_por_autor(nome_autor: str, anos: list) -> pd.DataFrame:
    """Emendas estaduais de um deputado nos anos pedidos (fonte: CSV oficial).

    O filtro de autoria do portal é por conteúdo parcial — o nome
    parlamentar completo da ALESP funciona diretamente.
    """
    sessao = _nova_sessao()
    partes = []
    for ano in anos:
        if int(ano) < 2022:
            continue  # portal só cobre 2022+ em formato estruturado
        try:
            df = baixar_emendas_sp_csv(autoria=nome_autor, ano_referencia=str(ano), sessao=sessao)
            if not df.empty:
                df["ANO REFERENCIA"] = int(ano)
                partes.append(df)
        except Exception as exc:
            logger.info(f"Falha ao consultar {ano}: {exc}")
    if not partes:
        return pd.DataFrame()
    return pd.concat(partes, ignore_index=True)


if __name__ == "__main__":
    # Teste manual rápido
    df = buscar_emendas_estaduais_por_autor("Danilo Balas", [2024, 2025])
    print(df.head())
    if not df.empty:
        print(f"\n[TESTE] {len(df)} emendas | Pago: R$ {df['VALOR PAGO'].sum():,.2f}")
