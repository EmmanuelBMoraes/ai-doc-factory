# Document AI Factory

Projeto de hackathon. Recebe um PDF de lote com muitas páginas escaneadas (ou uma imagem), faz OCR de cada página, separa os documentos do lote, classifica cada um por tipo documental e envia os casos duvidosos para uma fila de revisão humana. O texto das páginas fica no PostgreSQL e pode ser pesquisado.

Hoje existe apenas o backend (API + workers). O que está pronto, o que é parcial e o que ainda não existe está na seção [Estado atual](#estado-atual).

## Stack e serviços

- Python 3.12, FastAPI, PostgreSQL 16, Redis 7, Docker Compose.
- OCR: Tesseract (`-l por`) sobre páginas rasterizadas a 150 dpi com `pdf2image`/Poppler, 4 páginas em paralelo.
- Classificação: Jev (via OpenRouter) como classificador principal e Gemini como segunda opinião quando a confiança é baixa; ou um classificador por palavras-chave (`CLASSIFICADOR=regras`) que roda sem rede.
- Arquivos do lote em volume Docker (`/data/lote_<id>/`).

| Serviço | Função |
|---|---|
| `api` | FastAPI: upload, consulta, busca e revisão |
| `worker_ocr_seg` | Consome `segmentar_lote`: rasteriza, faz OCR, segmenta em documentos |
| `worker_classify` | Consome `classificar_documento`: classifica, roteia por confiança, fecha o lote |
| `postgres` | Dados e busca full-text (config `portuguese`) |
| `redis` | Filas (listas, com ack via `BLMOVE`, 3 tentativas e depois `dlq`) |

```
POST /lotes (PDF/imagem)
      |
      v
    api --------> Redis: segmentar_lote
                        |
                        v
                 worker_ocr_seg: rasteriza + OCR (texto por página no Postgres)
                                 segmentação (cascata abaixo)
                        |  um job por documento
                        v
                 Redis: classificar_documento
                        |
                        v
                 worker_classify: classificador -> roteamento por confiança
                        |                |
                 classificado        em_revisao ----> GET /revisao
                        |                             POST /documentos/{id}/revisao
                        v                                      |
              fan-in: lote.docs_pendentes = 0 => lote concluido
```

**Segmentação em cascata** (`app/segmentacao.py`): página em branco herda o documento anterior; "Página 1 de N" abre documento e "Página k de N" (k>1) continua; senão, similaridade TF-IDF entre páginas consecutivas (abaixo de `SEG_SIM_BAIXO` abre, a partir de `SEG_SIM_ALTO` continua); na faixa ambígua pergunta Sim/Não ao Jev (só com `CLASSIFICADOR=jev`). Se o Jev não responde ou fica no meio, o sistema abre documento novo e marca `segmentacao_ambigua`, o que leva o documento à revisão. Os limiares ainda não foram calibrados.

**Roteamento** (`app/roteamento.py`): confiança >= `CONF_AUTO` e sem desacordo entre modelos vira `classificado`; entre `CONF_MIN` e `CONF_AUTO`, ou com desacordo, ou segmentação ambígua, vira `em_revisao` com o tipo sugerido; abaixo de `CONF_MIN`, `em_revisao` com tipo `desconhecido`.

**Tipos documentais** (`app/config.py`): `aso`, `folha_pagamento`, `folha_ponto`, `holerite`, `recibo_ferias`, `atestado_medico`, `contrato_trabalho`.

**Estados.** Lote: `recebido`, `ocr`, `classificando`, `concluido`, `erro`. Documento: `segmentado`, `classificado`, `em_revisao`, `revisado`, `erro`.

## Como rodar

### Pré-requisitos

- Docker com Docker Compose v2.
- `curl`.
- Para o modo com LLM: chaves de OpenRouter (Jev) e Google AI Studio (Gemini). Para o modo sem rede, nenhuma chave.

Testado com Docker 28 e Compose v2.39 no Windows (Git Bash).

### 1. Configurar o `.env`

```bash
cp .env.example .env
```

Edite o `.env`:

- `POSTGRES_PASSWORD` é obrigatória (o `docker compose` falha sem ela). Use uma senha de desenvolvimento.
- `API_PORT` define a porta da API no host (padrão 8000).
- Para rodar sem rede e sem chaves, defina `CLASSIFICADOR=regras`. Com `CLASSIFICADOR=jev` (padrão do `.env.example`), preencha `OPENROUTER_API_KEY`, `JEV_MODEL` e `GEMINI_API_KEY`.

O `.env` está no `.gitignore`. Nunca o versione.

### 2. Subir os serviços

```bash
docker compose up -d --build
docker compose ps
```

Na primeira vez a imagem é construída (instala Tesseract e Poppler). Quando `api`, `postgres` e `redis` estiverem `healthy`:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

(troque `8000` pelo valor de `API_PORT`; os exemplos abaixo usam 8000).

### 3. Enviar um lote e consultar o resultado

```bash
curl -F "arquivo=@meu_lote.pdf" http://localhost:8000/lotes
# {"lote_id":1,"estado":"recebido","existente":false}

curl http://localhost:8000/lotes/1
```

O processamento é assíncrono: repita o `GET /lotes/1` até `"estado":"concluido"` (um lote pequeno leva alguns segundos). A resposta traz os documentos com intervalo de páginas, estado, tipo, confiança e probabilidades. Reenviar o mesmo arquivo não cria outro lote (a identidade é o SHA-256 dos bytes): a API devolve o existente com `"existente":true`.

Exemplo de resposta (lote de 3 páginas, `CLASSIFICADOR=regras`, resumida):

```json
{"id":1,"estado":"concluido","docs_pendentes":0,
 "documentos":[
  {"id":1,"ordem":1,"pagina_ini":1,"pagina_fim":1,"estado":"classificado","tipo":"aso","confianca":1.0},
  {"id":2,"ordem":2,"pagina_ini":2,"pagina_fim":3,"estado":"classificado","tipo":"contrato_trabalho","confianca":1.0}]}
```

Busca por texto e detalhe de um documento:

```bash
curl "http://localhost:8000/busca?q=contrato"
curl http://localhost:8000/documentos/2
```

### 4. Testes

```bash
docker compose exec api python -m pytest tests -q
```

Os testes rodam dentro do container `api`, que tem acesso ao Postgres e ao Redis do Compose. Na última execução: `93 passed`.

### 5. Rodar sem rede

Com `CLASSIFICADOR=regras` no `.env`, a classificação usa palavras-chave (`app/classificador_regras.py`) e a segmentação não chama o Jev, então nenhum texto de documento sai da máquina. Ao mudar o `.env`, recrie os serviços: `docker compose up -d`.

### 6. Mudança de schema e dados locais

O `sql/schema.sql` só é aplicado na primeira inicialização do volume do Postgres, e não há migrações. Se o schema mudar, é preciso recriar o banco:

```bash
docker compose down -v
```

O `-v` apaga os volumes: **todos os dados locais** (lotes, documentos, arquivos enviados e o cache de LLM) são perdidos. Para só parar os serviços, use `docker compose down` sem `-v`.

### Frontend

A pasta `frontend/` é um projeto separado do backend (Vite + React + TypeScript + Tailwind v4). Hoje contém apenas o esqueleto inicial gerado pelo template do Vite, sem chamadas à API. Não faz parte do `docker-compose.yml` e não foi testada para este README.

## Endpoints

| Método e rota | Descrição | Exemplo |
|---|---|---|
| `GET /health` | Verifica Postgres e Redis | `curl localhost:8000/health` |
| `POST /lotes` | Envia PDF, JPEG, PNG ou TIFF (multipágina inclusive); imagens viram `original.pdf`. Arquivo inválido: 400 | `curl -F "arquivo=@lote.pdf" localhost:8000/lotes` |
| `GET /lotes/{id}` | Estado do lote e lista de documentos (intervalo, tipo, confiança, probabilidades) | `curl localhost:8000/lotes/1` |
| `GET /documentos/{id}` | Documento com tipo, confiança, motivo de revisão e páginas (texto e `imagem_url`) | `curl localhost:8000/documentos/2` |
| `GET /lotes/{lote_id}/paginas/{n}/imagem` | PNG da página | `curl -o p1.png localhost:8000/lotes/1/paginas/1/imagem` |
| `GET /busca?q=...&limite=20` | Full-text search (`portuguese`); devolve lote, página e trecho com `<b>` | `curl "localhost:8000/busca?q=contrato"` |
| `GET /revisao` | Fila de documentos `em_revisao`, com tipo sugerido e motivo | `curl localhost:8000/revisao` |
| `POST /documentos/{id}/revisao` | Corrige o tipo; o documento vira `revisado` e `tipo_original` guarda o tipo sugerido. 409 se o documento não está em revisão | ver abaixo |

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"tipo":"aso","revisor":"nome_do_revisor"}' \
  localhost:8000/documentos/1/revisao
```

O `tipo` deve ser um dos tipos documentais listados acima. A documentação interativa do FastAPI fica em `/docs`.

## Variáveis de ambiente

Definidas no `.env` (modelo em `.env.example`), repassadas aos containers pelo `docker-compose.yml`. Nenhum valor secreto vai no repositório.

| Variável | Padrão | Uso |
|---|---|---|
| `POSTGRES_USER` | `docfactory` | Usuário do Postgres |
| `POSTGRES_PASSWORD` | (obrigatória) | Senha do Postgres |
| `POSTGRES_DB` | `docfactory` | Nome do banco |
| `API_PORT` | `8000` | Porta da API no host |
| `CONF_AUTO` | `0.85` | Confiança mínima para classificação automática |
| `CONF_MIN` | `0.50` | Abaixo disso o tipo vira `desconhecido` e vai para revisão |
| `CLASSIFICADOR` | `jev` | `jev` (Jev + Gemini) ou `regras` (sem rede) |
| `OPENROUTER_API_KEY` | vazio | Chave do OpenRouter (Jev). Só no `.env` |
| `JEV_MODEL` | vazio | Modelo do Jev. Testado com `typesafe/jev-1.13` |
| `GEMINI_API_KEY` | vazio | Chave do Google AI Studio. Só no `.env` |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Modelo da segunda opinião |

Também podem ser ajustadas por ambiente (valores em `app/config.py`, não listadas no `.env.example` nem repassadas pelo `docker-compose.yml` atual, então exigem editá-lo): `SEG_SIM_BAIXO`, `SEG_SIM_ALTO`, `SEG_LLM_CONTINUA`, `SEG_LLM_ABRE`, `LLM_TIMEOUT`, `LLM_TENTATIVAS`, `LLM_ESPERA`. As respostas dos LLMs são cacheadas em disco (volume `cache_llm`).

## Estado atual

| Item | Situação | Observação |
|---|---|---|
| Goal 1: início e fim de cada documento | Parcial | Cascata implementada (regras, TF-IDF, Jev na faixa ambígua, reconciliação). Limiares não calibrados. Não há correção de fronteiras na revisão |
| Goal 2: agrupamento de páginas | Parcial | Persistência de documentos e páginas e consulta por API prontas. Juntar e dividir documentos na revisão não existe. UI Streamlit fora do escopo por enquanto |
| Goal 3: classificação por tipo | Parcial | Jev + Gemini e classificador por regras funcionando. O baseline TF-IDF + regressão logística não está implementado |
| Goal 4: OCR pesquisável | Parcial | OCR e busca por texto no banco prontos. PDF pesquisável por documento não implementado: a busca é por texto no banco |
| Goal 5: confiança e revisão humana | Parcial | Roteamento por limiares, `GET /revisao` e `POST /documentos/{id}/revisao` prontos; `scripts/relatorio_cobertura.py` gera a curva cobertura x precisão. Limiares `CONF_AUTO=0,85` e `CONF_MIN=0,50` mantidos após a curva cobertura x precisão (ver Resultados). Sem tela de revisão |
| Goal 6: score de risco de ponto | Não implementado | Em desenvolvimento; não existe nesta branch (sem `worker_analise`, `analise_ponto` nem endpoint) |
| Goal 7: score de conformidade da empresa prestadora | Não implementado | Em desenvolvimento; não existe nesta branch (sem `documento_campos` nem `/lotes/{id}/conformidade`) |
| UI Streamlit | Não implementado | Fora do escopo por enquanto |
| `frontend/` | Esqueleto | Template inicial do Vite, separado do backend |

## Limitações

- Os dados sintéticos são otimistas. A validação em documentos reais (scans ruins, rotações, manuscritos) ainda é necessária.
- Um worker por fila: não há escala horizontal testada.
- Sem autenticação: qualquer cliente que alcance a API pode enviar, ler e revisar lotes. Não exponha a API fora de um ambiente local.
- Sem migrações: `sql/schema.sql` só vale em banco novo (ver `docker compose down -v`).
- Sem CI.
- O Jev e o Gemini recebem texto e imagem de páginas dos documentos. Use `CLASSIFICADOR=regras` se o conteúdo não puder sair da máquina.
- A confiança do classificador por regras é uma heurística sem calibração, usada só para roteamento.
- O sistema apoia a auditoria e não substitui parecer jurídico.

## Resultados

### Medições intermediárias (ajuste e treino) — NÃO são métricas finais

Dados do gerador sintético, em três conjuntos:

| Conjunto | Seed | Lotes | Páginas | Documentos | Uso |
|---|---|---|---|---|---|
| Ajuste | 101 | 5 | 36 | 30 | ajuste de regras e prompts |
| Treino | 202 | 20 | 204 | 159 | escolha de limiares e baseline |
| Teste | 303 | 10 | 97 | - | **não foi usado**; será medido uma única vez, no final |

Classificador Jev `typesafe/jev-1.13-20260917`. O Gemini deu segunda opinião em 3 documentos do treino e em nenhum do ajuste. Scripts: `scripts/avaliar_segmentacao.py`, `scripts/avaliar_classificacao.py` e `scripts/relatorio_cobertura.py`.

**Ajuste (30 documentos)**

- Segmentação: precisão das fronteiras 0,960, recall 0,960, documentos exatos 27/30 (0,900).
- Classificação com Jev: acurácia 0,967, F1 macro 0,992 (todos os documentos).
- Classificação com o classificador por regras: acurácia 0,867, F1 macro 0,810 (segmentação idêntica, 27/30).

**Treino (159 documentos no gabarito, 163 previstos)**

- Segmentação: precisão 0,909, recall 0,935, documentos exatos 134/159 (0,843).
- Jev: acurácia 0,969 e F1 macro 0,979 (todos os documentos); acurácia 0,963 e F1 macro 0,978 só nos 134 com segmentação exata.
- Estados: 146 classificados e 17 em revisão.

**Cobertura x precisão (Jev, treino, 163 documentos previstos)**

| Limiar | % automático | Precisão automática | % em revisão |
|---|---|---|---|
| 0,50 | 91,4 | 0,987 | 8,6 |
| 0,60 | 90,8 | 0,993 | 9,2 |
| 0,70 | 90,2 | 1,000 | 9,8 |
| 0,80 | 90,2 | 1,000 | 9,8 |
| 0,85 | 89,6 | 1,000 | 10,4 |
| 0,90 | 89,0 | 1,000 | 11,0 |
| 0,95 | 89,0 | 1,000 | 11,0 |

No ajuste (30 documentos) a curva é plana: 93,3% automático, precisão 1,000 e 6,7% em revisão em todos os limiares de 0,50 a 0,95, porque a confiança do Jev está saturada (26 de 30 com 1,00).

**Decisão:** `CONF_AUTO=0,85` e `CONF_MIN=0,50` foram mantidos. O limiar 0,70 é o menor com precisão automática 1,000, mas devolve ao automático só 1 de 163 documentos em relação a 0,85, diferença sem significância. `CONF_MIN` não foi escolhido pela curva, que não o mede. Os limiares foram avaliados no treino porque a curva do ajuste era plana. O treino também alimenta o baseline TF-IDF + regressão logística (`scripts/baseline_tfidf.py`, em PR separado; validação cruzada no treino com F1 macro 0,986, que não é métrica final), então o treino não é amostra independente para escolher limiares.

**Ressalvas**

- A segmentação foi pior no treino que no ajuste (0,843 contra 0,900 de documentos exatos), o que indica possível sobreajuste das regras ao ajuste.
- As amostras são pequenas.
- Os dados sintéticos são otimistas; a validação em documentos reais continua necessária.
- A confiança do classificador por regras é uma heurística sem calibração.

**Nota operacional:** para reclassificar um lote já concluído sem enviá-lo de novo (o upload é idempotente por SHA-256 e o worker ignora lotes `concluido`), mude o estado do lote para `recebido` no banco e reenfileire `segmentar_lote`. Isso apaga e refaz os documentos do lote. Não há endpoint para isso.

Os scripts de avaliação usam só a biblioteca padrão do Python. Rodam no host, contra a API em execução, com um `anotacoes.csv`:

```bash
python scripts/avaliar_segmentacao.py anotacoes.csv --api http://localhost:8000
python scripts/relatorio_cobertura.py anotacoes.csv --api http://localhost:8000
```

- `scripts/avaliar_segmentacao.py`: precisão e recall das fronteiras e fração de documentos exatos (início e fim), por documento.
- `scripts/relatorio_cobertura.py`: para cada limiar, % automático, precisão na parte automática e % em revisão.