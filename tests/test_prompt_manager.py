import os
import shutil
import pytest
from src.utils.prompt_manager import PromptManager


class TestPromptManager:
    @pytest.fixture
    def test_prompts_dir(self):
        """임시 테스트용 프롬프트 디렉토리 생성"""
        dir_path = "tests/temp_prompts"
        os.makedirs(dir_path, exist_ok=True)

        # 테스트용 YAML 파일 생성
        with open(f"{dir_path}/test_prompt.yaml", "w") as f:
            f.write("system: Test System {var}\nuser: Test User {var}")

        yield dir_path

        # 정리
        shutil.rmtree(dir_path)

    def test_load_prompt_success(self, test_prompts_dir):
        """프롬프트 로드 성공 테스트"""
        manager = PromptManager(prompts_dir=test_prompts_dir)
        prompt = manager.load_prompt("test_prompt")

        assert prompt["system"] == "Test System {var}"
        assert prompt["user"] == "Test User {var}"

    def test_load_prompt_not_found(self, test_prompts_dir):
        """없는 프롬프트 로드 시 에러"""
        manager = PromptManager(prompts_dir=test_prompts_dir)
        with pytest.raises(FileNotFoundError):
            manager.load_prompt("non_existent")

    def test_cache_usage(self, test_prompts_dir):
        """캐시 사용 확인"""
        manager = PromptManager(prompts_dir=test_prompts_dir)

        # 첫 번째 로드
        p1 = manager.load_prompt("test_prompt")

        # 파일 조작 (내용 변경)
        with open(f"{test_prompts_dir}/test_prompt.yaml", "w") as f:
            f.write("system: Modified")

        # 두 번째 로드 (캐시 사용)
        p2 = manager.load_prompt("test_prompt")

        # 캐시된 값을 가져와야 하므로 변경된 파일 내용이 반영되지 않아야 함
        assert p2["system"] == "Test System {var}"
        assert p1 is p2  # 객체 아이덴티티 확인

        # 캐시 무시하고 로드
        p3 = manager.load_prompt("test_prompt", use_cache=False)
        assert p3["system"] == "Modified"
