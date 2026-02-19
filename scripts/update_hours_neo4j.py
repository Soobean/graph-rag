"""
Neo4j WORKS_ON 관계의 allocated_hours / actual_hours 일괄 업데이트

CSV에서 계산된 현실적 공수 데이터를 Neo4j에 반영합니다.
사전 조건: scripts/enrich_csv.py 실행 완료

실행: python scripts/update_hours_neo4j.py
"""

import csv
import os

from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "company_realistic")
CSV_FILE = os.path.join(DATA_DIR, "employee_project.csv")
BATCH_SIZE = 500


def load_csv() -> list[dict]:
    with open(CSV_FILE, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["allocated_hours"] = int(row["allocated_hours"])
        row["actual_hours"] = int(row["actual_hours"])
    return rows


def update_neo4j(rows: list[dict]):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    updated = 0
    not_found = 0

    with driver.session() as session:
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            result = session.run(
                """
                UNWIND $batch AS item
                MATCH (e:Employee {id: item.employee_id})-[w:WORKS_ON]->(p:Project {id: item.project_id})
                SET w.allocated_hours = item.allocated_hours,
                    w.actual_hours = item.actual_hours
                RETURN count(w) AS cnt
                """,
                batch=batch,
            )
            cnt = result.single()["cnt"]
            updated += cnt
            not_found += len(batch) - cnt
            print(f"  batch {i // BATCH_SIZE + 1}: {cnt}/{len(batch)} updated")

    driver.close()
    return updated, not_found


def print_stats(driver_uri, user, password):
    driver = GraphDatabase.driver(driver_uri, auth=(user, password))
    with driver.session() as session:
        result = session.run(
            """
            MATCH ()-[w:WORKS_ON]->()
            RETURN
                count(w) AS total,
                count(DISTINCT w.allocated_hours) AS alloc_unique,
                min(w.allocated_hours) AS alloc_min,
                max(w.allocated_hours) AS alloc_max,
                avg(w.allocated_hours) AS alloc_avg,
                count(DISTINCT w.actual_hours) AS actual_unique,
                min(w.actual_hours) AS actual_min,
                max(w.actual_hours) AS actual_max,
                avg(w.actual_hours) AS actual_avg
            """
        )
        row = result.single()
        print(f"\n{'─' * 50}")
        print(f"  WORKS_ON 관계 총 {row['total']}건")
        print(f"  allocated_hours: {row['alloc_unique']} unique values, "
              f"range [{row['alloc_min']}, {row['alloc_max']}], "
              f"avg {row['alloc_avg']:.0f}")
        print(f"  actual_hours:    {row['actual_unique']} unique values, "
              f"range [{row['actual_min']}, {row['actual_max']}], "
              f"avg {row['actual_avg']:.0f}")
        print(f"{'─' * 50}")
    driver.close()


def main():
    print("=" * 50)
    print(" Neo4j WORKS_ON 공수 업데이트")
    print("=" * 50)

    print(f"\nCSV 로드: {CSV_FILE}")
    rows = load_csv()
    print(f"  {len(rows)} rows loaded")

    print(f"\nNeo4j 업데이트 ({NEO4J_URI})...")
    updated, not_found = update_neo4j(rows)
    print(f"\n  Updated: {updated}, Not found: {not_found}")

    print("\n검증 통계:")
    print_stats(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    print("\n완료!")


if __name__ == "__main__":
    main()
