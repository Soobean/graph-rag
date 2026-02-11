"""
비밀번호 해싱 및 검증

bcrypt 12 rounds를 사용하여 안전한 비밀번호 관리를 제공합니다.
"""

import bcrypt


class PasswordHandler:
    """bcrypt 기반 비밀번호 해싱/검증"""

    ROUNDS = 12

    @staticmethod
    def hash_password(password: str) -> str:
        """비밀번호를 bcrypt로 해싱"""
        salt = bcrypt.gensalt(rounds=PasswordHandler.ROUNDS)
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """평문 비밀번호가 해시와 일치하는지 검증"""
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
