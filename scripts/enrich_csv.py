"""
CSV 파생 컬럼 추가 스크립트

기존 CSV 컬럼에서 파생 필드를 계산하여 CSV에 직접 추가.
load_to_neo4j.py의 인라인 Cypher 계산을 CSV 레벨로 이동.

실행: python scripts/enrich_csv.py
"""

import csv
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "company_realistic")

# ─── 상수 ────────────────────────────────────────────

JOB_MULTIPLIER = {
    "보안엔지니어": 1.20,
    "ML엔지니어": 1.15,
    "데이터엔지니어": 1.10,
    "DevOps엔지니어": 1.10,
    "SRE": 1.10,
    "백엔드개발자": 1.05,
    "풀스택개발자": 1.05,
    "PM/PO": 1.05,
    "UX디자이너": 0.95,
}

HIGH_DEMAND_SKILLS = {
    "Python", "Kubernetes", "React", "AI/ML", "TensorFlow", "PyTorch",
    "Java", "JavaScript", "Docker", "AWS", "TypeScript", "Go",
}
MEDIUM_DEMAND_SKILLS = {"SQL", "PostgreSQL", "Node.js", "Spring Boot"}

PROFICIENCY_FACTOR = {"전문가": 1.0, "고급": 0.85, "중급": 0.7, "초급": 0.5}


def base_rate(years_exp: int) -> int:
    if years_exp >= 15:
        return 150000
    if years_exp >= 10:
        return 120000
    if years_exp >= 7:
        return 100000
    if years_exp >= 5:
        return 85000
    if years_exp >= 3:
        return 70000
    if years_exp >= 1:
        return 55000
    return 40000


def max_projects(years_exp: int) -> int:
    if years_exp >= 10:
        return 5
    if years_exp >= 5:
        return 4
    if years_exp >= 2:
        return 3
    return 2


# ─── CSV 읽기/쓰기 헬퍼 ─────────────────────────────

def read_csv(filename: str) -> list[dict]:
    path = os.path.join(DATA_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(filename: str, rows: list[dict], fieldnames: list[str]):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {filename}: {len(rows)} rows, columns={fieldnames}")


# ─── 1. skills.csv ───────────────────────────────────

def enrich_skills():
    print("\n[1/6] skills.csv 보강...")
    rows = read_csv("skills.csv")
    for row in rows:
        diff = row["difficulty"]
        row["hourly_rate_min"] = 80000 if diff == "Hard" else 60000 if diff == "Medium" else 40000
        row["hourly_rate_max"] = 180000 if diff == "Hard" else 120000 if diff == "Medium" else 80000
        name = row["name"]
        if name in HIGH_DEMAND_SKILLS:
            row["market_demand"] = "high"
        elif name in MEDIUM_DEMAND_SKILLS:
            row["market_demand"] = "medium"
        else:
            row["market_demand"] = "medium"
    fields = ["id", "name", "category", "difficulty", "hourly_rate_min", "hourly_rate_max", "market_demand"]
    write_csv("skills.csv", rows, fields)
    return {r["id"]: r for r in rows}


# ─── 2. employees.csv ────────────────────────────────

def enrich_employees(dept_map: dict[str, str]):
    print("\n[2/6] employees.csv 보강...")
    rows = read_csv("employees.csv")
    for row in rows:
        yrs = int(row["years_experience"])
        job = row["job_type"]
        mul = JOB_MULTIPLIER.get(job, 1.0)
        row["hourly_rate"] = int(base_rate(yrs) * mul)
        row["max_projects"] = max_projects(yrs)
        row["department"] = dept_map.get(row["department_id"], "")
    fields = [
        "id", "name", "email", "job_type", "years_experience", "hire_date",
        "position_id", "department_id", "hourly_rate", "max_projects", "department",
    ]
    write_csv("employees.csv", rows, fields)
    return {r["id"]: r for r in rows}


# ─── 3. projects.csv ─────────────────────────────────

def enrich_projects():
    print("\n[3/6] projects.csv 보강...")
    rows = read_csv("projects.csv")
    for row in rows:
        bm = int(row["budget_million"])
        row["budget_allocated"] = bm * 1_000_000
        status = row["status"]
        ratio = {"완료": 0.95, "진행중": 0.45, "보류": 0.2, "취소": 0.1}.get(status, 0)
        row["budget_spent"] = int(bm * 1_000_000 * ratio)
        row["duration_months"] = 12 if bm >= 7000 else 9 if bm >= 4000 else 6
        row["estimated_hours"] = 8000 if bm >= 7000 else 5000 if bm >= 4000 else 3000
        row["required_headcount"] = 8 if bm >= 7000 else 5 if bm >= 4000 else 3
    fields = [
        "id", "name", "type", "status", "start_date", "budget_million", "dept_id",
        "required_skills", "budget_allocated", "budget_spent",
        "duration_months", "estimated_hours", "required_headcount",
    ]
    write_csv("projects.csv", rows, fields)
    return {r["id"]: r for r in rows}


# ─── 4. employee_skill.csv ───────────────────────────

def enrich_employee_skill(skill_map: dict):
    print("\n[4/6] employee_skill.csv 보강...")
    rows = read_csv("employee_skill.csv")
    for row in rows:
        prof = row["proficiency"]
        rf = PROFICIENCY_FACTOR.get(prof, 0.5)
        row["rate_factor"] = rf
        skill = skill_map.get(row["skill_id"], {})
        rate_min = int(skill.get("hourly_rate_min", 40000))
        rate_max = int(skill.get("hourly_rate_max", 80000))
        years_used = int(row["years_used"])
        row["effective_rate"] = int(rate_min + (rate_max - rate_min) * rf * (0.3 + 0.7 * years_used / 10.0))
    fields = ["employee_id", "skill_id", "proficiency", "years_used", "rate_factor", "effective_rate"]
    write_csv("employee_skill.csv", rows, fields)


# ─── 5. employee_project.csv ─────────────────────────

def enrich_employee_project(emp_map: dict, proj_map: dict):
    print("\n[5/6] employee_project.csv 보강...")
    rows = read_csv("employee_project.csv")
    for row in rows:
        emp = emp_map.get(row["employee_id"], {})
        proj = proj_map.get(row["project_id"], {})
        row["agreed_rate"] = int(emp.get("hourly_rate", 0))
        est_hours = int(proj.get("estimated_hours", 3000))
        headcount = int(proj.get("required_headcount", 3))
        alloc = int(est_hours / headcount) if headcount > 0 else 0
        row["allocated_hours"] = alloc
        status = proj.get("status", "")
        ratio = {"완료": 0.95, "진행중": 0.5}.get(status, 0)
        row["actual_hours"] = int(alloc * ratio)
    fields = [
        "employee_id", "project_id", "role", "contribution_percent",
        "agreed_rate", "allocated_hours", "actual_hours",
    ]
    write_csv("employee_project.csv", rows, fields)


# ─── 6. project_skill.csv ────────────────────────────

def enrich_project_skill(skill_map: dict):
    print("\n[6/6] project_skill.csv 보강...")
    rows = read_csv("project_skill.csv")
    for row in rows:
        imp = row["importance"]
        row["required_proficiency"] = {"필수": "고급", "우대": "중급"}.get(imp, "초급")
        row["required_headcount"] = 2 if imp == "필수" else 1
        skill = skill_map.get(row["skill_id"], {})
        rate_min = int(skill.get("hourly_rate_min", 40000))
        rate_max = int(skill.get("hourly_rate_max", 80000))
        if imp == "필수":
            row["max_hourly_rate"] = rate_max
        elif imp == "우대":
            row["max_hourly_rate"] = int((rate_min + rate_max) / 2)
        else:
            row["max_hourly_rate"] = rate_min
        row["priority"] = {"필수": 1, "우대": 2}.get(imp, 3)
    fields = [
        "project_id", "skill_id", "importance",
        "required_proficiency", "required_headcount", "max_hourly_rate", "priority",
    ]
    write_csv("project_skill.csv", rows, fields)


# ─── main ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print(" CSV 파생 컬럼 추가")
    print("=" * 60)

    # Department name 매핑 (비정규화용)
    depts = read_csv("departments.csv")
    dept_map = {d["id"]: d["name"] for d in depts}

    skill_map = enrich_skills()
    emp_map = enrich_employees(dept_map)
    proj_map = enrich_projects()
    enrich_employee_skill(skill_map)
    enrich_employee_project(emp_map, proj_map)
    enrich_project_skill(skill_map)

    print("\n" + "=" * 60)
    print(" CSV 보강 완료!")
    print("=" * 60)


if __name__ == "__main__":
    main()
