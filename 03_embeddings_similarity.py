"""
03_embeddings_similarity.py
----------------------------
Paso equivalente al que hizo NASA con "cosine similarity" entre proyectos.

Qué hace:
1. Trae todos los :Project de Neo4j (title + description)
2. Genera un embedding (vector semántico) de cada descripción usando
   un modelo local y gratuito (sentence-transformers, no requiere API key)
3. Guarda ese embedding como propiedad del nodo
4. Calcula similitud coseno entre TODOS los pares de proyectos
5. Crea la relación (:Project)-[:SIMILAR_TO {score}]->(:Project)
   para los pares que superan un umbral (proyectos "casi duplicados"
   o muy relacionados temáticamente)
6. Crea un índice vectorial sobre :Entity para poder hacer búsqueda
   semántica rápida en el paso de GraphRAG


"""

import os
import sys
import numpy as np
from dotenv import load_dotenv
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer

load_dotenv()

URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD")

if not PASSWORD:
    sys.exit("Falta NEO4J_PASSWORD. Definila en un archivo .env (ver .env.example).")

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
SIMILARITY_THRESHOLD = 0.75


def fetch_projects(session):
    result = session.run(
        """
        MATCH (p:Project)
        RETURN p.project_id AS project_id,
               p.title AS title,
               p.description AS description
        """
    )
    return [dict(record) for record in result]


def save_embeddings(session, rows):
    session.execute_write(
        lambda tx: tx.run(
            """
            UNWIND $rows AS row
            MATCH (p:Project {project_id: row.project_id})
            SET p.embedding = row.embedding
            """,
            rows=rows,
        )
    )


def create_similar_to(session, rows):
    session.execute_write(
        lambda tx: tx.run(
            """
            UNWIND $rows AS row
            MATCH (p1:Project {project_id: row.id1})
            MATCH (p2:Project {project_id: row.id2})
            MERGE (p1)-[r:SIMILAR_TO]->(p2)
            SET r.score = row.score
            """,
            rows=rows,
        )
    )


def create_vector_index(session):
    session.run(
        f"""
        CREATE VECTOR INDEX entity_embeddings IF NOT EXISTS
        FOR (n:Entity) ON (n.embedding)
        OPTIONS {{
            indexConfig: {{
                `vector.dimensions`: {EMBEDDING_DIM},
                `vector.similarity_function`: 'cosine'
            }}
        }}
        """
    )


def cosine_sim_matrix(vectors):
    norm = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    return norm @ norm.T


def main():
    print(f"Cargando modelo de embeddings ({MODEL_NAME})...")
    model = SentenceTransformer(MODEL_NAME)

    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    with driver.session() as session:
        print("Trayendo proyectos desde Neo4j...")
        projects = fetch_projects(session)
        print(f"  {len(projects)} proyectos encontrados")

        # Usamos título + descripción para el embedding (más contexto)
        texts = [
            f"{p['title']}. {p['description'] or ''}" for p in projects
        ]

        print("Generando embeddings (puede tardar un minuto)...")
        embeddings = model.encode(texts, show_progress_bar=True)

        # Guardar embeddings como propiedad de cada nodo
        rows = [
            {"project_id": p["project_id"], "embedding": emb.tolist()}
            for p, emb in zip(projects, embeddings)
        ]
        print("Guardando embeddings en Neo4j...")
        save_embeddings(session, rows)

        # Calcular similitud coseno entre todos los pares
        print("Calculando similitud entre proyectos...")
        sim_matrix = cosine_sim_matrix(np.array(embeddings))

        n = len(projects)
        similar_pairs = []
        for i in range(n):
            for j in range(i + 1, n):  # evita duplicados y auto-comparación
                score = float(sim_matrix[i][j])
                if score >= SIMILARITY_THRESHOLD:
                    similar_pairs.append({
                        "id1": projects[i]["project_id"],
                        "id2": projects[j]["project_id"],
                        "score": score,
                    })

        print(f"  {len(similar_pairs)} pares superan el umbral de {SIMILARITY_THRESHOLD}")

        if similar_pairs:
            print("Creando relaciones SIMILAR_TO...")
            create_similar_to(session, similar_pairs)

        print("Creando índice vectorial (entity_embeddings)...")
        create_vector_index(session)

    driver.close()
    print("\n¡Listo! Embeddings, SIMILAR_TO e índice vectorial creados.")
    print("Probá en el Query tool:")
    print("  MATCH (p1:Project)-[r:SIMILAR_TO]->(p2:Project)")
    print("  RETURN p1.title, p2.title, r.score ORDER BY r.score DESC LIMIT 10")


if __name__ == "__main__":
    main()