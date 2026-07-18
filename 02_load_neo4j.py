"""
02_load_neo4j.py
-----------------
Carga a Neo4j el dataset ampliado de OpenAlex: Person, Project, Skill,
Organization, Venue, y las relaciones WORKS_ON, REQUIRES_SKILL,
AFFILIATED_WITH, PUBLISHED_IN y CITES.

Uso:
    pip install -r requirements.txt
    Configurar credenciales en .env (ver .env.example)
    python 02_load_neo4j.py
"""

import os
import sys
import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD")

if not PASSWORD:
    sys.exit("Falta NEO4J_PASSWORD. Definila en un archivo .env (ver .env.example).")

DATA_DIR = "data"
BATCH_SIZE = 500


def batched(records, size):
    for i in range(0, len(records), size):
        yield records[i:i + size]


def create_constraints(tx):
    tx.run("CREATE CONSTRAINT person_id IF NOT EXISTS FOR (p:Person) REQUIRE p.person_id IS UNIQUE")
    tx.run("CREATE CONSTRAINT project_id IF NOT EXISTS FOR (p:Project) REQUIRE p.project_id IS UNIQUE")
    tx.run("CREATE CONSTRAINT skill_id IF NOT EXISTS FOR (s:Skill) REQUIRE s.skill_id IS UNIQUE")
    tx.run("CREATE CONSTRAINT org_id IF NOT EXISTS FOR (o:Organization) REQUIRE o.org_id IS UNIQUE")
    tx.run("CREATE CONSTRAINT venue_id IF NOT EXISTS FOR (v:Venue) REQUIRE v.venue_id IS UNIQUE")


def load_people(tx, rows):
    tx.run(
        """
        UNWIND $rows AS row
        MERGE (p:Person:Entity {person_id: row.person_id})
        SET p.name = row.name
        """,
        rows=rows,
    )


def load_projects(tx, rows):
    tx.run(
        """
        UNWIND $rows AS row
        MERGE (p:Project:Entity {project_id: row.project_id})
        SET p.title = row.title,
            p.year = toInteger(row.year),
            p.description = row.description
        """,
        rows=rows,
    )


def load_skills(tx, rows):
    tx.run(
        """
        UNWIND $rows AS row
        MERGE (s:Skill:Entity {skill_id: row.skill_id})
        SET s.name = row.name
        """,
        rows=rows,
    )


def load_organizations(tx, rows):
    tx.run(
        """
        UNWIND $rows AS row
        MERGE (o:Organization:Entity {org_id: row.org_id})
        SET o.name = row.name
        """,
        rows=rows,
    )


def load_venues(tx, rows):
    tx.run(
        """
        UNWIND $rows AS row
        MERGE (v:Venue:Entity {venue_id: row.venue_id})
        SET v.name = row.name
        """,
        rows=rows,
    )


def load_works_on(tx, rows):
    tx.run(
        """
        UNWIND $rows AS row
        MATCH (p:Person {person_id: row.person_id})
        MATCH (pr:Project {project_id: row.project_id})
        MERGE (p)-[:WORKS_ON]->(pr)
        """,
        rows=rows,
    )


def load_requires_skill(tx, rows):
    tx.run(
        """
        UNWIND $rows AS row
        MATCH (pr:Project {project_id: row.project_id})
        MATCH (s:Skill {skill_id: row.skill_id})
        MERGE (pr)-[r:REQUIRES_SKILL]->(s)
        SET r.score = toFloat(row.score)
        """,
        rows=rows,
    )


def load_affiliated_with(tx, rows):
    tx.run(
        """
        UNWIND $rows AS row
        MATCH (p:Person {person_id: row.person_id})
        MATCH (o:Organization {org_id: row.org_id})
        MERGE (p)-[:AFFILIATED_WITH]->(o)
        """,
        rows=rows,
    )


def load_published_in(tx, rows):
    tx.run(
        """
        UNWIND $rows AS row
        MATCH (pr:Project {project_id: row.project_id})
        MATCH (v:Venue {venue_id: row.venue_id})
        MERGE (pr)-[:PUBLISHED_IN]->(v)
        """,
        rows=rows,
    )


def load_cites(tx, rows):
    tx.run(
        """
        UNWIND $rows AS row
        MATCH (p1:Project {project_id: row.project_id})
        MATCH (p2:Project {project_id: row.cited_id})
        MERGE (p1)-[:CITES]->(p2)
        """,
        rows=rows,
    )


def run_batched(session, csv_path, fn, label):
    df = pd.read_csv(csv_path).fillna("")
    rows = df.to_dict("records")
    total = len(rows)
    if total == 0:
        print(f"  {label}: 0 filas, se salta")
        return
    done = 0
    for batch in batched(rows, BATCH_SIZE):
        session.execute_write(fn, batch)
        done += len(batch)
        print(f"  {label}: {done}/{total}")


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    with driver.session() as session:
        print("Creando constraints...")
        session.execute_write(create_constraints)

        print("\nCargando Person...")
        run_batched(session, f"{DATA_DIR}/people.csv", load_people, "Person")

        print("\nCargando Project...")
        run_batched(session, f"{DATA_DIR}/projects.csv", load_projects, "Project")

        print("\nCargando Skill...")
        run_batched(session, f"{DATA_DIR}/skills.csv", load_skills, "Skill")

        print("\nCargando Organization...")
        run_batched(session, f"{DATA_DIR}/organizations.csv", load_organizations, "Organization")

        print("\nCargando Venue...")
        run_batched(session, f"{DATA_DIR}/venues.csv", load_venues, "Venue")

        print("\nCargando relaciones WORKS_ON...")
        run_batched(session, f"{DATA_DIR}/rel_works_on.csv", load_works_on, "WORKS_ON")

        print("\nCargando relaciones REQUIRES_SKILL...")
        run_batched(session, f"{DATA_DIR}/rel_requires_skill.csv", load_requires_skill, "REQUIRES_SKILL")

        print("\nCargando relaciones AFFILIATED_WITH...")
        run_batched(session, f"{DATA_DIR}/rel_affiliated_with.csv", load_affiliated_with, "AFFILIATED_WITH")

        print("\nCargando relaciones PUBLISHED_IN...")
        run_batched(session, f"{DATA_DIR}/rel_published_in.csv", load_published_in, "PUBLISHED_IN")

        print("\nCargando relaciones CITES...")
        run_batched(session, f"{DATA_DIR}/rel_cites.csv", load_cites, "CITES")

    driver.close()
    print("\n¡Listo! Grafo ampliado cargado en Neo4j.")


if __name__ == "__main__":
    main()