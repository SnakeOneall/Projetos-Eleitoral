"""
Radar Eleitoral IA - ETL offline: votos nas comissões da ALESP.

O arquivo oficial comissoes_permanentes_votacoes.xml tem ~64 MB (226 mil
votos desde 2005) — pesado demais para o app consultar ao vivo. Este
script baixa os arquivos oficiais, cruza votos + reuniões (data) +
comissões (sigla/nome) e gera um arquivo compacto que o Painel do
Eleitor lê instantaneamente:

    data/processed/alesp_votacoes_comissoes.csv.gz  (~2-4 MB)

Uso (rodar de tempos em tempos para atualizar; o arquivo gerado deve ser
commitado no repositório para o app publicado usar):

    .\\.venv\\Scripts\\python.exe scripts\\etl_alesp_votacoes.py

Fontes oficiais (Dados Abertos ALESP):
  https://www.al.sp.gov.br/repositorioDados/processo_legislativo/
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

BASE_PROCESSO = "https://www.al.sp.gov.br/repositorioDados/processo_legislativo"
RAW_DIR = BASE_DIR / "data" / "alesp_raw"
OUT_DIR = BASE_DIR / "data" / "processed"
SAIDA = OUT_DIR / "alesp_votacoes_comissoes.csv.gz"

TIMEOUT = 300


def _baixar(nome_arquivo: str, forcar: bool = False) -> Path:
    """Baixa um arquivo do repositório da ALESP para data/alesp_raw."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    destino = RAW_DIR / nome_arquivo
    if destino.exists() and not forcar:
        print(f"[ETL] Usando cache local de {nome_arquivo}")
        return destino
    url = f"{BASE_PROCESSO}/{nome_arquivo}"
    print(f"[ETL] Baixando {url} (pode demorar)...")
    with requests.get(url, timeout=TIMEOUT, stream=True) as resposta:
        resposta.raise_for_status()
        with open(destino, "wb") as f:
            for pedaco in resposta.iter_content(chunk_size=1 << 20):
                f.write(pedaco)
    print(f"[ETL] Salvo em {destino} ({destino.stat().st_size / 1048576:.1f} MB)")
    return destino


def _xml_para_registros(caminho: Path, campo_chave: str) -> list:
    """Percorre o XML em streaming (iterparse) para não estourar a memória.

    Considera 'registro' todo elemento que contenha um filho `campo_chave`.
    """
    registros = []
    for _, elemento in ET.iterparse(str(caminho), events=("end",)):
        filhos = {filho.tag: (filho.text or "").strip() for filho in elemento}
        if campo_chave in filhos:
            registros.append(filhos)
            elemento.clear()
    return registros


def executar(forcar_download: bool = False) -> Path:
    # 1. Votos (arquivo grande)
    arq_votos = _baixar("comissoes_permanentes_votacoes.xml", forcar_download)
    votos = _xml_para_registros(arq_votos, "TipoVoto")
    df_votos = pd.DataFrame(votos)
    print(f"[ETL] {len(df_votos)} votos carregados.")

    # 2. Reuniões (para obter a data de cada reunião)
    arq_reunioes = _baixar("comissoes_permanentes_reunioes.xml", forcar_download)
    reunioes = _xml_para_registros(arq_reunioes, "IdReuniao")
    df_reunioes = pd.DataFrame(reunioes)[["IdReuniao", "Data", "NrLegislatura"]]
    df_reunioes = df_reunioes.drop_duplicates("IdReuniao")
    print(f"[ETL] {len(df_reunioes)} reuniões carregadas.")

    # 3. Comissões (sigla e nome)
    arq_comissoes = _baixar("comissoes.xml", forcar_download)
    comissoes = _xml_para_registros(arq_comissoes, "IdComissao")
    df_comissoes = pd.DataFrame(comissoes)[["IdComissao", "SiglaComissao", "NomeComissao"]]
    df_comissoes = df_comissoes.drop_duplicates("IdComissao")
    print(f"[ETL] {len(df_comissoes)} comissões carregadas.")

    # 4. Cruzamentos
    df = df_votos.merge(df_reunioes, on="IdReuniao", how="left")
    df = df.merge(df_comissoes, on="IdComissao", how="left")

    df["data_reuniao"] = df["Data"].astype(str).str.slice(0, 10)
    df["ano"] = pd.to_numeric(df["data_reuniao"].str.slice(0, 4), errors="coerce")

    compacto = pd.DataFrame({
        "id_deputado": df.get("IdDeputado", ""),
        "deputado": df.get("Deputado", ""),
        "data_reuniao": df["data_reuniao"],
        "ano": df["ano"],
        "sigla_comissao": df.get("SiglaComissao", ""),
        "comissao": df.get("NomeComissao", ""),
        "id_documento": df.get("IdDocumento", ""),
        "voto": df.get("Voto", ""),
        "tipo_voto": df.get("TipoVoto", ""),
    })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    compacto.to_csv(SAIDA, index=False, compression="gzip")
    tamanho_mb = SAIDA.stat().st_size / 1048576
    print(f"[ETL] OK: {len(compacto)} votos gravados em {SAIDA} ({tamanho_mb:.1f} MB)")
    print("[ETL] Lembre-se de commitar o arquivo gerado (git add data/processed).")
    return SAIDA


if __name__ == "__main__":
    executar(forcar_download="--forcar" in sys.argv)
