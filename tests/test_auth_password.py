"""
PasswordHandler 테스트

bcrypt 해싱/검증 로직을 검증합니다.
"""

from src.auth.password import PasswordHandler


class TestPasswordHandler:
    """비밀번호 해싱/검증 테스트"""

    def test_hash_password_returns_bcrypt_hash(self):
        """해싱 결과가 bcrypt 포맷($2b$)"""
        hashed = PasswordHandler.hash_password("test123")
        assert hashed.startswith("$2b$")

    def test_hash_password_different_each_time(self):
        """같은 비밀번호도 매번 다른 해시 생성 (salt 적용)"""
        h1 = PasswordHandler.hash_password("test123")
        h2 = PasswordHandler.hash_password("test123")
        assert h1 != h2

    def test_verify_password_correct(self):
        """올바른 비밀번호 검증 통과"""
        hashed = PasswordHandler.hash_password("mypassword")
        assert PasswordHandler.verify_password("mypassword", hashed) is True

    def test_verify_password_wrong(self):
        """틀린 비밀번호 검증 실패"""
        hashed = PasswordHandler.hash_password("mypassword")
        assert PasswordHandler.verify_password("wrongpassword", hashed) is False

    def test_verify_password_empty(self):
        """빈 비밀번호 처리"""
        hashed = PasswordHandler.hash_password("")
        assert PasswordHandler.verify_password("", hashed) is True
        assert PasswordHandler.verify_password("notempty", hashed) is False

    def test_hash_password_unicode(self):
        """유니코드(한글) 비밀번호 지원"""
        hashed = PasswordHandler.hash_password("비밀번호123")
        assert PasswordHandler.verify_password("비밀번호123", hashed) is True
        assert PasswordHandler.verify_password("비밀번호124", hashed) is False
