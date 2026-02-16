"""
Unit tests for src.app (UserRepository).

These tests are intentionally lightweight (mocking the DB connection) to ensure
SonarCloud receives meaningful coverage, especially on new/changed lines.
"""

from unittest.mock import MagicMock

from src.app import UserRepository


class TestUserRepository:
    def test_init_stores_connection(self):
        conn = MagicMock()
        repo = UserRepository(conn)
        assert repo.connection is conn

    def test_get_user_by_id_success(self):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = {"id": 1, "email": "a@b.co", "name": "Alice"}
        conn.execute.return_value = cursor

        repo = UserRepository(conn)
        result = repo.get_user_by_id(1)

        assert result == {"id": 1, "email": "a@b.co", "name": "Alice"}
        conn.execute.assert_called_once_with("SELECT * FROM users WHERE id = ?", (1,))

    def test_get_user_by_id_exception_returns_none(self):
        conn = MagicMock()
        conn.execute.side_effect = Exception("DB error")

        repo = UserRepository(conn)
        assert repo.get_user_by_id(1) is None

    def test_create_user_success(self):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.lastrowid = 42
        conn.execute.return_value = cursor

        repo = UserRepository(conn)
        result = repo.create_user("user@example.com", "Bob Smith")

        assert result == 42
        conn.execute.assert_called_once_with(
            "INSERT INTO users (email, name) VALUES (?, ?)",
            ("user@example.com", "Bob Smith"),
        )
        conn.commit.assert_called_once()

    def test_create_user_invalid_email_returns_none(self):
        conn = MagicMock()
        repo = UserRepository(conn)
        assert repo.create_user("not-an-email", "Valid Name") is None
        conn.execute.assert_not_called()

    def test_create_user_invalid_name_returns_none(self):
        conn = MagicMock()
        repo = UserRepository(conn)
        assert repo.create_user("a@b.co", "") is None
        assert repo.create_user("a@b.co", "A") is None
        conn.execute.assert_not_called()

    def test_create_user_exception_rolls_back_and_returns_none(self):
        conn = MagicMock()
        conn.execute.side_effect = Exception("DB error")

        repo = UserRepository(conn)
        assert repo.create_user("user@example.com", "Bob") is None
        conn.rollback.assert_called_once()


class TestValidateEmail:
    def test_valid_email(self):
        assert UserRepository._validate_email("a@b.co") is True
        assert UserRepository._validate_email("user@example.com") is True
        assert UserRepository._validate_email("user.name+tag@domain.org") is True

    def test_invalid_email(self):
        assert UserRepository._validate_email("") is False
        assert UserRepository._validate_email("invalid") is False
        assert UserRepository._validate_email("a@b") is False
