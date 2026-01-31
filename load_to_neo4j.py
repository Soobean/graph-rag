"""
CSV 데이터를 Neo4j에 로드하는 스크립트
LOAD CSV 방식으로 빠르게 데이터 적재
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
    print("\n[0/7] 기존 데이터 삭제 중...")
    run_query(driver, "MATCH (n) DETACH DELETE n")
    print("  ✓ 완료")


def create_constraints(driver):
    """인덱스 및 제약조건 생성"""
    print("\n[1/7] 인덱스 및 제약조건 생성 중...")

    constraints = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Employee) REQUIRE e.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Department) REQUIRE d.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Skill) REQUIRE s.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Project) REQUIRE p.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Company) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (o:Office) REQUIRE o.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (pos:Position) REQUIRE pos.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (cert:Certificate) REQUIRE cert.id IS UNIQUE",
    ]

    for constraint in constraints:
        try:
            run_query(driver, constraint)
        except Exception:
            pass  # 이미 존재하는 경우 무시

    # name 필드 인덱스 (검색 성능 최적화)
    # 쿼리에서 WHERE n.name = $name, WHERE n.name CONTAINS $name 패턴이 빈번
    indexes = [
        "CREATE INDEX employee_name IF NOT EXISTS FOR (e:Employee) ON (e.name)",
        "CREATE INDEX department_name IF NOT EXISTS FOR (d:Department) ON (d.name)",
        "CREATE INDEX skill_name IF NOT EXISTS FOR (s:Skill) ON (s.name)",
        "CREATE INDEX project_name IF NOT EXISTS FOR (p:Project) ON (p.name)",
        "CREATE INDEX company_name IF NOT EXISTS FOR (c:Company) ON (c.name)",
        "CREATE INDEX office_name IF NOT EXISTS FOR (o:Office) ON (o.name)",
        "CREATE INDEX position_name IF NOT EXISTS FOR (pos:Position) ON (pos.name)",
        "CREATE INDEX certificate_name IF NOT EXISTS FOR (cert:Certificate) ON (cert.name)",
        # 추가 검색 필드 인덱스
        "CREATE INDEX skill_category IF NOT EXISTS FOR (s:Skill) ON (s.category)",
        "CREATE INDEX project_type IF NOT EXISTS FOR (p:Project) ON (p.type)",
        "CREATE INDEX project_status IF NOT EXISTS FOR (p:Project) ON (p.status)",
    ]

    for idx in indexes:
        try:
            run_query(driver, idx)
        except Exception:
            pass  # 이미 존재하는 경우 무시

    print("  ✓ 완료")


def load_nodes(driver):
    """노드 데이터 로드"""

    # 1. Company 노드
    print("\n[2/7] Company 노드 로드 중...")
    query = """
    LOAD CSV WITH HEADERS FROM 'file:///companies.csv' AS row
    CREATE (c:Company {
        id: row.id,
        name: row.name,
        type: row.type,
        industry: row.industry,
        employee_count: toInteger(row.employee_count)
    })
    """
    run_query(driver, query)
    print("  ✓ 완료")

    # 2. Office 노드
    print("\n[3/7] Office 노드 로드 중...")
    query = """
    LOAD CSV WITH HEADERS FROM 'file:///offices.csv' AS row
    CREATE (o:Office {
        id: row.id,
        name: row.name,
        city: row.city,
        address: row.address
    })
    """
    run_query(driver, query)
    print("  ✓ 완료")

    # 3. Department 노드 + Office 관계
    print("\n[4/7] Department 노드 로드 중...")
    query = """
    LOAD CSV WITH HEADERS FROM 'file:///departments.csv' AS row
    CREATE (d:Department {
        id: row.id,
        name: row.name,
        head_count: toInteger(row.head_count),
        budget_billion: toFloat(row.budget_billion)
    })
    WITH d, row
    MATCH (o:Office {id: row.office_id})
    CREATE (d)-[:LOCATED_AT]->(o)
    """
    run_query(driver, query)
    print("  ✓ 완료")

    # 4. Position 노드
    print("\n[5/7] Position 노드 로드 중...")
    query = """
    LOAD CSV WITH HEADERS FROM 'file:///positions.csv' AS row
    CREATE (p:Position {
        id: row.id,
        name: row.name,
        level: toInteger(row.level),
        min_years: toInteger(row.min_years),
        max_years: toInteger(row.max_years)
    })
    """
    run_query(driver, query)
    print("  ✓ 완료")

    # 5. Skill 노드
    print("\n[6/7] Skill 노드 로드 중...")
    query = """
    LOAD CSV WITH HEADERS FROM 'file:///skills.csv' AS row
    CREATE (s:Skill {
        id: row.id,
        name: row.name,
        category: row.category,
        difficulty: row.difficulty
    })
    """
    run_query(driver, query)
    print("  ✓ 완료")

    # 6. Certificate 노드
    print("\n[7/7] Certificate 노드 로드 중...")
    query = """
    LOAD CSV WITH HEADERS FROM 'file:///certificates.csv' AS row
    CREATE (c:Certificate {
        id: row.id,
        name: row.name,
        issuer: row.issuer,
        category: row.category
    })
    """
    run_query(driver, query)
    print("  ✓ 완료")


def load_employees(driver):
    """Employee 노드 및 관계 로드"""
    print("\n[8/10] Employee 노드 로드 중...")

    # Employee 노드 생성 + Department, Position 관계
    query = """
    LOAD CSV WITH HEADERS FROM 'file:///employees.csv' AS row
    CREATE (e:Employee {
        id: row.id,
        name: row.name,
        email: row.email,
        job_type: row.job_type,
        years_experience: toInteger(row.years_experience),
        hire_date: row.hire_date
    })
    WITH e, row
    MATCH (d:Department {id: row.department_id})
    MATCH (p:Position {id: row.position_id})
    CREATE (e)-[:BELONGS_TO]->(d)
    CREATE (e)-[:HAS_POSITION]->(p)
    """
    run_query(driver, query)
    print("  ✓ 완료")


def load_projects(driver):
    """Project 노드 및 관계 로드"""
    print("\n[9/10] Project 노드 로드 중...")

    query = """
    LOAD CSV WITH HEADERS FROM 'file:///projects.csv' AS row
    CREATE (p:Project {
        id: row.id,
        name: row.name,
        type: row.type,
        status: row.status,
        start_date: row.start_date,
        budget_million: toInteger(row.budget_million)
    })
    WITH p, row
    MATCH (d:Department {id: row.dept_id})
    CREATE (p)-[:OWNED_BY]->(d)
    """
    run_query(driver, query)
    print("  ✓ 완료")


def load_relationships(driver):
    """관계 데이터 로드"""
    print("\n[10/10] 관계 데이터 로드 중...")

    # Employee - Skill 관계
    print("  - Employee-Skill 관계...")
    query = """
    LOAD CSV WITH HEADERS FROM 'file:///employee_skill.csv' AS row
    MATCH (e:Employee {id: row.employee_id})
    MATCH (s:Skill {id: row.skill_id})
    CREATE (e)-[:HAS_SKILL {
        proficiency: row.proficiency,
        years_used: toInteger(row.years_used)
    }]->(s)
    """
    run_query(driver, query)

    # Employee - Project 관계
    print("  - Employee-Project 관계...")
    query = """
    LOAD CSV WITH HEADERS FROM 'file:///employee_project.csv' AS row
    MATCH (e:Employee {id: row.employee_id})
    MATCH (p:Project {id: row.project_id})
    CREATE (e)-[:WORKS_ON {
        role: row.role,
        contribution_percent: toInteger(row.contribution_percent)
    }]->(p)
    """
    run_query(driver, query)

    # Project - Skill 관계
    print("  - Project-Skill 관계...")
    query = """
    LOAD CSV WITH HEADERS FROM 'file:///project_skill.csv' AS row
    MATCH (p:Project {id: row.project_id})
    MATCH (s:Skill {id: row.skill_id})
    CREATE (p)-[:REQUIRES {
        importance: row.importance
    }]->(s)
    """
    run_query(driver, query)

    # Employee - Certificate 관계
    print("  - Employee-Certificate 관계...")
    query = """
    LOAD CSV WITH HEADERS FROM 'file:///employee_certificate.csv' AS row
    MATCH (e:Employee {id: row.employee_id})
    MATCH (c:Certificate {id: row.certificate_id})
    CREATE (e)-[:HAS_CERTIFICATE {
        acquired_date: row.acquired_date
    }]->(c)
    """
    run_query(driver, query)

    # Mentorship 관계
    print("  - Mentorship 관계...")
    query = """
    LOAD CSV WITH HEADERS FROM 'file:///mentorship.csv' AS row
    MATCH (mentor:Employee {id: row.mentor_id})
    MATCH (mentee:Employee {id: row.mentee_id})
    CREATE (mentor)-[:MENTORS {
        start_date: row.start_date
    }]->(mentee)
    """
    run_query(driver, query)

    print("  ✓ 모든 관계 로드 완료")


def verify_data(driver):
    """데이터 검증"""
    print("\n" + "=" * 60)
    print(" 데이터 검증")
    print("=" * 60)

    with driver.session() as session:
        # 노드 수 확인
        result = session.run("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY count DESC")
        print("\n[노드 통계]")
        total_nodes = 0
        for record in result:
            print(f"  {record['label']}: {record['count']}개")
            total_nodes += record['count']
        print(f"  --------")
        print(f"  총 노드: {total_nodes}개")

        # 관계 수 확인
        result = session.run("MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY count DESC")
        print("\n[관계 통계]")
        total_edges = 0
        for record in result:
            print(f"  {record['type']}: {record['count']}개")
            total_edges += record['count']
        print(f"  --------")
        print(f"  총 관계: {total_edges}개")


def sample_queries(driver):
    """샘플 쿼리 실행"""
    print("\n" + "=" * 60)
    print(" 샘플 쿼리 테스트")
    print("=" * 60)

    with driver.session() as session:
        # 1. Python 스킬을 가진 시니어 개발자
        print("\n[쿼리 1] Python 전문가 (고급 이상) 조회")
        result = session.run("""
            MATCH (e:Employee)-[r:HAS_SKILL]->(s:Skill {name: 'Python'})
            WHERE r.proficiency IN ['고급', '전문가']
            RETURN e.name AS name, e.job_type AS job, r.proficiency AS level
            LIMIT 5
        """)
        for record in result:
            print(f"  - {record['name']} ({record['job']}) - {record['level']}")

        # 2. 특정 프로젝트에 필요한 기술과 해당 기술을 가진 직원
        print("\n[쿼리 2] 'AI/ML' 프로젝트에 필요한 기술 보유자")
        result = session.run("""
            MATCH (p:Project {type: 'AI/ML'})-[:REQUIRES]->(s:Skill)
            WITH s LIMIT 3
            MATCH (e:Employee)-[:HAS_SKILL]->(s)
            RETURN s.name AS skill, collect(DISTINCT e.name)[0..3] AS employees
        """)
        for record in result:
            print(f"  - {record['skill']}: {record['employees']}")

        # 3. 멘토-멘티 관계 조회
        print("\n[쿼리 3] 멘토-멘티 관계")
        result = session.run("""
            MATCH (mentor:Employee)-[:MENTORS]->(mentee:Employee)
            RETURN mentor.name AS mentor, mentee.name AS mentee,
                   mentor.years_experience AS mentor_exp, mentee.years_experience AS mentee_exp
            LIMIT 5
        """)
        for record in result:
            print(f"  - {record['mentor']}({record['mentor_exp']}년) → {record['mentee']}({record['mentee_exp']}년)")


def main():
    print("\n" + "=" * 60)
    print(" CSV → Neo4j 데이터 로더")
    print("=" * 60)

    driver = GraphDatabase.driver(URI, auth=AUTH)

    try:
        # 연결 테스트
        driver.verify_connectivity()
        print("\n✓ Neo4j 연결 성공!")

        # 데이터 로드
        clear_database(driver)
        create_constraints(driver)
        load_nodes(driver)
        load_employees(driver)
        load_projects(driver)
        load_relationships(driver)

        # 검증
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
