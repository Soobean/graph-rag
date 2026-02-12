"""
CSV 데이터를 Neo4j에 로드하는 스크립트
LOAD CSV 방식으로 빠르게 데이터 적재

파생 필드는 CSV에 사전 계산됨 (scripts/enrich_csv.py).
이 스크립트는 CSV 컬럼을 그대로 읽어서 Neo4j에 적재만 수행.
유일한 예외: Employee.availability는 관계 로드 후 post-load로 계산.
"""

from neo4j import GraphDatabase

# Neo4j 연결 설정
URI = "bolt://localhost:7687"
AUTH = ("neo4j", "password123")


def run_query(driver, query, params=None):
    """Cypher 쿼리 실행"""
    with driver.session() as session:
        result = session.run(query, params or {})
        return result.consume()


def clear_database(driver):
    """기존 데이터 삭제"""
    print("\n[0/10] 기존 데이터 삭제 중...")
    run_query(driver, "MATCH (n) DETACH DELETE n")
    print("  ✓ 완료")


def create_constraints(driver):
    """인덱스 및 제약조건 생성"""
    print("\n[1/10] 인덱스 및 제약조건 생성 중...")

    constraints = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Employee) REQUIRE e.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Department) REQUIRE d.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Skill) REQUIRE s.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Project) REQUIRE p.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (o:Office) REQUIRE o.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (pos:Position) REQUIRE pos.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (cert:Certificate) REQUIRE cert.id IS UNIQUE",
    ]

    for constraint in constraints:
        try:
            run_query(driver, constraint)
        except Exception:
            pass

    indexes = [
        "CREATE INDEX employee_name IF NOT EXISTS FOR (e:Employee) ON (e.name)",
        "CREATE INDEX department_name IF NOT EXISTS FOR (d:Department) ON (d.name)",
        "CREATE INDEX skill_name IF NOT EXISTS FOR (s:Skill) ON (s.name)",
        "CREATE INDEX project_name IF NOT EXISTS FOR (p:Project) ON (p.name)",
        "CREATE INDEX office_name IF NOT EXISTS FOR (o:Office) ON (o.name)",
        "CREATE INDEX position_name IF NOT EXISTS FOR (pos:Position) ON (pos.name)",
        "CREATE INDEX certificate_name IF NOT EXISTS FOR (cert:Certificate) ON (cert.name)",
        "CREATE INDEX skill_category IF NOT EXISTS FOR (s:Skill) ON (s.category)",
        "CREATE INDEX project_type IF NOT EXISTS FOR (p:Project) ON (p.type)",
        "CREATE INDEX project_status IF NOT EXISTS FOR (p:Project) ON (p.status)",
    ]

    for idx in indexes:
        try:
            run_query(driver, idx)
        except Exception:
            pass

    print("  ✓ 완료")


def load_nodes(driver):
    """기본 노드 데이터 로드 (Office, Department, Position, Skill, Certificate)"""

    # 1. Office
    print("\n[2/10] Office 노드 로드 중...")
    run_query(driver, """
    LOAD CSV WITH HEADERS FROM 'file:///offices.csv' AS row
    CREATE (o:Office {
        id: row.id, name: row.name, city: row.city, address: row.address
    })
    """)
    print("  ✓ 완료")

    # 2. Department + Office 관계
    print("\n[3/10] Department 노드 로드 중...")
    run_query(driver, """
    LOAD CSV WITH HEADERS FROM 'file:///departments.csv' AS row
    CREATE (d:Department {
        id: row.id, name: row.name,
        head_count: toInteger(row.head_count),
        budget_billion: toFloat(row.budget_billion)
    })
    WITH d, row
    MATCH (o:Office {id: row.office_id})
    CREATE (d)-[:LOCATED_AT]->(o)
    """)
    print("  ✓ 완료")

    # 3. Position
    print("\n[4/10] Position 노드 로드 중...")
    run_query(driver, """
    LOAD CSV WITH HEADERS FROM 'file:///positions.csv' AS row
    CREATE (p:Position {
        id: row.id, name: row.name,
        level: toInteger(row.level),
        min_years: toInteger(row.min_years),
        max_years: toInteger(row.max_years)
    })
    """)
    print("  ✓ 완료")

    # 4. Skill (파생 필드: hourly_rate_min/max, market_demand → CSV에서 직접 읽기)
    print("\n[5/10] Skill 노드 로드 중...")
    run_query(driver, """
    LOAD CSV WITH HEADERS FROM 'file:///skills.csv' AS row
    CREATE (s:Skill {
        id: row.id, name: row.name,
        category: row.category, difficulty: row.difficulty,
        hourly_rate_min: toInteger(row.hourly_rate_min),
        hourly_rate_max: toInteger(row.hourly_rate_max),
        market_demand: row.market_demand
    })
    """)
    print("  ✓ 완료")

    # 5. Certificate
    print("\n[6/10] Certificate 노드 로드 중...")
    run_query(driver, """
    LOAD CSV WITH HEADERS FROM 'file:///certificates.csv' AS row
    CREATE (c:Certificate {
        id: row.id, name: row.name,
        issuer: row.issuer, category: row.category
    })
    """)
    print("  ✓ 완료")


def load_employees(driver):
    """Employee 노드 로드 (파생 필드: hourly_rate, max_projects, department → CSV에서 직접 읽기)"""
    print("\n[7/10] Employee 노드 로드 중...")

    run_query(driver, """
    LOAD CSV WITH HEADERS FROM 'file:///employees.csv' AS row
    CREATE (e:Employee {
        id: row.id, name: row.name, email: row.email,
        job_type: row.job_type,
        years_experience: toInteger(row.years_experience),
        hire_date: row.hire_date,
        hourly_rate: toInteger(row.hourly_rate),
        max_projects: toInteger(row.max_projects),
        department: row.department
    })
    WITH e, row
    MATCH (d:Department {id: row.department_id})
    MATCH (p:Position {id: row.position_id})
    CREATE (e)-[:BELONGS_TO]->(d)
    CREATE (e)-[:HAS_POSITION]->(p)
    """)
    print("  ✓ 완료")


def load_projects(driver):
    """Project 노드 로드 (파생 필드: budget_allocated/spent, duration 등 → CSV에서 직접 읽기)"""
    print("\n[8/10] Project 노드 로드 중...")

    run_query(driver, """
    LOAD CSV WITH HEADERS FROM 'file:///projects.csv' AS row
    CREATE (p:Project {
        id: row.id, name: row.name, type: row.type,
        status: row.status, start_date: row.start_date,
        budget_million: toInteger(row.budget_million),
        budget_allocated: toInteger(row.budget_allocated),
        budget_spent: toInteger(row.budget_spent),
        duration_months: toInteger(row.duration_months),
        estimated_hours: toInteger(row.estimated_hours),
        required_headcount: toInteger(row.required_headcount)
    })
    WITH p, row
    MATCH (d:Department {id: row.dept_id})
    CREATE (p)-[:OWNED_BY]->(d)
    """)
    print("  ✓ 완료")


def load_relationships(driver):
    """관계 데이터 로드 (파생 필드 모두 CSV에서 직접 읽기)"""
    print("\n[9/10] 관계 데이터 로드 중...")

    # HAS_SKILL (파생: rate_factor, effective_rate)
    print("  - Employee-Skill 관계...")
    run_query(driver, """
    LOAD CSV WITH HEADERS FROM 'file:///employee_skill.csv' AS row
    MATCH (e:Employee {id: row.employee_id})
    MATCH (s:Skill {id: row.skill_id})
    CREATE (e)-[:HAS_SKILL {
        proficiency: row.proficiency,
        years_used: toInteger(row.years_used),
        rate_factor: toFloat(row.rate_factor),
        effective_rate: toInteger(row.effective_rate)
    }]->(s)
    """)

    # WORKS_ON (파생: agreed_rate, allocated_hours, actual_hours)
    print("  - Employee-Project 관계...")
    run_query(driver, """
    LOAD CSV WITH HEADERS FROM 'file:///employee_project.csv' AS row
    MATCH (e:Employee {id: row.employee_id})
    MATCH (p:Project {id: row.project_id})
    CREATE (e)-[:WORKS_ON {
        role: row.role,
        contribution_percent: toInteger(row.contribution_percent),
        agreed_rate: toInteger(row.agreed_rate),
        allocated_hours: toInteger(row.allocated_hours),
        actual_hours: toInteger(row.actual_hours)
    }]->(p)
    """)

    # REQUIRES (파생: required_proficiency, required_headcount, max_hourly_rate, priority)
    print("  - Project-Skill 관계...")
    run_query(driver, """
    LOAD CSV WITH HEADERS FROM 'file:///project_skill.csv' AS row
    MATCH (p:Project {id: row.project_id})
    MATCH (s:Skill {id: row.skill_id})
    CREATE (p)-[:REQUIRES {
        importance: row.importance,
        required_proficiency: row.required_proficiency,
        required_headcount: toInteger(row.required_headcount),
        max_hourly_rate: toInteger(row.max_hourly_rate),
        priority: toInteger(row.priority)
    }]->(s)
    """)

    # HAS_CERTIFICATE
    print("  - Employee-Certificate 관계...")
    run_query(driver, """
    LOAD CSV WITH HEADERS FROM 'file:///employee_certificate.csv' AS row
    MATCH (e:Employee {id: row.employee_id})
    MATCH (c:Certificate {id: row.certificate_id})
    CREATE (e)-[:HAS_CERTIFICATE {
        acquired_date: row.acquired_date
    }]->(c)
    """)

    # MENTORS
    print("  - Mentorship 관계...")
    run_query(driver, """
    LOAD CSV WITH HEADERS FROM 'file:///mentorship.csv' AS row
    MATCH (mentor:Employee {id: row.mentor_id})
    MATCH (mentee:Employee {id: row.mentee_id})
    CREATE (mentor)-[:MENTORS {
        start_date: row.start_date
    }]->(mentee)
    """)

    print("  ✓ 모든 관계 로드 완료")


def set_employee_availability(driver):
    """Employee.availability 설정 (활성 프로젝트 수 기반 — 유일한 post-load 계산)"""
    print("\n[10/10] Employee availability 설정 중...")

    run_query(driver, """
    MATCH (e:Employee)
    OPTIONAL MATCH (e)-[:WORKS_ON]->(p:Project)
    WHERE p.status IN ['진행중', '계획']
    WITH e, count(p) AS active_count
    SET e.availability = CASE
      WHEN active_count >= e.max_projects THEN 'unavailable'
      WHEN active_count >= e.max_projects - 1 THEN 'partial'
      ELSE 'available' END
    """)
    print("  ✓ 완료")


def verify_data(driver):
    """데이터 검증"""
    print("\n" + "=" * 60)
    print(" 데이터 검증")
    print("=" * 60)

    with driver.session() as session:
        result = session.run(
            "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY count DESC"
        )
        print("\n[노드 통계]")
        total_nodes = 0
        for record in result:
            print(f"  {record['label']}: {record['count']}개")
            total_nodes += record["count"]
        print(f"  --------\n  총 노드: {total_nodes}개")

        result = session.run(
            "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY count DESC"
        )
        print("\n[관계 통계]")
        total_edges = 0
        for record in result:
            print(f"  {record['type']}: {record['count']}개")
            total_edges += record["count"]
        print(f"  --------\n  총 관계: {total_edges}개")

        # hourly_rate 범위
        record = session.run("""
            MATCH (e:Employee)
            RETURN min(e.hourly_rate) AS min_rate,
                   max(e.hourly_rate) AS max_rate,
                   avg(e.hourly_rate) AS avg_rate
        """).single()
        print("\n[Employee hourly_rate]")
        print(f"  min: {record['min_rate']:,}원 / max: {record['max_rate']:,}원 / avg: {record['avg_rate']:,.0f}원")

        # effective_rate 범위
        record = session.run("""
            MATCH ()-[r:HAS_SKILL]->()
            RETURN min(r.effective_rate) AS min_rate,
                   max(r.effective_rate) AS max_rate,
                   avg(r.effective_rate) AS avg_rate
        """).single()
        print("\n[HAS_SKILL effective_rate]")
        print(f"  min: {record['min_rate']:,}원 / max: {record['max_rate']:,}원 / avg: {record['avg_rate']:,.0f}원")

        # availability 분포
        result = session.run("""
            MATCH (e:Employee)
            RETURN e.availability AS status, count(*) AS count
            ORDER BY count DESC
        """)
        print("\n[Employee availability]")
        for record in result:
            print(f"  {record['status']}: {record['count']}명")


def sample_queries(driver):
    """샘플 쿼리 실행"""
    print("\n" + "=" * 60)
    print(" 샘플 쿼리 테스트")
    print("=" * 60)

    with driver.session() as session:
        print("\n[쿼리 1] Python 전문가 (고급 이상)")
        for r in session.run("""
            MATCH (e:Employee)-[r:HAS_SKILL]->(s:Skill {name: 'Python'})
            WHERE r.proficiency IN ['고급', '전문가']
            RETURN e.name AS name, e.job_type AS job, r.proficiency AS level
            LIMIT 5
        """):
            print(f"  - {r['name']} ({r['job']}) - {r['level']}")

        print("\n[쿼리 2] Python 고급+ 단가 TOP 5")
        for r in session.run("""
            MATCH (e:Employee)-[r:HAS_SKILL]->(s:Skill)
            WHERE toLower(s.name) = 'python'
              AND r.proficiency IN ['고급', '전문가']
              AND e.availability <> 'unavailable'
            RETURN e.name AS name, e.hourly_rate AS base_rate,
                   r.effective_rate AS skill_rate, e.availability AS avail
            ORDER BY r.effective_rate DESC
            LIMIT 5
        """):
            print(f"  - {r['name']}: base={r['base_rate']:,}원, "
                  f"skill={r['skill_rate']:,}원, avail={r['avail']}")

        print("\n[쿼리 3] 진행중 프로젝트 예산 TOP 3")
        for r in session.run("""
            MATCH (p:Project)
            WHERE p.status = '진행중'
            RETURN p.name AS project,
                   p.budget_allocated AS allocated,
                   p.budget_spent AS spent,
                   p.required_headcount AS headcount
            ORDER BY p.budget_allocated DESC
            LIMIT 3
        """):
            print(f"  - {r['project']}: allocated={r['allocated']:,}원, "
                  f"spent={r['spent']:,}원, headcount={r['headcount']}명")

        print("\n[쿼리 4] 멘토-멘티 관계")
        for r in session.run("""
            MATCH (mentor:Employee)-[:MENTORS]->(mentee:Employee)
            RETURN mentor.name AS mentor, mentee.name AS mentee,
                   mentor.years_experience AS mentor_exp
            LIMIT 5
        """):
            print(f"  - {r['mentor']}({r['mentor_exp']}년) → {r['mentee']}")


def main():
    print("\n" + "=" * 60)
    print(" CSV → Neo4j 데이터 로더")
    print("=" * 60)

    driver = GraphDatabase.driver(URI, auth=AUTH)

    try:
        driver.verify_connectivity()
        print("\n✓ Neo4j 연결 성공!")

        clear_database(driver)
        create_constraints(driver)
        load_nodes(driver)
        load_employees(driver)
        load_projects(driver)
        load_relationships(driver)
        set_employee_availability(driver)

        verify_data(driver)
        sample_queries(driver)

        print("\n" + "=" * 60)
        print(" 로드 완료!")
        print(" 브라우저에서 확인: http://localhost:7474")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
