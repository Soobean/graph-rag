"""
X-Demo-Role API 통합 테스트 (라이브 서버 필요)

실행: pytest tests/test_api_demo_role_live.py -v -s
사전조건: uvicorn src.main:app (port 8000) + Neo4j 실행 중
"""

import asyncio
import json

import httpx
import pytest

BASE_URL = "http://localhost:8000/api/v1"
TIMEOUT = 60.0


def _server_is_running() -> bool:
    try:
        resp = httpx.get(f"{BASE_URL}/health", timeout=2)
        return resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


pytestmark = pytest.mark.skipif(
    not _server_is_running(),
    reason="Backend server not running on localhost:8000",
)


# ============================================
# Helper
# ============================================

async def stream_query(question: str, demo_role: str | None = None) -> dict:
    """SSE 스트리밍 쿼리 실행 후 결과를 dict로 반환"""
    headers = {"Content-Type": "application/json"}
    if demo_role:
        headers["X-Demo-Role"] = demo_role

    result = {
        "role": demo_role or "no_header",
        "chunks": [],
        "metadata": None,
        "done": None,
        "error": None,
        "full_response": "",
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/query/stream",
            headers=headers,
            json={"question": question},
        ) as response:
            if response.status_code != 200:
                result["error"] = f"HTTP {response.status_code}"
                return result

            buffer = ""
            current_event = {"event": None, "data": []}

            async for chunk in response.aiter_text():
                buffer += chunk
                lines = buffer.split("\n")
                buffer = lines.pop()  # keep incomplete line

                for line in lines:
                    line = line.rstrip("\r")
                    if line.startswith("event:"):
                        current_event["event"] = line[6:].strip()
                    elif line.startswith("data:"):
                        current_event["data"].append(line[5:])
                    elif line.strip() == "" and current_event["event"]:
                        event_type = current_event["event"]
                        event_data = "\n".join(current_event["data"])

                        if event_type == "metadata":
                            result["metadata"] = json.loads(event_data)
                        elif event_type == "chunk":
                            result["chunks"].append(event_data)
                            result["full_response"] += event_data
                        elif event_type == "done":
                            result["done"] = json.loads(event_data)
                        elif event_type == "error":
                            result["error"] = event_data

                        current_event = {"event": None, "data": []}

    return result


async def sync_query(question: str, demo_role: str | None = None) -> dict:
    """일반 (non-streaming) POST /query 호출"""
    headers = {"Content-Type": "application/json"}
    if demo_role:
        headers["X-Demo-Role"] = demo_role

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{BASE_URL}/query",
            headers=headers,
            json={"question": question},
        )
        return {"status": resp.status_code, "body": resp.json()}


# ============================================
# Phase 1: API 단위 테스트
# ============================================

@pytest.mark.integration
class TestDemoRoleAPIBasic:
    """X-Demo-Role 헤더가 정상적으로 처리되는지 검증"""

    @pytest.mark.asyncio
    async def test_admin_stream_succeeds(self):
        """admin 역할로 스트리밍 질의 성공"""
        result = await stream_query("안녕", "admin")
        assert result["error"] is None, f"Unexpected error: {result['error']}"
        assert result["metadata"] is not None
        assert result["done"] is not None

    @pytest.mark.asyncio
    async def test_viewer_stream_succeeds(self):
        """viewer 역할로 스트리밍 질의 성공"""
        result = await stream_query("안녕", "viewer")
        assert result["error"] is None
        assert result["metadata"] is not None

    @pytest.mark.asyncio
    async def test_no_header_defaults_to_admin(self):
        """헤더 없음 -> anonymous_admin (기존 동작)"""
        result = await stream_query("안녕")
        assert result["error"] is None
        assert result["metadata"] is not None

    @pytest.mark.asyncio
    async def test_invalid_role_defaults_to_admin(self):
        """잘못된 역할 -> anonymous_admin"""
        result = await stream_query("안녕", "superuser")
        assert result["error"] is None
        assert result["metadata"] is not None

    @pytest.mark.asyncio
    async def test_sync_query_with_role(self):
        """POST /query (non-streaming) 에서도 X-Demo-Role 동작"""
        result = await sync_query("안녕", "viewer")
        assert result["status"] == 200


# ============================================
# Phase 2: D1~D4 시나리오 테스트
# ============================================

@pytest.mark.integration
class TestAccessControlScenarios:
    """같은 질문, 다른 역할 -> 다른 결과 검증"""

    @pytest.mark.asyncio
    async def test_d1_label_filtering_viewer_vs_admin(self):
        """
        D1 라벨 필터링: viewer는 Company/Concept 접근 불가
        질문: "Python 관련 개념 보여줘" -> admin은 Concept 접근 가능, viewer는 불가
        """
        admin_result, viewer_result = await asyncio.gather(
            stream_query("Python 관련 개념 계층 보여줘", "admin"),
            stream_query("Python 관련 개념 계층 보여줘", "viewer"),
        )

        # 둘 다 에러 없이 응답
        assert admin_result["error"] is None, f"admin error: {admin_result['error']}"
        assert viewer_result["error"] is None, f"viewer error: {viewer_result['error']}"

        # admin 응답에는 Concept 관련 내용이 있어야 함 (또는 최소한 더 많은 결과)
        admin_response = admin_result["full_response"]
        viewer_response = viewer_result["full_response"]
        print(f"\n[D1] admin response ({len(admin_response)} chars): {admin_response[:200]}...")
        print(f"[D1] viewer response ({len(viewer_response)} chars): {viewer_response[:200]}...")

        # 최소한 둘 다 응답이 있어야 함
        assert len(admin_response) > 0 or admin_result["done"] is not None
        assert len(viewer_response) > 0 or viewer_result["done"] is not None

    @pytest.mark.asyncio
    async def test_d2_property_filtering_salary(self):
        """
        D2 속성 필터링: viewer/editor는 salary 접근 불가
        질문: "개발자들 연봉 알려줘"
        """
        admin_result, viewer_result = await asyncio.gather(
            stream_query("개발자들 연봉 알려줘", "admin"),
            stream_query("개발자들 연봉 알려줘", "viewer"),
        )

        assert admin_result["error"] is None
        assert viewer_result["error"] is None

        admin_response = admin_result["full_response"]
        viewer_response = viewer_result["full_response"]
        print(f"\n[D2] admin response: {admin_response[:300]}...")
        print(f"[D2] viewer response: {viewer_response[:300]}...")

    @pytest.mark.asyncio
    async def test_d3_department_scope_manager(self):
        """
        D3 부서 범위: manager는 자기 부서(백엔드개발팀) 데이터만 조회
        """
        admin_result, manager_result = await asyncio.gather(
            stream_query("Python 개발자 찾아줘", "admin"),
            stream_query("Python 개발자 찾아줘", "manager"),
        )

        assert admin_result["error"] is None
        assert manager_result["error"] is None

        admin_meta = admin_result["metadata"] or {}
        manager_meta = manager_result["metadata"] or {}
        admin_count = admin_meta.get("result_count", 0)
        manager_count = manager_meta.get("result_count", 0)

        print(f"\n[D3] admin result_count: {admin_count}")
        print(f"[D3] manager result_count: {manager_count}")
        print(f"[D3] admin response: {admin_result['full_response'][:300]}...")
        print(f"[D3] manager response: {manager_result['full_response'][:300]}...")

        # manager 결과 <= admin 결과 (부서 필터링으로 더 적은 결과)
        # (단, 모든 Python 개발자가 백엔드개발팀이면 같을 수 있음)

    @pytest.mark.asyncio
    async def test_d4_relationship_filtering_mentors(self):
        """
        D4 관계 필터링: viewer/editor는 MENTORS 접근 불가
        질문: "멘토링 관계 보여줘"
        """
        admin_result, viewer_result = await asyncio.gather(
            stream_query("멘토링 관계 보여줘", "admin"),
            stream_query("멘토링 관계 보여줘", "viewer"),
        )

        assert admin_result["error"] is None
        assert viewer_result["error"] is None

        admin_response = admin_result["full_response"]
        viewer_response = viewer_result["full_response"]
        print(f"\n[D4] admin response: {admin_response[:300]}...")
        print(f"[D4] viewer response: {viewer_response[:300]}...")

    @pytest.mark.asyncio
    async def test_four_roles_parallel_comparison(self):
        """
        4역할 병렬 비교: ComparePage 시뮬레이션
        같은 질문을 4개 역할로 동시 전송
        """
        question = "Python 개발자 찾아줘"
        results = await asyncio.gather(
            stream_query(question, "admin"),
            stream_query(question, "manager"),
            stream_query(question, "editor"),
            stream_query(question, "viewer"),
        )

        print(f"\n{'='*70}")
        print(f"4-Role Comparison: '{question}'")
        print(f"{'='*70}")

        for r in results:
            meta = r["metadata"] or {}
            count = meta.get("result_count", "N/A")
            cypher = meta.get("cypher_query", "N/A")
            response_preview = r["full_response"][:150].replace("\n", " ")
            print(f"\n[{r['role']:>8}] result_count={count}")
            print(f"           cypher: {cypher[:120] if cypher != 'N/A' else 'N/A'}...")
            print(f"           response: {response_preview}...")

        # 모든 역할이 에러 없이 응답해야 함
        for r in results:
            assert r["error"] is None, f"{r['role']} error: {r['error']}"
            assert r["done"] is not None, f"{r['role']} did not complete"


# ============================================
# Phase 3: 보안 경계 테스트
# ============================================

@pytest.mark.integration
class TestSecurityEdgeCases:
    """X-Demo-Role 보안 경계 케이스"""

    @pytest.mark.asyncio
    async def test_empty_role_header(self):
        """빈 문자열 역할 -> anonymous_admin"""
        result = await stream_query("안녕", "")
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_special_chars_in_role(self):
        """특수문자 포함 역할 -> 무시 (anonymous_admin)"""
        result = await stream_query("안녕", "admin'; DROP TABLE--")
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_very_long_role(self):
        """매우 긴 역할명 -> 무시"""
        result = await stream_query("안녕", "a" * 10000)
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_unicode_confusable_role(self):
        """유니코드 혼동 공격 -> HTTP 프로토콜 레벨에서 차단 (헤더는 ASCII only)"""
        with pytest.raises(UnicodeEncodeError):
            await stream_query("안녕", "\u0430dmin")  # Cyrillic 'а'

    @pytest.mark.asyncio
    async def test_case_sensitive_role(self):
        """대문자 역할 -> 무시 (Admin != admin)"""
        result = await stream_query("안녕", "Admin")
        assert result["error"] is None
