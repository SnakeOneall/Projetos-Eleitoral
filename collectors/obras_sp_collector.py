"""
Radar Eleitoral IA - Conector de Obras Estaduais de SP.

RESULTADO DA INVESTIGAÇÃO (jul/2026) — Cenário ★★★★★: API oficial CKAN.

Fonte: Portal de Dados Abertos do Estado de SP (https://dadosabertos.sp.gov.br),
plataforma CKAN com API REST pública e sem autenticação.

Endpoints CKAN usados:
  - GET /api/3/action/package_search?q=obras&rows=50   -> lista datasets de obras
  - GET /api/3/action/package_show?id=obras-der-sp      -> arquivos de um dataset
  - Download direto do XLSX indicado no recurso.

Dataset principal: "Obras - DER/SP" (Departamento de Estradas de Rodagem).
Arquivo XLSX (aba GERAL) com 694 obras (verificado jul/2026). Colunas:
  Nome-Projeto-Obra, Descrição do projeto, Nome do programa, Secretaria,
  Responsável, Categoria, Tipo de intervenção, Modal, Valor Atual (R$),
  Lista de Municípios, Lista Região Administrativa, Status,
  Extensão (quilômetro), Data de Início, Data de Término,
  Data Efetiva da Entrega, Código da Rodovia, Quilômetro inicial/final,
  Empregos Gerados (Direto/Indireto/Total).

Observação importante: são obras do EXECUTIVO estadual (DER), não têm autoria
parlamentar. No Radar do Eleitor entram como seção "Obras no seu município".

COMPLIANCE (Resolução TSE 23.755/2026): dados factuais, sem ranking.
"""

import logging
import sys
import unicodedata
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CKAN = "https://dadosabertos.sp.gov.br/api/3/action"
DATASET_DER = "obras-der-sp"
TIMEOUT = 120
HEADERS = {"User-Agent": "Mozilla/5.0 RadarEleitoral/1.0"}


def _criar_logger() -> logging.Logger:
    log = logging.getLogger("radar_eleitoral.obras_sp")
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("[OBRAS-SP] %(message)s"))
        log.addHandler(h)
    log.setLevel(logging.INFO)
    log.propagate = False
    return log


logger = _criar_logger()


def _sem_acento(texto: str) -> str:
    texto = str(texto or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def normalizar_nome_municipio(municipio: str) -> str:
    """Devolve o nome do município no formato oficial de SP (MAIÚSCULO, com
    acento), a partir do que o usuário digitou.

    Necessário porque o filtro de emendas do Portal da Transparência SP só
    aceita o valor EXATO (ex.: 'MARÍLIA'); 'marilia' ou 'Marília' retornam 0.
    Usa a lista de obras (que traz municípios acentuados) como dicionário.
    """
    alvo = _sem_acento(municipio)
    if not alvo:
        return municipio.upper().strip()
    try:
        df = baixar_obras_der()
        vistos = set()
        for lista in df.get("municipios", pd.Series(dtype=str)).dropna():
            for nome in str(lista).replace(";", ",").split(","):
                nome = nome.strip()
                if nome and _sem_acento(nome) == alvo:
                    return nome.upper()
                vistos.add(nome)
    except Exception:
        pass
    return municipio.upper().strip()


def listar_datasets_obras() -> pd.DataFrame:
    """Lista os datasets de obras disponíveis no CKAN do Estado."""
    r = requests.get(f"{CKAN}/package_search", params={"q": "obras", "rows": 50},
                     headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    resultados = r.json().get("result", {}).get("results", [])
    registros = [{
        "titulo": d.get("title"),
        "id": d.get("name"),
        "orgao": (d.get("organization") or {}).get("title"),
        "formatos": ",".join(sorted({rec.get("format", "") for rec in d.get("resources", [])})),
    } for d in resultados]
    return pd.DataFrame(registros)


def _url_xlsx_do_dataset(dataset_id: str) -> str | None:
    r = requests.get(f"{CKAN}/package_show", params={"id": dataset_id},
                     headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    recursos = r.json().get("result", {}).get("resources", [])
    for rec in recursos:
        if str(rec.get("format", "")).upper() == "XLSX" and rec.get("url"):
            return rec["url"]
    return None


def baixar_obras_der(dataset_id: str = DATASET_DER) -> pd.DataFrame:
    """Baixa e normaliza a planilha oficial de obras do DER/SP.

    Retorna DataFrame com colunas normalizadas, incluindo 'municipios' (lista
    de municípios em texto) e 'valor' (numérico).
    """
    url = _url_xlsx_do_dataset(dataset_id)
    if not url:
        logger.info(f"Dataset {dataset_id} não tem XLSX disponível.")
        return pd.DataFrame()

    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    df = pd.read_excel(BytesIO(resp.content), sheet_name="GERAL")

    renome = {
        "Nome-Projeto-Obra": "obra",
        "Descrição do projeto": "descricao",
        "Nome do programa": "programa",
        "Secretaria": "secretaria",
        "Categoria": "categoria",
        "Tipo de intervenção": "tipo_intervencao",
        "Valor Atual (R$)": "valor",
        "Lista de Municípios": "municipios",
        "Lista Região Administrativa": "regiao",
        "Status": "status",
        "Extensão (quilômetro)": "extensao_km",
        "Data de Início": "data_inicio",
        "Data de Término": "data_termino",
        "Data Efetiva da Entrega": "data_entrega",
        "Empregos Gerados - Total": "empregos_total",
    }
    df = df.rename(columns={k: v for k, v in renome.items() if k in df.columns})
    if "valor" in df.columns:
        df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)
    logger.info(f"{len(df)} obra(s) do DER/SP carregada(s).")
    return df


def buscar_obras_por_municipio(municipio: str, dataset_id: str = DATASET_DER) -> pd.DataFrame:
    """Filtra as obras que incluem o município (comparação sem acento/caixa).

    O campo 'Lista de Municípios' pode conter vários municípios por obra
    (obras rodoviárias cruzam cidades), então a busca é por conteúdo.
    """
    df = baixar_obras_der(dataset_id)
    if df.empty or "municipios" not in df.columns:
        return df
    alvo = _sem_acento(municipio)
    mask = df["municipios"].map(lambda m: alvo in _sem_acento(m))
    recorte = df[mask].reset_index(drop=True)
    logger.info(f"{len(recorte)} obra(s) em {municipio}.")
    return recorte


if __name__ == "__main__":
    print(listar_datasets_obras().head(10).to_string())
    obras = buscar_obras_por_municipio("Marília")
    cols = [c for c in ["obra", "categoria", "status", "valor", "municipios"] if c in obras.columns]
    print(obras[cols].head().to_string())
    if not obras.empty:
        print(f"\nTotal investido nas obras de Marília: R$ {obras['valor'].sum():,.2f}")
