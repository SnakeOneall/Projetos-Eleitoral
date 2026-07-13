"""
Radar Eleitoral IA - Coletor de dados eleitorais do TSE.

Responsável por baixar, extrair, carregar e filtrar os arquivos
públicos de resultados eleitorais do TSE. Como os links oficiais
mudam de formato, as URLs ficam centralizadas em config/tse_sources.py
e nada aqui depende de um link fixo "hardcoded".

Quando os arquivos reais ainda não estiverem configurados (url_zip
vazia), as funções de carregamento usam dados de teste para que o
restante do pipeline (análise, dashboard) continue funcionável.
"""

import logging
import os
import re
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

from config.tse_sources import (
    COLUNAS_CHAVE_DIAGNOSTICO,
    COLUNAS_PADRONIZADAS,
    TSE_DOWNLOAD_DIR,
    TSE_ENCODINGS_TENTATIVAS,
    anos_disponiveis,
    get_fonte,
    ultimas_n_eleicoes,
)
from database.init_db import get_connection


def _criar_logger_tse() -> logging.Logger:
    logger_tse = logging.getLogger("radar_eleitoral.tse")
    if not logger_tse.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[TSE] %(message)s"))
        logger_tse.addHandler(handler)
    logger_tse.setLevel(logging.INFO)
    logger_tse.propagate = False
    return logger_tse


logger = _criar_logger_tse()

# User-Agent de navegador real. Alguns firewalls/antivírus com inspeção de
# tráfego HTTPS tratam requisições de ferramentas de linha de comando
# (curl, python-requests) de forma diferente de requisições de navegador,
# o que pode ser parte do motivo de quedas de conexão em downloads grandes.
USER_AGENT_NAVEGADOR = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _formatar_tamanho(num_bytes: int) -> str:
    """Formata um tamanho em bytes de forma legível (B/KB/MB/GB)."""
    valor = float(num_bytes)
    for unidade in ("B", "KB", "MB", "GB"):
        if valor < 1024:
            return f"{valor:.1f}{unidade}"
        valor /= 1024
    return f"{valor:.1f}TB"


# ----------------------------------------------------------------------
# Download e extração
# ----------------------------------------------------------------------

def download_file_resumable(
    url: str,
    output_path: str,
    max_retries: int = 5,
    chunk_size: int = 1024 * 1024,
    timeout: int = 60,
) -> str:
    """Faz o download resiliente de um arquivo grande, com retomada e retry.

    Criada para contornar um sintoma comum em redes corporativas/Windows
    onde a conexão HTTPS cai no meio de downloads grandes (ex: erros como
    "[SSL: RECORD_LAYER_FAILURE]" ou "schannel SEC_E_DECRYPT_FAILURE"),
    tipicamente causado por antivírus ou firewall fazendo inspeção de
    tráfego — sem afetar downloads feitos pelo navegador.

    Estratégia:
      1. Se `output_path` já existe e é um ZIP válido, não baixa de novo.
      2. Download em streaming, em chunks (não carrega tudo na memória).
      3. Se já existir um arquivo parcial, tenta retomar de onde parou
         usando o header HTTP "Range".
      4. Se o servidor não suportar retomada (devolver 200 em vez de 206),
         reinicia o download do zero.
      5. Em caso de falha de rede, mantém o arquivo parcial no disco e
         tenta novamente — só desiste após `max_retries` tentativas.
      6. Ao final de cada tentativa concluída, valida o ZIP com
         `zipfile.is_zipfile()`. Só retorna sucesso se a validação passar.

    Parâmetros:
        url: URL do arquivo a baixar.
        output_path: caminho local de destino (ex: "data/raw/tse/tse_2024.zip").
        max_retries: número máximo de tentativas (padrão 5).
        chunk_size: tamanho do chunk de streaming, em bytes (padrão 1MB).
        timeout: timeout de conexão/leitura por requisição, em segundos.

    Retorna `output_path` em caso de sucesso.
    Levanta ConnectionError se todas as tentativas falharem (o arquivo
    parcial é preservado em disco para uma tentativa futura).
    """
    pasta = os.path.dirname(output_path)
    if pasta:
        os.makedirs(pasta, exist_ok=True)

    if os.path.exists(output_path) and zipfile.is_zipfile(output_path):
        logger.debug(
            f"Arquivo já existe e é um ZIP válido: {output_path} "
            f"({_formatar_tamanho(os.path.getsize(output_path))}). Download pulado."
        )
        return output_path

    ultimo_erro = None

    for tentativa in range(1, max_retries + 1):
        bytes_existentes = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        headers = {"User-Agent": USER_AGENT_NAVEGADOR, "Connection": "close"}
        modo_arquivo = "wb"

        if bytes_existentes > 0:
            headers["Range"] = f"bytes={bytes_existentes}-"
            modo_arquivo = "ab"
            logger.info(
                f"Tentativa {tentativa}/{max_retries}: retomando download de '{url}' "
                f"a partir de {_formatar_tamanho(bytes_existentes)} já baixados."
            )
        else:
            logger.info(f"Tentativa {tentativa}/{max_retries}: iniciando download de '{url}'.")

        try:
            with requests.get(url, headers=headers, stream=True, timeout=timeout) as resposta:
                if bytes_existentes > 0 and resposta.status_code == 200:
                    # Servidor ignorou o Range e está enviando o arquivo do zero.
                    logger.info("Servidor não suportou retomada (Range); reiniciando download do zero.")
                    bytes_existentes = 0
                    modo_arquivo = "wb"
                elif resposta.status_code == 416:
                    # Range não satisfazível: geralmente significa que já temos tudo.
                    logger.info("Servidor reportou range inválido (416); validando arquivo já existente.")
                    if zipfile.is_zipfile(output_path):
                        logger.info("Validação do ZIP: OK. Download considerado completo.")
                        return output_path
                    logger.info("Validação do ZIP: FALHOU. Descartando arquivo parcial e reiniciando.")
                    os.remove(output_path)
                    continue

                resposta.raise_for_status()

                content_length = resposta.headers.get("Content-Length")
                if content_length is not None:
                    content_length = int(content_length)
                    tamanho_total = (
                        content_length + bytes_existentes if resposta.status_code == 206 else content_length
                    )
                else:
                    tamanho_total = None

                baixado = bytes_existentes
                ultimo_marco_logado = baixado

                with open(output_path, modo_arquivo) as f:
                    for chunk in resposta.iter_content(chunk_size=chunk_size):
                        if not chunk:
                            continue
                        f.write(chunk)
                        baixado += len(chunk)

                        # Loga a cada ~5MB (ou a cada novo múltiplo de 5% se o
                        # tamanho total for conhecido), para não inundar o log.
                        if baixado - ultimo_marco_logado >= 5 * 1024 * 1024:
                            if tamanho_total:
                                pct = int(baixado * 100 / tamanho_total)
                                logger.info(
                                    f"Tentativa {tentativa}/{max_retries}: "
                                    f"{_formatar_tamanho(baixado)} / {_formatar_tamanho(tamanho_total)} "
                                    f"(~{pct}%)"
                                )
                            else:
                                logger.info(
                                    f"Tentativa {tentativa}/{max_retries}: "
                                    f"{_formatar_tamanho(baixado)} baixados (tamanho total desconhecido)."
                                )
                            ultimo_marco_logado = baixado

            # Streaming concluído sem exceção de rede nesta tentativa. Valida o ZIP.
            if zipfile.is_zipfile(output_path):
                logger.info(
                    f"Validação do ZIP: OK ({_formatar_tamanho(os.path.getsize(output_path))}). "
                    f"Download concluído em {tentativa} tentativa(s)."
                )
                return output_path

            ultimo_erro = ValueError(
                "Arquivo baixado não é um ZIP válido (zipfile.is_zipfile retornou False)."
            )
            logger.info(
                f"Validação do ZIP: FALHOU nesta tentativa. {ultimo_erro} "
                f"Arquivo parcial ({_formatar_tamanho(os.path.getsize(output_path))}) mantido para retomada."
            )

        except (requests.exceptions.RequestException, OSError) as e:
            ultimo_erro = e
            tamanho_parcial = os.path.getsize(output_path) if os.path.exists(output_path) else 0
            logger.info(
                f"Tentativa {tentativa}/{max_retries} falhou: {e}. "
                f"Arquivo parcial mantido com {_formatar_tamanho(tamanho_parcial)} para retomada na próxima tentativa."
            )

        if tentativa < max_retries:
            espera = min(3 * tentativa, 15)
            logger.info(f"Aguardando {espera}s antes da próxima tentativa...")
            time.sleep(espera)

    raise ConnectionError(
        f"Falha ao baixar '{url}' após {max_retries} tentativas. Último erro: {ultimo_erro}. "
        f"O arquivo parcial foi preservado em '{output_path}' e a próxima chamada tentará retomar dele."
    )


def baixar_arquivo_tse(ano: int, destino: str = None) -> str:
    """Baixa (ou reaproveita) o arquivo ZIP de resultados do TSE para um ano configurado.

    Usa `download_file_resumable()` internamente: download em streaming,
    com retomada automática de downloads parciais e múltiplas tentativas,
    para lidar com redes que derrubam conexões HTTPS no meio de arquivos
    grandes (sintoma comum em antivírus/firewalls corporativos no Windows).

    Se um arquivo válido já existir localmente (baixado manualmente pelo
    navegador, por exemplo, e colocado em `data/raw/tse/tse_<ano>.zip`),
    o download é pulado completamente — mesmo que a URL não esteja
    configurada em config/tse_sources.py.

    Retorna o caminho local do arquivo.
    Levanta FileNotFoundError se a fonte não estiver configurada (url_zip
    vazia) e não houver arquivo local válido.
    Levanta ConnectionError se o download falhar após todas as tentativas
    (ver download_file_resumable) — ou seja, NUNCA cai silenciosamente
    para dados de teste sem ter tentado pelo menos `max_retries` vezes.
    """
    pasta_destino = destino or TSE_DOWNLOAD_DIR
    os.makedirs(pasta_destino, exist_ok=True)
    caminho_zip = os.path.join(pasta_destino, f"tse_{ano}.zip")

    if os.path.exists(caminho_zip) and zipfile.is_zipfile(caminho_zip):
        logger.info(f"Usando arquivo local já presente e válido: {caminho_zip} (download pulado).")
        return caminho_zip

    fonte = get_fonte(ano)
    if not fonte or not fonte.get("url_zip"):
        raise FileNotFoundError(
            f"URL do TSE não configurada para o ano {ano} e nenhum arquivo local válido "
            f"encontrado em {caminho_zip}. Edite config/tse_sources.py com o link oficial, "
            f"ou baixe manualmente pelo navegador e salve em {caminho_zip}."
        )

    return download_file_resumable(fonte["url_zip"], caminho_zip)


def extrair_zip(caminho_zip: str, destino: str = None) -> str:
    """Extrai um arquivo ZIP do TSE e retorna a pasta de destino."""
    pasta_destino = destino or os.path.splitext(caminho_zip)[0]
    os.makedirs(pasta_destino, exist_ok=True)

    with zipfile.ZipFile(caminho_zip, "r") as zf:
        zf.extractall(pasta_destino)

    logger.info(f"Arquivo extraído em: {pasta_destino}")
    return pasta_destino


def detectar_separador_encoding(caminho_csv: str) -> tuple:
    """Detecta automaticamente o encoding e o separador de um CSV do TSE.

    Tenta cada encoding em TSE_ENCODINGS_TENTATIVAS; para o primeiro que
    conseguir decodificar uma amostra do arquivo, usa csv.Sniffer para
    detectar o delimitador entre ';' e ','. Se o Sniffer falhar, usa uma
    heurística simples: conta ocorrências de ';' e ',' na amostra e
    escolhe a mais frequente.

    Retorna (separador, encoding).
    """
    import csv

    for encoding in TSE_ENCODINGS_TENTATIVAS:
        try:
            with open(caminho_csv, "r", encoding=encoding, errors="strict") as f:
                amostra = f.read(8192)
        except (UnicodeDecodeError, UnicodeError):
            continue

        try:
            dialeto = csv.Sniffer().sniff(amostra, delimiters=";,")
            return dialeto.delimiter, encoding
        except csv.Error:
            qtd_ponto_virgula = amostra.count(";")
            qtd_virgula = amostra.count(",")
            separador = ";" if qtd_ponto_virgula >= qtd_virgula else ","
            return separador, encoding

    # Nenhum encoding testado conseguiu decodificar; assume o par mais
    # comum nos arquivos do TSE e deixa o pd.read_csv levantar o erro real.
    return ";", "latin-1"


# Quando mais de uma coluna de origem mapeia para o mesmo nome interno
# (ex: NM_UE e NM_MUNICIPIO ambos -> 'municipio') E ambas aparecem juntas
# no mesmo arquivo (caso real confirmado nos pacotes de 2024 do TSE), esta
# ordem de prioridade decide qual delas "ganha" o nome normalizado. A(s)
# outra(s) ficam com o nome original — sem perda de dado, sem coluna
# duplicada.
PRIORIDADE_ORIGENS_POR_DESTINO = {
    "municipio": ["NM_MUNICIPIO", "NM_UE"],
}


def normalizar_colunas_tse(df: pd.DataFrame) -> pd.DataFrame:
    """Renomeia colunas oficiais do TSE para os nomes internos padronizados.

    Usa o dicionário COLUNAS_PADRONIZADAS (config/tse_sources.py). Tolerante
    a espaços extras e a diferenças de caixa no nome das colunas originais
    (ex: ' SG_UF ', 'sg_uf' e 'SG_UF' são todos reconhecidos).

    Importante: alguns pacotes do TSE trazem MAIS DE UMA coluna original
    que mapeia para o mesmo nome interno (ex: NM_UE e NM_MUNICIPIO, ambas
    presentes simultaneamente no mesmo CSV). Renomear as duas para o mesmo
    nome criaria uma coluna duplicada (df['municipio'] deixaria de ser uma
    Series e passaria a ser um DataFrame, quebrando todo o resto do
    pipeline). Esta função detecta esse caso e usa PRIORIDADE_ORIGENS_POR_DESTINO
    para escolher uma única "vencedora"; as demais ficam com o nome original.
    """
    mapa_normalizado = {chave.strip().upper(): valor for chave, valor in COLUNAS_PADRONIZADAS.items()}

    candidatos_por_destino = {}
    for coluna_original in df.columns:
        chave = str(coluna_original).strip().upper()
        if chave in mapa_normalizado:
            destino = mapa_normalizado[chave]
            candidatos_por_destino.setdefault(destino, []).append(coluna_original)

    renomeio = {}
    for destino, origens in candidatos_por_destino.items():
        if len(origens) == 1:
            renomeio[origens[0]] = destino
            continue

        # Múltiplas colunas de origem mapeiam para o mesmo destino no mesmo
        # arquivo. Usa a ordem de prioridade quando definida; senão, mantém
        # a primeira encontrada (ordem de aparição no arquivo).
        prioridade = PRIORIDADE_ORIGENS_POR_DESTINO.get(destino, [])
        origens_upper = [str(o).strip().upper() for o in origens]

        vencedora = None
        for nome_prioritario in prioridade:
            if nome_prioritario in origens_upper:
                vencedora = origens[origens_upper.index(nome_prioritario)]
                break
        if vencedora is None:
            vencedora = origens[0]

        renomeio[vencedora] = destino
        outras = [o for o in origens if o != vencedora]
        logger.info(
            f"Colunas {origens} mapeiam todas para '{destino}' neste arquivo; usando "
            f"'{vencedora}' e mantendo {outras} com o nome original (evitando coluna duplicada)."
        )

    nao_mapeadas = [c for c in df.columns if c not in renomeio]
    if nao_mapeadas:
        logger.debug(f"Colunas não mapeadas (mantidas com o nome original): {nao_mapeadas}")

    return df.rename(columns=renomeio)


def carregar_csv(caminho_csv: str) -> pd.DataFrame:
    """Carrega um CSV do TSE com detecção automática de separador e encoding,
    normaliza as colunas para os nomes internos e imprime diagnóstico
    detalhado no log (caminho, shape, colunas originais, amostra de linhas
    e valores únicos das colunas-chave).
    """
    separador, encoding = detectar_separador_encoding(caminho_csv)
    logger.info(f"Carregando CSV: {caminho_csv}")
    logger.info(f"Separador detectado: '{separador}' | Encoding detectado: {encoding}")

    df = pd.read_csv(caminho_csv, sep=separador, encoding=encoding, low_memory=False)
    df.columns = [str(c).strip() for c in df.columns]

    logger.info(f"Linhas: {len(df)} | Colunas: {len(df.columns)}")
    logger.info(f"Colunas originais: {list(df.columns)}")
    logger.info(f"Primeiras 5 linhas:\n{df.head(5).to_string()}")

    df = normalizar_colunas_tse(df)

    for coluna in COLUNAS_CHAVE_DIAGNOSTICO:
        if coluna in df.columns:
            valores_unicos = df[coluna].dropna().unique()
            amostra_valores = list(valores_unicos[:15])
            logger.info(
                f"Valores únicos em '{coluna}' ({len(valores_unicos)} total): {amostra_valores}"
                + (" ..." if len(valores_unicos) > 15 else "")
            )

    return df


# ----------------------------------------------------------------------
# Filtros
# ----------------------------------------------------------------------

def filtrar_por_uf(df: pd.DataFrame, uf: str) -> pd.DataFrame:
    """Filtra por UF. Usa a coluna normalizada 'uf' (mapeada de SG_UF) quando
    existir; cai para a coluna original 'SG_UF' como segurança se a
    normalização não tiver rodado por algum motivo.
    """
    if not uf:
        return df
    coluna = "uf" if "uf" in df.columns else ("SG_UF" if "SG_UF" in df.columns else None)
    if coluna is None:
        logger.info("Coluna de UF não encontrada no DataFrame; filtro por UF não aplicado.")
        return df
    return df[df[coluna].astype(str).str.strip().str.upper() == uf.strip().upper()]


def filtrar_por_cargo(df: pd.DataFrame, cargo: str) -> pd.DataFrame:
    if not cargo:
        return df
    coluna = "cargo" if "cargo" in df.columns else ("DS_CARGO" if "DS_CARGO" in df.columns else None)
    if coluna is None:
        return df
    return df[df[coluna].astype(str).str.strip().str.upper() == cargo.strip().upper()]


def _filtrar_por_texto(df: pd.DataFrame, coluna_normalizada: str, coluna_original: str, termo: str, modo: str = "parcial") -> pd.DataFrame:
    """Filtra um DataFrame por um campo de texto (nome civil ou nome de urna).

    modo="parcial" (padrão, comportamento original): busca por substring
    livre, case-insensitive — "Sandra Santana" também encontra qualquer
    nome que contenha esses caracteres em sequência (ex: "Alessandra
    Santana", já que "essandra" contém "sandra"). Isso é intencional e foi
    pedido assim originalmente, pra não exigir digitação exata.

    modo="palavra" (novo): exige que CADA PALAVRA do termo de busca apareça
    como palavra inteira no nome (em qualquer ordem/posição), usando
    fronteira de palavra (\\b). "Sandra Santana" passa a encontrar "Sandra
    Santana" mas NÃO "Alessandra Santana", porque "Sandra" não é uma
    palavra inteira dentro de "Alessandra".
    """
    if not termo:
        return df
    coluna = coluna_normalizada if coluna_normalizada in df.columns else (coluna_original if coluna_original in df.columns else None)
    if coluna is None:
        return df

    termo = termo.strip()
    valores = df[coluna].astype(str).str.strip()

    if modo == "palavra":
        palavras = [re.escape(p) for p in termo.split() if p]
        if not palavras:
            return df
        padrao = "".join(rf"(?=.*\b{p}\b)" for p in palavras)
        return df[valores.str.contains(padrao, case=False, regex=True, na=False)]

    if modo != "parcial":
        raise ValueError(f"modo inválido: '{modo}'. Use 'parcial' ou 'palavra'.")

    return df[valores.str.contains(termo, case=False, na=False)]


def filtrar_por_nome_civil(df: pd.DataFrame, nome_civil: str, modo: str = "parcial") -> pd.DataFrame:
    return _filtrar_por_texto(df, "nome_civil", "NM_CANDIDATO", nome_civil, modo)


def filtrar_por_nome_urna(df: pd.DataFrame, nome_urna: str, modo: str = "parcial") -> pd.DataFrame:
    return _filtrar_por_texto(df, "nome_urna", "NM_URNA_CANDIDATO", nome_urna, modo)


def filtrar_por_numero(df: pd.DataFrame, numero) -> pd.DataFrame:
    """Filtra por número de candidato. Converte coluna e filtro para string
    (e remove espaços) antes de comparar, para evitar mismatches entre
    int/str/float (ex: 45123 vs '45123' vs '45123.0')."""
    if numero is None or str(numero).strip() == "":
        return df
    coluna = "numero" if "numero" in df.columns else ("NR_CANDIDATO" if "NR_CANDIDATO" in df.columns else None)
    if coluna is None:
        return df
    coluna_str = df[coluna].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    return df[coluna_str == str(numero).strip()]


def filtrar_por_partido(df: pd.DataFrame, partido: str) -> pd.DataFrame:
    """Filtra por partido, buscando tanto na sigla (SG_PARTIDO -> 'partido')
    quanto no nome completo (NM_PARTIDO -> 'nome_partido'), case-insensitive
    e com busca parcial.
    """
    if not partido:
        return df

    colunas_candidatas = []
    for nome_normalizado, nome_original in (("partido", "SG_PARTIDO"), ("nome_partido", "NM_PARTIDO")):
        if nome_normalizado in df.columns:
            colunas_candidatas.append(nome_normalizado)
        elif nome_original in df.columns:
            colunas_candidatas.append(nome_original)

    if not colunas_candidatas:
        return df

    mask = pd.Series(False, index=df.index)
    termo = partido.strip()
    for coluna in colunas_candidatas:
        mask |= df[coluna].astype(str).str.strip().str.contains(termo, case=False, na=False)
    return df[mask]


# ----------------------------------------------------------------------
# Dados de teste (usados quando a fonte oficial não está configurada)
# ----------------------------------------------------------------------

def _dados_teste(ano: int, uf: str = "SP") -> pd.DataFrame:
    """Gera um DataFrame de teste no mesmo formato esperado do TSE real
    (já usando a convenção normalizada: 'partido' = sigla, 'nome_partido' = nome completo).
    """
    logger.info(f"Usando dados de teste para {ano} (fonte oficial indisponível ou ainda não configurada).")
    return pd.DataFrame(
        [
            {
                "ano": ano, "uf": uf, "nome_civil": "José da Silva Pereira",
                "nome_urna": "Zé Pereira", "numero": "45123", "partido": "PEX",
                "nome_partido": "Partido Exemplo", "cargo": "Vereador", "municipio": "São Paulo",
                "codigo_municipio_tse": "00001", "votos": 12000, "situacao": "ELEITO",
                "origem_dados": "demo", "fonte_dados": "Dados de demonstração do MVP",
            },
            {
                "ano": ano, "uf": uf, "nome_civil": "Maria Souza Lima",
                "nome_urna": "Maria Lima", "numero": "13777", "partido": "PMO",
                "nome_partido": "Partido Modelo", "cargo": "Vereador", "municipio": "Guarulhos",
                "codigo_municipio_tse": "00002", "votos": 8500, "situacao": "ELEITO",
                "origem_dados": "demo", "fonte_dados": "Dados de demonstração do MVP",
            },
        ]
    )


# ----------------------------------------------------------------------
# API principal do módulo
# ----------------------------------------------------------------------

def localizar_csv_tse(ano: int, uf: str = None) -> Path:
    """Localiza o arquivo CSV correto dentro da pasta extraída do pacote do TSE.

    Regras:
      - uf informado (ex: 'SP'): procura o arquivo que termine com '_SP.csv'.
      - uf == 'BRASIL': procura o arquivo que termine com '_BRASIL.csv'.
      - uf None: procura o arquivo BRASIL (consolidado nacional); se não
        existir, levanta FileNotFoundError orientando a informar uma UF ou
        usar carregar_dados_tse(ano) sem uf, que concatena automaticamente
        todos os arquivos estaduais (ver listar_csvs_uf_tse).

    NUNCA usa simplesmente o primeiro arquivo da pasta (arquivos[0]) — esse
    era o bug original que fazia a busca por SP carregar o CSV do AC.

    Levanta FileNotFoundError com a lista de arquivos disponíveis sempre
    que não encontrar o arquivo esperado.
    """
    pasta = Path(TSE_DOWNLOAD_DIR) / f"tse_{ano}"
    if not pasta.exists():
        raise FileNotFoundError(f"Pasta não encontrada: {pasta}")

    arquivos = list(pasta.glob("*.csv"))
    if not arquivos:
        raise FileNotFoundError(f"Nenhum CSV encontrado em: {pasta}")

    if uf:
        uf = uf.upper().strip()
        padrao = f"_{uf}.CSV"
        candidatos = [arq for arq in arquivos if arq.name.upper().endswith(padrao)]
        if candidatos:
            return candidatos[0]
        disponiveis = sorted(a.name for a in arquivos)
        raise FileNotFoundError(
            f"CSV da UF '{uf}' não encontrado em {pasta}. Arquivos disponíveis: {disponiveis}"
        )

    brasil = [arq for arq in arquivos if arq.name.upper().endswith("_BRASIL.CSV")]
    if brasil:
        return brasil[0]

    disponiveis = sorted(a.name for a in arquivos)
    raise FileNotFoundError(
        f"UF não informada e nenhum arquivo '_BRASIL.csv' encontrado em {pasta}. "
        f"Informe uma UF (ex: uf='SP'), ou chame carregar_dados_tse(ano) sem uf para "
        f"concatenar automaticamente todos os arquivos estaduais encontrados: {disponiveis}"
    )


def listar_csvs_uf_tse(ano: int) -> list:
    """Lista todos os CSVs de UF (excluindo o consolidado '_BRASIL.csv', se
    existir) na pasta extraída do pacote do TSE para um ano.

    Usado por carregar_dados_tse() para concatenar todos os estados quando
    nenhuma UF específica é pedida e não existe um arquivo BRASIL consolidado.
    """
    pasta = Path(TSE_DOWNLOAD_DIR) / f"tse_{ano}"
    if not pasta.exists():
        raise FileNotFoundError(f"Pasta não encontrada: {pasta}")
    arquivos = list(pasta.glob("*.csv"))
    return [a for a in arquivos if not a.name.upper().endswith("_BRASIL.CSV")]


def _ler_csv_tse(caminho: Path) -> pd.DataFrame:
    """Lê um único CSV do TSE com separador/encoding detectados
    automaticamente, sempre como string (dtype=str) para preservar zeros à
    esquerda em códigos (município, candidato, zona) e evitar coerção de
    tipos prematura — a conversão para numérico acontece depois, só nas
    colunas que de fato são numéricas (votos, turno, ano, zona).
    """
    separador, encoding = detectar_separador_encoding(str(caminho))
    df = pd.read_csv(caminho, sep=separador, encoding=encoding, dtype=str, low_memory=False)
    df.columns = [str(c).strip() for c in df.columns]
    return df


# Colunas que devem ser convertidas para numérico após a normalização
# (o restante permanece como string para preservar zeros à esquerda).
_COLUNAS_NUMERICAS = ["votos", "votos_validos", "turno", "ano", "zona"]


def carregar_dados_tse(ano: int, uf: str = None) -> pd.DataFrame:
    """Carrega os dados de votação nominal por candidato do TSE para um ano,
    escolhendo o CSV certo via localizar_csv_tse():
      - se `uf` for informado, carrega só o CSV daquela UF (ou do
        consolidado BRASIL, se uf='BRASIL');
      - se `uf` for None, tenta o consolidado BRASIL; se não existir,
        concatena automaticamente todos os arquivos estaduais encontrados
        (listar_csvs_uf_tse).

    Normaliza as colunas (normalizar_colunas_tse) e converte as colunas
    numéricas conhecidas. Loga claramente qual arquivo foi usado, o
    tamanho do resultado e as UFs encontradas.
    """
    if uf:
        csv_path = localizar_csv_tse(ano, uf)
        logger.info(f"CSV selecionado para UF {uf.upper().strip()}: {csv_path}")
        df = _ler_csv_tse(csv_path)
    else:
        try:
            csv_path = localizar_csv_tse(ano, uf=None)
            logger.info(f"CSV consolidado (BRASIL) selecionado: {csv_path}")
            df = _ler_csv_tse(csv_path)
        except FileNotFoundError:
            arquivos_uf = listar_csvs_uf_tse(ano)
            if not arquivos_uf:
                raise
            logger.info(
                f"Nenhum arquivo BRASIL encontrado; concatenando {len(arquivos_uf)} "
                f"arquivo(s) estaduais: {sorted(a.name for a in arquivos_uf)}"
            )
            df = pd.concat([_ler_csv_tse(a) for a in arquivos_uf], ignore_index=True)

    df = normalizar_colunas_tse(df)

    for coluna in _COLUNAS_NUMERICAS:
        if coluna in df.columns:
            df[coluna] = pd.to_numeric(df[coluna], errors="coerce")

    logger.info(f"CSV carregado: {len(df)} linhas, {len(df.columns)} colunas")
    if "uf" in df.columns:
        ufs_encontradas = sorted(df["uf"].dropna().unique().tolist())
        logger.info(f"UFs encontradas no arquivo: {', '.join(ufs_encontradas)}")

    return df


def debug_tse_dataset(ano: int, uf: str = None) -> pd.DataFrame:
    """Diagnóstico de um pacote de dados do TSE para um ano (e,
    opcionalmente, uma UF específica — usa o mesmo carregar_dados_tse()
    usado pela busca real, então o que você vê aqui é exatamente o que
    buscar_candidato_tse() vai usar).

    Imprime: CSV carregado, shape, UFs disponíveis, cargos disponíveis e
    uma amostra das primeiras linhas.

    Uso:
        python -c "from collectors.tse_collector import debug_tse_dataset; debug_tse_dataset(2024, uf='SP')"
    """
    titulo = f"DIAGNÓSTICO DO PACOTE TSE - ANO {ano}" + (f" - UF {uf.upper().strip()}" if uf else "")
    print(f"\n{'='*70}\n{titulo}\n{'='*70}\n")

    caminho_zip = baixar_arquivo_tse(ano)
    extrair_zip(caminho_zip)  # garante que a pasta data/raw/tse/tse_<ano> exista
    df = carregar_dados_tse(ano, uf=uf)

    print(f"\nShape: {df.shape[0]} linhas x {df.shape[1]} colunas")
    print(f"Colunas (normalizadas): {list(df.columns)}")

    if "uf" in df.columns:
        print(f"\nUFs disponíveis: {sorted(df['uf'].dropna().unique().tolist())}")
    else:
        print("\nColuna 'uf' não encontrada após normalização.")

    if "cargo" in df.columns:
        print(f"Cargos disponíveis: {sorted(df['cargo'].dropna().unique().tolist())}")
    else:
        print("Coluna 'cargo' não encontrada após normalização.")

    print(f"\nPrimeiras linhas:\n{df.head(10).to_string()}")
    print(f"\n{'='*70}\nFIM DO DIAGNÓSTICO\n{'='*70}\n")

    return df


def buscar_candidato_tse(
    nome_civil: str = None,
    nome_urna: str = None,
    numero: str = None,
    uf: str = "SP",
    cargo: str = None,
    ano: int = None,
    anos: list[int] | tuple[int, ...] = None,
    modo_nome: str = "parcial",
    usar_demo_quando_falhar: bool = True,
) -> pd.DataFrame:
    """Busca candidatos no(s) arquivo(s) do TSE aplicando os filtros informados.

    Se `ano` ou `anos` não forem informados, mantém o comportamento legado e
    busca nas últimas 5 eleições configuradas. No app Streamlit, passe sempre
    `ano=<ano_base>` para baixar somente o ano escolhido pelo usuário.

    Quando a fonte oficial falha, o fallback para dados de demonstração só é
    usado se `usar_demo_quando_falhar=True`. Em todos os casos, os avisos ficam
    em `df.attrs["avisos_tse"]` para a UI exibir a origem claramente.

    `modo_nome` controla como `nome_civil`/`nome_urna` são comparados:
      - "parcial" (padrão): substring livre — "Sandra Santana" também
        encontra "Alessandra Santana" (porque a sequência de caracteres
        está contida ali). Bom para digitação incompleta/aproximada.
      - "palavra": exige que cada palavra do termo de busca apareça como
        palavra inteira no nome — "Sandra Santana" encontra só quem tem
        as palavras "Sandra" E "Santana" de fato, excluindo "Alessandra
        Santana". Use quando souber o nome completo e quiser precisão.
    """
    if anos is not None:
        anos_busca = [int(a) for a in anos if a]
    elif ano is not None:
        anos_busca = [int(ano)]
    else:
        anos_busca = ultimas_n_eleicoes(5)

    resultados = []
    avisos_tse = []

    for ano_busca in anos_busca:
        try:
            caminho_zip = baixar_arquivo_tse(ano_busca)
            extrair_zip(caminho_zip)  # garante que a pasta data/raw/tse/tse_<ano> exista
            df_ano = carregar_dados_tse(ano=ano_busca, uf=uf)
            df_ano["origem_dados"] = "real"
            df_ano["fonte_dados"] = f"TSE - votação nominal por município e zona ({ano_busca})"
        except FileNotFoundError as e:
            mensagem = f"Arquivo não encontrado para {ano_busca}: {e}."
            logger.info(mensagem)
            if not usar_demo_quando_falhar:
                avisos_tse.append(mensagem)
                continue
            avisos_tse.append(f"{mensagem} Usando dados de demonstração sinalizados.")
            df_ano = _dados_teste(ano_busca, uf)
        except Exception as e:
            mensagem = f"Erro ao processar {ano_busca}: {e}."
            logger.info(mensagem)
            if not usar_demo_quando_falhar:
                avisos_tse.append(mensagem)
                continue
            avisos_tse.append(f"{mensagem} Usando dados de demonstração sinalizados.")
            df_ano = _dados_teste(ano_busca, uf)

        # Filtro por UF reaplicado por segurança: carregar_dados_tse já
        # devolve só a UF pedida quando uf é informado, mas reaplicar aqui
        # é inofensivo (idempotente) e cobre o caso dos dados de teste e do
        # fallback de concatenação de todos os estados (uf=None).
        df_ano = filtrar_por_uf(df_ano, uf)
        df_ano = filtrar_por_cargo(df_ano, cargo)
        df_ano = filtrar_por_nome_civil(df_ano, nome_civil, modo=modo_nome)
        df_ano = filtrar_por_nome_urna(df_ano, nome_urna, modo=modo_nome)
        df_ano = filtrar_por_numero(df_ano, numero)
        if df_ano.empty:
            filtros_aplicados = {
                "nome_civil": nome_civil,
                "nome_urna": nome_urna,
                "numero": numero,
                "uf": uf,
                "cargo": cargo,
            }
            filtros_limpos = {k: v for k, v in filtros_aplicados.items() if v}
            avisos_tse.append(
                f"Ano {ano_busca}: TSE carregado, mas nenhuma candidatura bateu com os filtros {filtros_limpos}. "
                "Isso pode acontecer quando o candidato não concorreu naquele ano, concorreu em outro cargo, "
                "foi vice/suplente ou usou outro número/nome de urna."
            )
        resultados.append(df_ano)

    df_final = pd.concat(resultados, ignore_index=True) if resultados else pd.DataFrame()
    df_final.attrs["avisos_tse"] = avisos_tse
    df_final.attrs["anos_consultados"] = anos_busca
    df_final.attrs["usou_demo"] = bool(
        "origem_dados" in df_final.columns and df_final["origem_dados"].eq("demo").any()
    )

    if df_final.empty:
        logger.info("Nenhum candidato encontrado com os filtros informados.")
    elif "nome_civil" in df_final.columns and df_final["nome_civil"].nunique() > 1:
        logger.info(f"Atenção: {df_final['nome_civil'].nunique()} candidatos diferentes encontrados.")
    else:
        logger.info(f"{len(df_final)} registro(s) encontrado(s).")

    return df_final


def carregar_votacao_candidato(candidato: dict, anos: list) -> pd.DataFrame:
    """Carrega o histórico de votação de um candidato já identificado para os anos dados."""
    if not candidato or not anos:
        return pd.DataFrame()
    return buscar_candidato_tse(
        nome_civil=candidato.get("nome_civil"),
        nome_urna=candidato.get("nome_urna"),
        numero=candidato.get("numero"),
        uf=candidato.get("uf", "SP"),
        cargo=candidato.get("cargo"),
        anos=anos,
    )


def _buscar_candidato_id_existente(cur, nome_civil: str, uf: str):
    """Procura um candidato já salvo no banco com o mesmo nome_civil e UF
    (em QUALQUER ano), para reaproveitar o mesmo candidato_id entre
    importações de eleições diferentes da mesma pessoa.

    Usa nome_civil (nome legal completo) em vez de nome_urna ou numero
    porque esses dois podem mudar de uma eleição para outra (a pessoa pode
    trocar de "nome de urna" ou de número de partido), enquanto o nome
    civil tende a ser estável. Isso replica a convenção já usada nos dados
    fake do projeto (database/init_db.py): um único candidato_id "âncora"
    acumula linhas de votação de vários anos diferentes.
    """
    if not nome_civil or not uf:
        return None
    cur.execute(
        "SELECT id FROM candidatos WHERE nome_civil = ? AND uf = ? ORDER BY ano ASC LIMIT 1",
        (nome_civil, uf),
    )
    row = cur.fetchone()
    return row[0] if row else None


def salvar_resultados_no_banco(df: pd.DataFrame) -> dict:
    """Persiste candidatos e votações (por município e por zona) no banco.

    Três correções importantes em relação à versão anterior:

    1. Agregação correta: os dados do TSE vêm com 1 linha por ZONA
       eleitoral. A tabela `votacao_municipio` espera o TOTAL por
       município, então agora somamos os votos por município antes de
       inserir lá, e guardamos o detalhe original por zona em
       `votacao_zona` (mantendo as duas granularidades disponíveis).

    2. Performance: usa uma única transação e `executemany` (inserção em
       lote) para as tabelas de votação, em vez de uma linha por vez —
       importante para volumes reais do TSE (decenas de milhares de
       linhas por candidato/UF).

    3. Continuidade entre anos: se a mesma pessoa (mesmo nome_civil + UF)
       já tiver um candidato salvo de uma importação anterior (de outro
       ano), REAPROVEITA o candidato_id existente em vez de criar um novo
       — assim votacao_municipio/votacao_zona acumulam o histórico de
       vários anos sob um único candidato_id, que é o que
       analysis.electoral_analysis.gerar_linha_do_tempo() espera (a mesma
       convenção já usada nos dados fake do projeto). Sem isso, buscar o
       mesmo candidato em anos diferentes geraria candidato_id's distintos
       e a linha do tempo nunca uniria os anos.

    Agrupamento de candidato dentro do DataFrame: usa 'id_tse' (SQ_CANDIDATO)
    quando disponível — é o identificador único de candidatura do TSE,
    mais confiável do que agrupar só por nome_urna (que pode se repetir
    entre municípios diferentes, como Sandra/Alessandra Santana mostrou).
    Sem id_tse (ex: dados de teste), cai para numero+nome_urna+município.

    Retorna um dict: {"candidatos_novos": N, "candidatos_reaproveitados": N,
    "municipios": N, "zonas": N}.
    """
    if df.empty:
        logger.info("Nada para salvar (DataFrame vazio).")
        return {"candidatos_novos": 0, "candidatos_reaproveitados": 0, "municipios": 0, "zonas": 0}

    df = df.copy()
    if "id_tse" in df.columns and df["id_tse"].notna().all():
        chave = "id_tse"
    else:
        colunas_chave = [c for c in ("numero", "nome_urna", "municipio") if c in df.columns]
        if not colunas_chave:
            raise ValueError(
                "DataFrame não tem colunas suficientes para identificar candidatos "
                "(precisa de pelo menos numero, nome_urna ou municipio)."
            )
        df["_chave_candidato"] = df[colunas_chave].astype(str).agg("|".join, axis=1)
        chave = "_chave_candidato"

    conn = get_connection()
    cur = conn.cursor()

    registros_municipio = []
    registros_zona = []
    candidatos_novos = 0
    candidatos_reaproveitados = 0
    anos_candidato_regravados = set()

    try:
        for _, grupo in df.groupby(chave):
            primeira = grupo.iloc[0]
            turno = int(primeira.get("turno")) if pd.notna(primeira.get("turno")) else 1
            ano = int(primeira.get("ano"))
            nome_civil = primeira.get("nome_civil")
            uf_candidato = primeira.get("uf")

            candidato_id = _buscar_candidato_id_existente(cur, nome_civil, uf_candidato)
            origem_dados = primeira.get("origem_dados") or "real"
            fonte_dados = primeira.get("fonte_dados") or f"TSE - votação nominal por município e zona ({ano})"

            if candidato_id is not None:
                candidatos_reaproveitados += 1
                cur.execute(
                    """UPDATE candidatos
                       SET origem_dados = ?, fonte_dados = ?
                       WHERE id = ? AND (origem_dados IS NULL OR origem_dados = 'demo')""",
                    (origem_dados, fonte_dados, candidato_id),
                )
                logger.info(
                    f"Candidato '{nome_civil}' ({uf_candidato}) já existe no banco "
                    f"(candidato_id={candidato_id}); reaproveitando para o ano {ano}."
                )
            else:
                cur.execute(
                    """INSERT INTO candidatos
                       (id_tse, nome_civil, nome_urna, numero, cpf_mascarado, partido,
                        sigla_partido, cargo, uf, ano, situacao, origem_dados, fonte_dados)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(primeira.get("id_tse")) if pd.notna(primeira.get("id_tse")) else None,
                        nome_civil,
                        primeira.get("nome_urna"),
                        str(primeira.get("numero")),
                        None,
                        primeira.get("nome_partido") or primeira.get("partido"),
                        primeira.get("partido"),
                        primeira.get("cargo"),
                        uf_candidato,
                        ano,
                        primeira.get("situacao"),
                        origem_dados,
                        fonte_dados,
                    ),
                )
                candidato_id = cur.lastrowid
                candidatos_novos += 1

            chave_regravacao = (candidato_id, ano)
            if chave_regravacao not in anos_candidato_regravados:
                cur.execute(
                    "DELETE FROM votacao_zona WHERE candidato_id = ? AND ano = ?",
                    (candidato_id, ano),
                )
                cur.execute(
                    "DELETE FROM votacao_municipio WHERE candidato_id = ? AND ano = ?",
                    (candidato_id, ano),
                )
                anos_candidato_regravados.add(chave_regravacao)

            # Detalhe por zona — granularidade original do arquivo do TSE.
            for _, linha in grupo.iterrows():
                registros_zona.append((
                    candidato_id, ano, turno, linha.get("uf"), linha.get("municipio"),
                    str(linha.get("zona")) if pd.notna(linha.get("zona")) else None,
                    int(linha.get("votos", 0)) if pd.notna(linha.get("votos")) else 0,
                ))

            # Total por município — soma das zonas (o que votacao_municipio espera).
            colunas_agg = {"votos": "sum"}
            if "codigo_municipio_tse" in grupo.columns:
                colunas_agg["codigo_municipio_tse"] = "first"
            por_municipio = grupo.groupby("municipio", dropna=False).agg(colunas_agg).reset_index()

            for _, linha_mun in por_municipio.iterrows():
                registros_municipio.append((
                    candidato_id, ano, turno, primeira.get("uf"),
                    linha_mun.get("codigo_municipio_tse"), linha_mun["municipio"],
                    primeira.get("cargo"), primeira.get("partido"),
                    int(linha_mun["votos"]) if pd.notna(linha_mun["votos"]) else 0,
                    None, None,
                ))

        if registros_zona:
            cur.executemany(
                """INSERT INTO votacao_zona
                   (candidato_id, ano, turno, uf, municipio, zona, votos)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                registros_zona,
            )

        if registros_municipio:
            cur.executemany(
                """INSERT INTO votacao_municipio
                   (candidato_id, ano, turno, uf, codigo_municipio_tse, municipio, cargo,
                    partido, votos, votos_validos_municipio, percentual_votos)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                registros_municipio,
            )

        conn.commit()
    finally:
        conn.close()

    logger.info(
        f"{candidatos_novos} candidato(s) novo(s), {candidatos_reaproveitados} reaproveitado(s) "
        f"de anos anteriores, {len(registros_municipio)} registro(s) de município e "
        f"{len(registros_zona)} registro(s) de zona salvos no banco (em lote, 1 transação)."
    )
    return {
        "candidatos_novos": candidatos_novos,
        "candidatos_reaproveitados": candidatos_reaproveitados,
        "municipios": len(registros_municipio),
        "zonas": len(registros_zona),
    }


if __name__ == "__main__":
    print(f"[TESTE] Anos disponíveis configurados: {anos_disponiveis()}")
    resultado = buscar_candidato_tse(nome_urna="Zé Pereira", uf="SP", ano=2024)
    print(resultado)
    print("\nDica: para diagnosticar a estrutura real de um pacote do TSE, rode:")
    print('  python -c "from collectors.tse_collector import debug_tse_dataset; debug_tse_dataset(2024)"')
