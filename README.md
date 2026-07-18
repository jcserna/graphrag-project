# Grafo de Conocimiento Académico con GraphRAG

Réplica académica a escala reducida del *People Knowledge Graph* de NASA, construida con **Neo4j**, **OpenAlex** y **Google Gemini**.

> Proyecto académico — Maestría en Big Data y Ciencia de Datos (2026)

## Motivación

Este proyecto replica, a escala académica, la iniciativa *People Knowledge Graph* desarrollada por el equipo de People Analytics de NASA (presentada en un community call organizado por Memgraph en abril de 2025), donde se construyó un grafo de conocimiento que conecta empleados, proyectos y habilidades para identificar expertos internos, detectar proyectos similares y responder preguntas organizacionales mediante un chatbot GraphRAG.

Al no contar con datos propios de una organización, se construyó un grafo análogo con datos **públicos y reales** extraídos de [OpenAlex](https://openalex.org), sobre el dominio "inteligencia artificial aplicada a la exploración espacial".

El objetivo no es un estudio bibliométrico riguroso, sino aprender de forma práctica el diseño de un grafo de conocimiento en Neo4j y la implementación de un pipeline GraphRAG completo, incluyendo sus capacidades y limitaciones reales.

El informe completo, con metodología, resultados y análisis crítico de limitaciones, está en [`Informe_GraphRAG.docx`](Informe_GraphRAG.docx).

## Esquema del grafo

![Esquema del grafo](images/schema_visualisation.png)

| Nodo | Origen del dato | Propiedades principales |
|---|---|---|
| `Person` | `authorships.author` | `person_id`, `name` |
| `Project` | work (paper) | `project_id`, `title`, `year`, `description`, `embedding` |
| `Skill` | `concepts` | `skill_id`, `name` |
| `Organization` | `authorships.institutions` | `org_id`, `name` |
| `Venue` | `primary_location.source` | `venue_id`, `name` |

Todos los nodos comparten además la etiqueta genérica `Entity`, lo que permite un único índice vectorial sobre la totalidad del grafo.

| Relación | Desde → Hacia | Propiedad |
|---|---|---|
| `WORKS_ON` | Person → Project | — |
| `REQUIRES_SKILL` | Project → Skill | `score` |
| `AFFILIATED_WITH` | Person → Organization | — |
| `PUBLISHED_IN` | Project → Venue | — |
| `CITES` | Project → Project | — |
| `SIMILAR_TO` | Project → Project | `score` (similitud coseno) |

## Pipeline

1. **`01_fetch_data.py`** — Descarga papers públicos de OpenAlex (búsqueda: *"artificial intelligence space exploration"*) y genera los CSV en `data/`.
2. **`02_load_neo4j.py`** — Carga los CSV a Neo4j (nodos, relaciones y constraints de unicidad).
3. **`03_embeddings_similarity.py`** — Genera embeddings de cada `Project` con `all-MiniLM-L6-v2` (local, sin API key), calcula similitud coseno entre proyectos, crea la relación `SIMILAR_TO` y el índice vectorial `entity_embeddings`.
4. **`04_graphrag_chatbot.py`** — Chatbot GraphRAG: embedding de la pregunta → búsqueda vectorial ("pivot search") → expansión de un salto en el grafo ("context triplets") → respuesta generada por Gemini usando solo ese contexto.

## Instalación

```bash
git clone <url-del-repo>
cd graphrag-project
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

Requiere una instancia de Neo4j corriendo localmente (por ejemplo, Neo4j Desktop) con soporte de índices vectoriales.

### Credenciales

Copiar `.env.example` a `.env` y completar con tus propios valores:

```bash
copy .env.example .env
```

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=tu_contraseña
GEMINI_API_KEY=tu_api_key       # gratis en https://aistudio.google.com/app/apikey
```

`.env` está excluido del repositorio vía `.gitignore` — nunca subir credenciales reales.

## Uso

```bash
python 01_fetch_data.py
python 02_load_neo4j.py
python 03_embeddings_similarity.py
python 04_graphrag_chatbot.py
```

## Resultados y limitaciones (resumen)

El sistema tiene buen desempeño en preguntas temáticas y de búsqueda de talento con razonamiento sobre estructura de grafo (usando relaciones como `CITES` o `SIMILAR_TO` para justificar respuestas). Muestra limitaciones claras en preguntas de **agregación global** ("¿quién participa en más proyectos?"), ya que la búsqueda vectorial solo expone al modelo una porción local del grafo — este tipo de preguntas se resuelve mejor con consultas Cypher directas. El detalle completo, con capturas de cada caso, está en el informe y en [`images/`](images/).

## Fuentes de datos y herramientas

- [OpenAlex](https://openalex.org) — índice académico abierto (datos públicos, sin autenticación).
- [Neo4j](https://neo4j.com) — base de datos orientada a grafos.
- [Sentence-Transformers](https://www.sbert.net) (`all-MiniLM-L6-v2`) — embeddings locales y gratuitos.
- [Google AI Studio / Gemini](https://aistudio.google.com) — LLM usado para generar las respuestas del chatbot.

## Referencias

- Tasneem, S. (2025). *How NASA is Using Graph Technology and LLMs to Build a People Knowledge Graph*. Memgraph Blog. https://memgraph.com/blog/nasa-memgraph-people-knowledge-graph
