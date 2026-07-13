# Radar Eleitoral IA

MVP em Python/Streamlit para inteligência territorial eleitoral, diagnóstico estratégico, análise de esforço x resultado, planejamento de comunicação institucional e compliance.

O sistema não automatiza campanha, não faz disparos, não gera propaganda automática e não substitui revisão humana ou jurídica especializada.

## Lógica de Dados do TSE

Os dados eleitorais do TSE são históricos e quase imutáveis. Por isso, o projeto separa duas etapas:

1. **ETL/importação**: baixa ou reaproveita o ZIP do TSE, extrai, normaliza e salva os dados tratados no SQLite.
2. **Dashboard**: consulta apenas o banco local tratado, sem baixar ZIP durante a pesquisa principal.

Tabelas principais:

- `tse_importacoes`: controle de ano/UF importado, status, quantidade de linhas, arquivo de origem e hash.
- `candidaturas_tse`: cache tratado com uma linha por candidato/município/zona do arquivo `votacao_candidato_munzona`.
- `candidatos`, `votacao_municipio` e `votacao_zona`: tabelas usadas pelas análises, preenchidas quando uma candidatura do cache é confirmada no dashboard.

Para uma nova eleição, basta adicionar/configurar o novo ano em `config/tse_sources.py` e importar esse ano para o banco local.

## Camada geográfica

A primeira camada geográfica do MVP usa o CSV público de zonas eleitorais do Mapas Livres e deixa registradas fontes complementares do IBGE e do Google Drive auxiliar em `config/geo_sources.py`.

O TSE fornece votação por município, zona ou seção conforme o arquivo eleitoral usado. O dashboard prioriza:

- Vereador em São Paulo: distribuição por zona eleitoral.
- Cargos estaduais/federais: distribuição por município.
- Mapa com pontos apenas quando a base geográfica importada contém `latitude` e `longitude`.

Quando não há coordenadas confiáveis, o app não mostra mapa vazio: ele exibe ranking territorial com os dados oficiais do TSE. Mapa por bairro, distrito ou setor censitário exige uma base de cruzamento territorial confiável; o projeto não infere bairro/setor eleitoral automaticamente.

Importar zonas eleitorais:

```powershell
cd C:\radar-eleitoral-ia
.\.venv\Scripts\python.exe scripts\import_geo_data.py --zonas-eleitorais
.\.venv\Scripts\python.exe scripts\import_geo_data.py --uf SP --municipio "São Paulo"
```

## Instalação

```powershell
cd C:\radar-eleitoral-ia
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
```

Se a venv já existir:

```powershell
cd C:\radar-eleitoral-ia
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## Inicializar Banco

```powershell
cd C:\radar-eleitoral-ia
.\.venv\Scripts\python.exe database\init_db.py
```

O banco local fica em:

```text
C:\radar-eleitoral-ia\database\radar_eleitoral.db
```

## Importar Histórico do TSE

Importar um ano/UF:

```powershell
cd C:\radar-eleitoral-ia
.\.venv\Scripts\python.exe scripts\import_tse_history.py --uf SP --anos 2024
```

Importar mais de um ano:

```powershell
.\.venv\Scripts\python.exe scripts\import_tse_history.py --uf SP --anos 2024 2020
```

Usar apenas ZIPs já baixados em `data/raw/tse`:

```powershell
.\.venv\Scripts\python.exe scripts\import_tse_history.py --uf SP --anos 2022 --somente-baixados
```

Forçar reimportação de um ano/UF já carregado:

```powershell
.\.venv\Scripts\python.exe scripts\import_tse_history.py --uf SP --anos 2024 --forcar
```

O dashboard também possui a aba **Administração de Dados**, onde é possível ver o status das importações e importar/reimportar um ano/UF.

## Rodar Dashboard

```powershell
cd C:\radar-eleitoral-ia
.\.venv\Scripts\activate
streamlit run app.py
```

Fluxo recomendado:

1. Importe o ano/UF desejado pela aba **Administração de Dados** ou pelo script.
2. Use os filtros da sidebar e clique em **Pesquisar candidato**.
3. Confirme a candidatura correta.
4. Consulte municípios, mapa visual, esforço x resultado, comunicação, compliance e relatório.

Se o ano/UF ainda não estiver importado, o app mostra:

```text
Dados de {uf}/{ano} ainda não importados. Acesse a área de Administração para importar.
```

## Funcionalidades

- Pesquisa candidato no cache local tratado do TSE por nome civil, nome na urna, número, UF, cargo, partido e ano.
- Importa dados eleitorais oficiais do TSE por script ou pela aba Administração.
- Salva candidatos e votação em SQLite para análises rápidas.
- Consulta emendas no banco local/CSV e, quando houver chave, no Portal da Transparência.
- Gera linha do tempo, municípios fortes, quedas, crescimento e oportunidades.
- Exibe mapa visual de desempenho municipal.
- Gera matriz esforço x resultado em linguagem institucional.
- Gera plano de comunicação 30/60/90 dias sem disparos em massa.
- Executa checklist de compliance eleitoral.
- Gera relatório PDF com fonte dos dados e aviso jurídico.

Aviso obrigatório: este relatório não substitui análise jurídica especializada.

## Estrutura

```text
radar-eleitoral-ia/
  app.py
  commercial_flow.py
  requirements.txt
  ai/
  analysis/
  collectors/
  compliance/
  config/
  data/
  database/
  reports/
  scripts/
  tests/
```

Arquivos principais:

- `app.py`: dashboard Streamlit, busca local e administração de dados.
- `scripts/import_tse_history.py`: ETL controlado do histórico TSE.
- `collectors/tse_collector.py`: download retomável, extração, leitura e normalização TSE.
- `database/init_db.py`: schema SQLite e seed de demonstração.
- `database/db_utils.py`: funções de banco, cache TSE e consultas.
- `analysis/tse_aggregations.py`: agregações sobre o cache tratado.
- `collectors/emendas_collector.py`: CSV, Portal da Transparência e normalização.
- `reports/pdf_generator.py`: PDF com fallback mínimo sem ReportLab.
- `scripts/health_check.py`: validação local do MVP.

## Portal da Transparência

A chave da API é opcional para o app abrir. Para consultas online:

1. Cadastre a chave no Portal da Transparência.
2. Configure uma destas opções:
   - variável de ambiente `PORTAL_TRANSPARENCIA_API_KEY`;
   - arquivo `.env`;
   - arquivo `config/secrets_local.py`.

`config/secrets_local.py` e `.env` não devem ser versionados.

## Validação

```powershell
cd C:\radar-eleitoral-ia
.\.venv\Scripts\python.exe -m compileall .
.\.venv\Scripts\python.exe database\init_db.py
.\.venv\Scripts\python.exe scripts\health_check.py
.\.venv\Scripts\python.exe -m pytest
```

Se o Windows negar acesso ao diretório temporário padrão do pytest, defina um temporário local antes de rodar:

```powershell
$env:TEMP='C:\radar-eleitoral-ia\.pytest_tmp'
$env:TMP='C:\radar-eleitoral-ia\.pytest_tmp'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp 'C:\radar-eleitoral-ia\.pytest_tmp'
```
