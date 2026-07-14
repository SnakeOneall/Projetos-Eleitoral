# Memorial Descritivo — Radar Eleitoral IA / Radar do Eleitor

**Projeto:** Plataforma de transparência da atividade parlamentar
**Módulo público:** Radar do Eleitor
**Local do repositório:** `radar-eleitoral-ia`
**Data de referência deste memorial:** julho de 2026
**Situação:** em desenvolvimento ativo, com módulo público publicado (Streamlit Community Cloud)

---

## 1. Apresentação

O Radar Eleitoral IA é uma plataforma de transparência cívica que reúne, em um único lugar e em linguagem acessível, a atividade real de parlamentares brasileiros a partir de fontes oficiais do governo. Seu módulo voltado ao cidadão, o **Radar do Eleitor**, permite que qualquer pessoa consulte o trabalho de quem elegeu — ou pretende eleger — sem precisar navegar por dezenas de portais governamentais distintos, cada um com sua própria estrutura, linguagem técnica e barreiras de acesso.

A premissa central do projeto é simples: os dados que permitem avaliar um mandato já são públicos, mas estão espalhados, fragmentados e escritos em jargão administrativo que a maioria dos eleitores não domina. A plataforma resolve esse problema de acesso e tradução, trazendo luz sobre presença em sessões, gastos de gabinete, emendas parlamentares, projetos apresentados, votações e obras públicas — sempre com o link para a fonte oficial de cada número.

O projeto não faz ranking, não atribui notas e não recomenda voto. Apresenta fatos públicos de forma factual e comparável, para que cada eleitor tire suas próprias conclusões.

---

## 2. Objetivos

### 2.1 Objetivo geral

Democratizar o acesso à informação sobre a atividade parlamentar, transformando dados públicos dispersos e técnicos em conhecimento claro e conferível para o eleitor comum.

### 2.2 Objetivos específicos

O primeiro objetivo é permitir que o cidadão consulte, por parlamentar, quantas emendas ele assinou e para onde os recursos foram destinados, com identificação de município, área e valores empenhado, liquidado e pago. O segundo objetivo é oferecer uma leitura territorial do impacto dessa atuação ao longo do mandato, mostrando a distribuição geográfica dos recursos e a evolução ano a ano. A esses objetivos iniciais somaram-se, ao longo do desenvolvimento, a presença em sessões e comissões, os gastos de gabinete com comprovação documental, a produção legislativa, o registro de votações nominais e as obras públicas estaduais por município.

Um princípio inegociável atravessa todos os objetivos: **todos os dados devem ser coletados exclusivamente de sites e serviços oficiais do governo.**

---

## 3. Público-alvo e proposta de valor

O público-alvo primário é o eleitor comum, de todos os níveis de escolaridade e familiaridade digital. Por isso, decisões de design priorizaram a máxima clareza: valores sempre em formato de moeda corrente (R$ 200.000,00), números escritos diretamente sobre as barras dos gráficos (sem exigir que o usuário passe o cursor), termos técnicos explicados em linguagem cotidiana, siglas legislativas acompanhadas de sua descrição por extenso, e denominadores de contexto (por exemplo, "participou de 343 de 353 sessões", em vez de um número solto que não permite julgamento).

A proposta de valor está na combinação de três atributos difíceis de encontrar juntos: **fonte oficial** (cada dado é rastreável até o portal governamental de origem), **linguagem de eleitor** (nada de jargão) e **agregação por mandato** (a história completa de uma legislatura, não apenas o recorte de um ano).

---

## 4. Escopo funcional

A plataforma cobre atualmente três níveis do Poder Legislativo que o eleitor paulista vota, além de uma camada de obras do Executivo estadual.

Para **deputados federais e senadores** (cobertura nacional), o painel apresenta o perfil e a situação do mandato; o trabalho no plenário (sessões de votação com denominador, eventos, discursos e projetos apresentados); a seção "Como votou", com o registro de votações nominais; os gastos da cota parlamentar (CEAP na Câmara, CEAPS no Senado), item a item e com o documento fiscal; e as emendas parlamentares federais, com valores, áreas beneficiadas e destino.

Para **deputados estaduais de São Paulo** (ALESP), o painel apresenta o perfil enriquecido com base eleitoral e áreas de atuação declaradas; a presença em comissões permanentes, com denominador e nomes das comissões por extenso; os votos em comissões (processados por ETL a partir do arquivo oficial); a verba de gabinete; e as emendas estaduais, obtidas da API de consulta oficial do Portal da Transparência do Estado.

Para **qualquer município de São Paulo**, uma seção independente ("Obras no seu município") apresenta as obras estaduais do Departamento de Estradas de Rodagem (DER) que passam pela cidade e, ao lado, as emendas estaduais destinadas ao mesmo município — permitindo ao eleitor observar o contexto entre verba direcionada e obra executada, sem afirmar vínculo direto onde ele não é comprovável.

Toda a navegação por parlamentares se dá por **mandato (legislatura)**, cobrindo as cinco últimas legislaturas federais (2023–2026, 2019–2022, 2015–2018, 2011–2014 e 2007–2010), com agregação dos valores por período e visualização ano a ano.

---

## 5. Arquitetura técnica

### 5.1 Stack

A plataforma é desenvolvida em Python. A interface do Radar do Eleitor utiliza Streamlit, com visualizações em Plotly. O tratamento de dados é feito com pandas; a comunicação com serviços oficiais, com requests. A persistência local de apoio usa SQLite. O módulo público está publicado no Streamlit Community Cloud, com a chave de API sensível protegida via mecanismo de segredos (st.secrets), nunca versionada.

### 5.2 Organização em módulos

O projeto separa claramente as responsabilidades. A camada de **coletores** (`collectors/`) concentra a integração com cada fonte oficial, um módulo por origem de dados. A camada de **configuração** (`config/`) centraliza fontes oficiais, escopo e credenciais locais (estas fora do controle de versão). A camada de **banco** (`database/`) cuida do esquema e do acesso a dados. A camada de **scripts** hospeda rotinas de ETL offline. O aplicativo público (`app_eleitor.py`) orquestra a interface, mantido separado do dashboard estratégico original (`app.py`).

Essa separação permitiu evoluir a plataforma de forma incremental e segura: cada nova fonte de dados entrou como um coletor isolado, testado de ponta a ponta antes de ser exposto na interface.

### 5.3 Estratégia de desempenho

Consultas a serviços oficiais são armazenadas em cache — de 24 horas para dados históricos (que não mudam) e de 1 hora para dados correntes. Como resultado, após a primeira consulta de um parlamentar, todas as seções carregam praticamente de forma instantânea, e o custo de requisições aos portais governamentais é minimizado. Arquivos oficiais muito grandes (como o de 64 MB com 226 mil votos de comissões da ALESP) são processados por ETL offline, que gera um arquivo compacto versionado, lido instantaneamente pelo aplicativo publicado.

---

## 6. Fontes de dados oficiais

Um dos pilares do projeto é a rastreabilidade: cada informação apresentada tem origem em serviço oficial de governo, e o link de conferência acompanha o dado na tela. As fontes integradas até o momento são:

**Câmara dos Deputados — API de Dados Abertos** (`dadosabertos.camara.leg.br`, pública, sem chave). Fornece a lista de deputados, situação do mandato, despesas da cota parlamentar (CEAP) com nota fiscal, eventos e sessões deliberativas, discursos, proposições de autoria e votações nominais com o voto individual.

**Senado Federal — API Legis** (`legis.senado.leg.br`, pública, sem chave) e o CSV oficial de despesas CEAPS da transparência do Senado. Fornecem a lista de senadores, votações nominais já com o voto de cada um, autorias e a verba de gabinete.

**Portal da Transparência do Governo Federal** (`api.portaldatransparencia.gov.br`, mediante chave gratuita). Fornece as emendas parlamentares federais por autor e ano, com valores empenhado, liquidado e pago, e a localidade do gasto.

**Assembleia Legislativa do Estado de São Paulo (ALESP) — Portal de Dados Abertos** (`al.sp.gov.br/dados-abertos`, público, arquivos XML). Fornece a lista de deputados estaduais, despesas de gabinete (série desde 2002), presenças e votações em comissões permanentes, e o cadastro de comissões.

**Portal da Transparência do Estado de São Paulo** (`transparencia.sp.gov.br`). Fornece as emendas parlamentares estaduais, por meio da mesma API de consulta usada pelo frontend oficial, descoberta por engenharia reversa (ver seção 8).

**Portal de Dados Abertos do Estado de São Paulo — CKAN** (`dadosabertos.sp.gov.br`, API REST oficial, sem chave). Fornece o dataset de obras do DER/SP e outros 22 datasets de obras estaduais.

---

## 7. Metodologia de dados e decisões técnicas relevantes

O rigor no tratamento dos dados foi tão importante quanto a coleta. Diversas correções e decisões metodológicas garantem que os números exibidos sejam corretos e honestos.

No coletor de emendas federais, verificou-se que a API do Portal da Transparência ignora silenciosamente parâmetros como UF e município e aceita apenas o filtro por nome do autor; o coletor foi ajustado para usar o parâmetro correto e para interpretar o campo de localidade do gasto, distinguindo emenda municipal, estadual e nacional.

Nas emendas estaduais de São Paulo, identificou-se que a API oficial entrega os valores multiplicados por cem (centavos formatados como reais) — o que inicialmente produzia totais irreais, na casa dos bilhões por deputado. A comprovação veio de uma verificação cruzada (a soma de um ano daria R$ 179 bilhões, contra um orçamento real de emendas de aproximadamente R$ 3,3 bilhões anuais; e uma emenda para maquinário aparecia cem vezes maior que o preço de mercado do equipamento). A correção, dividindo por cem, está documentada no código.

Na medição de presença, adotou-se o princípio do denominador justo. Para deputados federais, a presença é apresentada sobre o total de sessões deliberativas realizadas no período. Para deputados estaduais, sobre o total de reuniões realizadas apenas nas comissões em que o parlamentar efetivamente atuou — pois ninguém participa de todas as comissões da casa, e comparar com o total geral seria enganoso. Em todos os casos, uma nota metodológica esclarece que a presença é derivada dos registros de eventos das APIs e não substitui o boletim oficial de frequência, e distingue recesso parlamentar (constitucional) de eventual ausência individual.

Diferenças de identificadores entre arquivos da mesma casa (a ALESP usa códigos distintos para o mesmo deputado em arquivos diferentes) foram resolvidas com vínculo por múltiplas chaves e reforço por nome. Filtros sensíveis a acento e caixa (o Portal SP exige o nome do município exatamente como "MARÍLIA") foram tratados com normalização automática a partir da lista oficial de municípios.

---

## 8. Investigações técnicas de integração (engenharia reversa de endpoints)

Parte do trabalho consistiu em descobrir formas oficiais e estáveis de consumir dados de portais que, à primeira vista, só ofereciam painéis interativos, privilegiando integrações por endpoint HTTP em vez de raspagem de HTML.

No **Portal da Transparência do Estado de SP**, a investigação da comunicação entre navegador e servidor revelou que a consulta de emendas realizadas utiliza um endpoint REST (`POST /EmendasParlamentares/Buscar`, com corpo JSON) e um endpoint de exportação (`POST /EmendasParlamentares/ExportarCsv`) que devolve o CSV completo do filtro em uma única resposta, sem autenticação. Esse achado permitiu integrar as emendas estaduais diretamente, sem navegador nem scraping. Classificação de estabilidade: endpoint interno estável.

No **Portal da Transparência — Obras Públicas**, constatou-se que os dados vivem em um relatório Power BI embarcado. A engenharia reversa demonstrou ser possível consultar o modelo (`modelsAndExploration`) e executar consultas de dados (`querydata`) de forma anônima, mas o formato de resposta é frágil e não constitui dado aberto oficial; a integração foi considerada de menor robustez.

Posteriormente, identificou-se o **Portal de Dados Abertos do Estado (CKAN)** como a fonte ideal para obras — uma API REST oficial e consagrada, com dataset baixável do DER/SP. Essa passou a ser a fonte adotada para a seção de obras, por ser a mais sólida das alternativas investigadas.

---

## 9. Conformidade eleitoral

O projeto foi concebido em conformidade com a Resolução TSE nº 23.755/2026, que, entre outras regras, proíbe que sistemas de inteligência artificial ranqueiem, recomendem candidatos ou indiquem preferência de voto, direta ou indiretamente.

Em decorrência, a plataforma adota, por decisão de arquitetura e de produto, a exibição de dados brutos e comparáveis, sempre acompanhados da fonte oficial, e evita deliberadamente notas, pontuações ou rankings. Um rodapé institucional, presente em todas as consultas, reafirma que o painel informa e não recomenda voto, e lembra que quantidade não é sinônimo de qualidade — um bom mandato se avalia também pelo conteúdo dos projetos e pela realidade de cada localidade. Essa postura, além de atender à norma, tornou-se um diferencial de credibilidade da plataforma.

---

## 10. Estado atual do projeto

Encontram-se implementados e validados com dados reais: a integração completa das fontes federais (Câmara e Senado), estaduais (ALESP e Portal da Transparência de SP) e do Portal de Dados Abertos estadual (CKAN); a navegação por mandato ao longo das cinco últimas legislaturas federais; a seção "Como votou" para as três casas; os gastos de gabinete com comprovação documental; as emendas federais e estaduais com correção de valores; a seção de obras por município com contexto de emendas; e o conjunto de melhorias de acessibilidade visual (moeda corrente, rótulos nas barras, denominadores, glossário de siglas e nomes de comissões por extenso).

O módulo público está publicado no Streamlit Community Cloud, com atualização automática a cada nova versão enviada ao repositório e com a chave de API protegida por segredo. A base de código está versionada no GitHub, com credenciais e artefatos sensíveis devidamente excluídos do controle de versão.

---

## 11. Limitações conhecidas

Algumas limitações decorrem das próprias fontes e são apresentadas com transparência ao usuário. As emendas estaduais de São Paulo têm dados estruturados disponíveis a partir de 2022 (anos anteriores existem apenas em PDF). A presença em plenário da ALESP não é publicada em formato aberto — apenas a presença em comissões permanentes. As obras integradas até o momento cobrem o DER/SP (rodovias e infraestrutura estadual), não obras municipais. O vínculo direto entre uma emenda específica e uma obra específica não é afirmado quando não é comprovável documentalmente; a plataforma apresenta o contexto por município, deixando explícita essa ressalva.

---

## 12. Perspectivas e próximas fases

Como evolução natural, mapearam-se caminhos que ampliam a cobertura e a profundidade da plataforma: a incorporação de vereadores de capitais com dados abertos; a integração de emendas estaduais quando o Estado as disponibilizar em formato aberto (recomendação de política de transparência já reforçada por organizações da sociedade civil); a expansão da camada de obras para além do DER; e o aprofundamento do cruzamento entre emendas e obras conforme os identificadores oficiais permitam vínculo mais preciso.

---

## 13. Ficha técnica

**Linguagem:** Python. **Interface:** Streamlit + Plotly. **Dados:** pandas, requests. **Persistência de apoio:** SQLite. **Publicação:** Streamlit Community Cloud. **Controle de versão:** Git/GitHub.

**Fontes oficiais integradas:** API de Dados Abertos da Câmara dos Deputados; API Legis e transparência (CEAPS) do Senado Federal; Portal da Transparência do Governo Federal (emendas); Portal de Dados Abertos da ALESP; Portal da Transparência do Estado de SP (emendas estaduais); Portal de Dados Abertos do Estado de SP — CKAN (obras).

**Conformidade:** Resolução TSE nº 23.755/2026 — plataforma de caráter informativo, sem ranqueamento ou recomendação de voto.

---

*Este memorial descreve o estado do projeto até julho de 2026 e é atualizado conforme a plataforma evolui.*
