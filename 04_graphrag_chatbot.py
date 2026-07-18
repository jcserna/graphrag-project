"""
04_graphrag_chatbot.py
------------------------
Chatbot GraphRAG sobre grafo de Neo4j, replicando el flujo que describió
NASA en el artículo:

    1. Pregunta del usuario -> embedding
    2. Búsqueda vectorial en Neo4j -> nodos más relevantes ("pivot search")
    3. Expansión 1 salto en el grafo desde esos nodos -> "context triplets"
    4. Se le pasan los triplets + la pregunta original a un LLM (acá: Gemini,
       gratis via Google AI Studio) -> respuesta final en lenguaje natural

Uso:
    pip install -r requirements.txt

    1) Obtener una API key gratuita en https://aistudio.google.com/app/apikey
    2) Configurar credenciales en .env (ver .env.example)
    3) python 04_graphrag_chatbot.py
"""

import os
import sys
import logging
import textwrap
from dotenv import load_dotenv
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer
from google import genai

load_dotenv()

# Los warnings de deprecación del driver de Neo4j son informativos y no
# afectan el resultado; se silencian para mantener la salida legible.
logging.getLogger("neo4j").setLevel(logging.ERROR)

WRAP_WIDTH = 100  # ancho fijo de línea, independiente del tamaño de la terminal


def wrap(text):
    return "\n".join(
        textwrap.fill(line, WRAP_WIDTH) for line in text.split("\n")
    )


# ---------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------
URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not PASSWORD or not GEMINI_API_KEY:
    sys.exit(
        "Faltan credenciales. Definí NEO4J_PASSWORD y GEMINI_API_KEY en un "
        "archivo .env (ver .env.example)."
    )

GEMINI_MODEL = "gemini-flash-latest"   # alias que siempre apunta al Flash vigente, evita romperse cuando Google retira versiones

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
TOP_K = 150           # cuántos nodos trae la búsqueda vectorial inicial
HOPS_LIMIT = 8       # cuántas relaciones vecinas trae por cada nodo relevante


def vector_search(session, query_embedding, k=TOP_K):
    result = session.run(
        """
        CALL db.index.vector.queryNodes('entity_embeddings', $k, $embedding)
        YIELD node, score
        RETURN node.project_id AS project_id,
               labels(node) AS labels,
               coalesce(node.title, node.name) AS name,
               score
        """,
        k=k,
        embedding=query_embedding,
    )
    return [dict(r) for r in result]


def expand_context(session, project_ids):
    """Trae 'context triplets': nodo relevante -[relación]-> vecino, en ambas
    direcciones, hasta HOPS_LIMIT por nodo."""
    result = session.run(
        """
        UNWIND $ids AS pid
        MATCH (start:Project {project_id: pid})
        OPTIONAL MATCH (start)-[r]-(neighbor)
        WITH start, r, neighbor
        LIMIT $limit
        RETURN start.title AS start_name,
               type(r) AS relation,
               coalesce(neighbor.name, neighbor.title) AS neighbor_name,
               labels(neighbor) AS neighbor_labels
        """,
        ids=project_ids,
        limit=HOPS_LIMIT * len(project_ids),
    )
    triplets = []
    for r in result:
        if r["relation"] is None:
            continue
        neighbor_type = [l for l in r["neighbor_labels"] if l != "Entity"]
        neighbor_type = neighbor_type[0] if neighbor_type else "Nodo"
        triplets.append(
            f"({r['start_name']}) -[{r['relation']}]-> ({neighbor_type}: {r['neighbor_name']})"
        )
    return triplets


def build_prompt(question, triplets):
    context = "\n".join(triplets) if triplets else "(sin contexto relevante encontrado)"
    return f"""Eres un asistente que responde preguntas usando ÚNICAMENTE la información
de contexto extraída de un grafo de conocimiento académico sobre IA aplicada a
exploración espacial. No inventes datos que no estén en el contexto.

Contexto (tripletas nodo-relación-nodo extraídas del grafo):
{context}

Pregunta: {question}

Responde en español, de forma clara y concisa, citando los nombres de proyectos,
personas o skills relevantes que aparecen en el contexto."""


def ask_llm(client, prompt):
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    return response.text


def main():
    print("Cargando modelo de embeddings...")
    embed_model = SentenceTransformer(EMBEDDING_MODEL)

    print("Conectando a Neo4j...")
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    print("Conectando a Gemini...")
    client = genai.Client(api_key=GEMINI_API_KEY)

    print("\nEscribe una pregunta sobre los proyectos del grafo (o 'salir').\n")

    with driver.session() as session:
        while True:
            question = input("Pregunta> ").strip()
            if question.lower() in ("salir", "exit", "quit"):
                break
            if not question:
                continue

            # 1) Embedding de la pregunta
            q_embedding = embed_model.encode(question).tolist()

            # 2) Búsqueda vectorial ("pivot search")
            hits = vector_search(session, q_embedding)
            project_ids = [h["project_id"] for h in hits if h["project_id"]]

            if not project_ids:
                print("No encontré proyectos relevantes en el grafo.\n")
                continue

            print(f"  (nodos relevantes encontrados: {[h['name'] for h in hits]})")

            # 3) Expansión de contexto
            triplets = expand_context(session, project_ids)

            # 4) LLM con contexto
            prompt = build_prompt(question, triplets)
            answer = ask_llm(client, prompt)

            print(f"\nRespuesta:\n{wrap(answer)}\n")

    driver.close()


if __name__ == "__main__":
    main()