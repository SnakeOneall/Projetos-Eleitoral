# Radar Eleitoral IA — Visão de Produto

## O problema

Candidatos, partidos e equipes de comunicação tomam decisões de onde investir tempo e recursos com base em percepção, não em dados. Resultado: esforço de comunicação mal direcionado, verbas públicas sem conexão clara com a percepção do eleitorado, e dificuldade de provar, com dados, onde a atuação parlamentar realmente gerou retorno territorial.

## A solução

O Radar Eleitoral IA cruza três camadas de dados públicos e gera um diagnóstico territorial:

1. **Histórico eleitoral** — como o candidato (ou partido) evoluiu, município a município, eleição após eleição.
2. **Atuação parlamentar** — emendas e verbas públicas destinadas a cada município, por área (saúde, educação, infraestrutura etc.).
3. **Esforço versus resultado** — cruzamento das duas camadas anteriores para identificar:
   - onde o investimento público teve retorno eleitoral (alto esforço / alto resultado);
   - onde houve investimento sem retorno aparente, sinalizando oportunidade de reforço de comunicação (alto esforço / baixo resultado);
   - onde há reconhecimento regional mesmo com baixo investimento direto (baixo esforço / alto resultado);
   - onde nenhum dos dois aconteceu, sinalizando prioridade para o próximo ciclo.

A partir desse diagnóstico, o sistema gera automaticamente um **plano de comunicação de 30/60/90 dias** — com temas, formatos de conteúdo e calendário editorial — sempre em linguagem institucional (prestação de contas, escuta pública, divulgação de propostas), e passa esse plano por um **checklist de compliance eleitoral** antes de chegar à equipe humana.

## Para quem é

- Candidatos e mandatos em exercício que querem decisão por dados em vez de percepção.
- Partidos que precisam organizar estratégia territorial entre múltiplos candidatos.
- Agências e equipes de comunicação política que precisam de um diagnóstico rápido para montar calendário editorial e produção de conteúdo.

## O que o produto entrega

- Dashboard interativo para pesquisar candidato, comparar eleições e visualizar mapas/rankings de municípios.
- Relatório estratégico em PDF, pronto para apresentação a clientes ou à própria campanha.
- Checklist de risco eleitoral em cada etapa do planejamento de comunicação.

## Camada geográfica

A camada geográfica atual estabiliza a visualização territorial sem inventar precisão que a base não possui. O TSE pode fornecer votação por município, zona ou seção, dependendo do arquivo importado. Nesta versão, o produto usa distribuição por zona eleitoral para vereador em São Paulo e distribuição por município para cargos estaduais/federais.

O arquivo público de zonas eleitorais do Mapas Livres pode trazer endereço e, quando disponível, latitude/longitude aproximada da zona. A base de setores censitários do IBGE é uma fonte complementar para evolução futura, mas exige cruzamento geográfico adicional. O Radar não infere bairro, distrito ou setor eleitoral sem uma base confiável de relacionamento.

Quando não há coordenadas, o dashboard exibe ranking territorial em vez de mapa azul vazio. Isso preserva leitura estratégica e mantém a rastreabilidade dos dados oficiais.

## O que o produto **não** faz (por design)

- Não automatiza disparo de mensagens ou publicações.
- Não gera conteúdo de ataque pessoal, fake news ou impulsionamento negativo.
- Não substitui assessoria jurídica eleitoral — todo plano inclui aviso de revisão jurídica recomendada.

## Estágio atual

MVP funcional para São Paulo, com dados de teste e importação manual de emendas via CSV. Arquitetura modular (engines independentes de coleta, análise, IA e compliance) já preparada para escalar para dados reais do TSE, integração com Portal da Transparência/SIGA Brasil/Transferegov, e expansão para outros estados.
