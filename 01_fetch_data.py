"""
01_fetch_data.py
-----------------
Descarga datos PÚBLICOS y REALES de OpenAlex (https://openalex.org).

Tema: inteligencia artificial aplicada a exploración espacial.

Esquema resultante:
    (:Person)-[:WORKS_ON]->(:Project)
    (:Project)-[:REQUIRES_SKILL {score}]->(:Skill)
    (:Person)-[:AFFILIATED_WITH]->(:Organization)
    (:Project)-[:PUBLISHED_IN]->(:Venue)
    (:Project)-[:CITES]->(:Project)   <- solo entre papers que ya están en el dataset

Salida: CSVs en ./data/
    people.csv, projects.csv, skills.csv, organizations.csv, venues.csv
    rel_works_on.csv, rel_requires_skill.csv, rel_affiliated_with.csv,
    rel_published_in.csv, rel_cites.csv

Uso:
    pip install requests pandas
    python 01_fetch_data.py
"""

import requests
import pandas as pd
import time
import os

SEARCH_QUERY = "artificial intelligence space exploration"
MAX_WORKS = 150
PER_PAGE = 50
OUTPUT_DIR = "data"
MAILTO = "student@example.com"

BASE_URL = "https://api.openalex.org/works"


def reconstruct_abstract(inverted_index):
    if not inverted_index:
        return ""
    positions = {}
    for word, idxs in inverted_index.items():
        for idx in idxs:
            positions[idx] = word
    ordered = [positions[i] for i in sorted(positions.keys())]
    return " ".join(ordered)


def fetch_works():
    works = []
    cursor = "*"
    fetched = 0

    while fetched < MAX_WORKS:
        params = {
            "search": SEARCH_QUERY,
            "per-page": PER_PAGE,
            "cursor": cursor,
            "mailto": MAILTO,
        }
        resp = requests.get(BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        batch = data.get("results", [])
        if not batch:
            break

        works.extend(batch)
        fetched += len(batch)
        cursor = data.get("meta", {}).get("next_cursor")

        print(f"  descargados {fetched} papers...")
        if not cursor:
            break
        time.sleep(0.2)

    return works[:MAX_WORKS]


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Buscando papers sobre: '{SEARCH_QUERY}'")
    works = fetch_works()
    print(f"Total papers obtenidos: {len(works)}")

    people = {}
    projects = []
    skills = {}
    organizations = {}
    venues = {}

    rel_works_on = []
    rel_requires_skill = []
    rel_affiliated_with = []
    rel_published_in = []
    rel_cites_raw = []  # (project_id, referenced_work_id) -- se filtra al final

    project_ids = set()

    for w in works:
        project_id = w["id"]
        project_ids.add(project_id)

        title = w.get("title") or ""
        year = w.get("publication_year")
        abstract = reconstruct_abstract(w.get("abstract_inverted_index"))

        projects.append({
            "project_id": project_id,
            "title": title,
            "year": year,
            "description": abstract[:2000],
        })

        # --- Autores (Person) + Organización (Organization) ---
        for authorship in w.get("authorships", []):
            author = authorship.get("author", {})
            author_id = author.get("id")
            author_name = author.get("display_name")
            if not author_id or not author_name:
                continue

            if author_id not in people:
                people[author_id] = {"person_id": author_id, "name": author_name}

            rel_works_on.append({"person_id": author_id, "project_id": project_id})

            for inst in authorship.get("institutions", []):
                org_id = inst.get("id")
                org_name = inst.get("display_name")
                if not org_id or not org_name:
                    continue
                if org_id not in organizations:
                    organizations[org_id] = org_name
                rel_affiliated_with.append({"person_id": author_id, "org_id": org_id})

        # --- Skills (conceptos) ---
        for concept in w.get("concepts", []):
            concept_id = concept.get("id")
            concept_name = concept.get("display_name")
            score = concept.get("score", 0)
            if not concept_id or not concept_name or score < 0.3:
                continue
            if concept_id not in skills:
                skills[concept_id] = concept_name
            rel_requires_skill.append({
                "project_id": project_id,
                "skill_id": concept_id,
                "score": score,
            })

        # --- Venue (revista / conferencia) ---
        primary_location = w.get("primary_location") or {}
        source = primary_location.get("source") or {}
        venue_id = source.get("id")
        venue_name = source.get("display_name")
        if venue_id and venue_name:
            if venue_id not in venues:
                venues[venue_id] = venue_name
            rel_published_in.append({"project_id": project_id, "venue_id": venue_id})

        # --- Citas (se filtran después de tener todos los project_ids) ---
        for ref_id in w.get("referenced_works", []):
            rel_cites_raw.append({"project_id": project_id, "cited_id": ref_id})

    # Solo nos quedamos con citas donde el paper citado TAMBIÉN está en nuestro dataset
    rel_cites = [
        r for r in rel_cites_raw if r["cited_id"] in project_ids
    ]

    # ---------------------------------------------------------------
    # Guardar CSVs
    # ---------------------------------------------------------------
    pd.DataFrame(people.values()).to_csv(f"{OUTPUT_DIR}/people.csv", index=False)
    pd.DataFrame(projects).to_csv(f"{OUTPUT_DIR}/projects.csv", index=False)
    pd.DataFrame(
        [{"skill_id": k, "name": v} for k, v in skills.items()]
    ).to_csv(f"{OUTPUT_DIR}/skills.csv", index=False)
    pd.DataFrame(
        [{"org_id": k, "name": v} for k, v in organizations.items()]
    ).to_csv(f"{OUTPUT_DIR}/organizations.csv", index=False)
    pd.DataFrame(
        [{"venue_id": k, "name": v} for k, v in venues.items()]
    ).to_csv(f"{OUTPUT_DIR}/venues.csv", index=False)

    pd.DataFrame(rel_works_on).drop_duplicates().to_csv(f"{OUTPUT_DIR}/rel_works_on.csv", index=False)
    pd.DataFrame(rel_requires_skill).drop_duplicates().to_csv(f"{OUTPUT_DIR}/rel_requires_skill.csv", index=False)
    pd.DataFrame(rel_affiliated_with).drop_duplicates().to_csv(f"{OUTPUT_DIR}/rel_affiliated_with.csv", index=False)
    pd.DataFrame(rel_published_in).drop_duplicates().to_csv(f"{OUTPUT_DIR}/rel_published_in.csv", index=False)
    pd.DataFrame(rel_cites).drop_duplicates().to_csv(f"{OUTPUT_DIR}/rel_cites.csv", index=False)

    print("\nListo. Resumen:")
    print(f"  Personas:                {len(people)}")
    print(f"  Proyectos:               {len(projects)}")
    print(f"  Skills:                  {len(skills)}")
    print(f"  Organizaciones:          {len(organizations)}")
    print(f"  Venues:                  {len(venues)}")
    print(f"  Relaciones WORKS_ON:     {len(rel_works_on)}")
    print(f"  Relaciones REQUIRES_SKILL: {len(rel_requires_skill)}")
    print(f"  Relaciones AFFILIATED_WITH: {len(rel_affiliated_with)}")
    print(f"  Relaciones PUBLISHED_IN: {len(rel_published_in)}")
    print(f"  Relaciones CITES (internas al dataset): {len(rel_cites)}")
    print(f"\nCSVs guardados en ./{OUTPUT_DIR}/")


if __name__ == "__main__":
    main()