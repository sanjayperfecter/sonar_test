"""
Unit tests for src.app (UserRepository).
"""
import pytest
from unittest.mock import MagicMock

from src.app import UserRepository


class TestUserRepository:
    """Tests for UserRepository."""

    def test_init_stores_connection(self):
        """UserRepository stores connection on instance."""
        conn = MagicMock()
        repo = UserRepository(conn)
        assert repo.connection is conn

    def test_get_user_by_id_success(self):
        """get_user_by_id returns user dict when found."""
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = {"id": 1, "email": "a@b.co", "name": "Alice"}
        conn.execute.return_value = cursor

        repo = UserRepository(conn)
        result = repo.get_user_by_id(1)

        assert result == {"id": 1, "email": "a@b.co", "name": "Alice"}
        conn.execute.assert_called_once_with("SELECT * FROM users WHERE id = ?", (1,))

    def test_get_user_by_id_not_found(self):
        """get_user_by_id returns None when fetchone returns None."""
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        conn.execute.return_value = cursor

        repo = UserRepository(conn)
        result = repo.get_user_by_id(999)

        assert result is None

    def test_get_user_by_id_exception_returns_none(self):
        """get_user_by_id returns None and logs when execute raises."""
        conn = MagicMock()
        conn.execute.side_effect = Exception("DB error")

        repo = UserRepository(conn)
        result = repo.get_user_by_id(1)

        assert result is None

    def test_create_user_success(self):
        """create_user returns new user id on success."""
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
        """create_user returns None for invalid email."""
        repo = UserRepository(MagicMock())
        result = repo.create_user("not-an-email", "Valid Name")
        assert result is None
        repo.connection.execute.assert_not_called()

    def test_create_user_invalid_name_empty_returns_none(self):
        """create_user returns None for empty name."""
        repo = UserRepository(MagicMock())
        result = repo.create_user("a@b.co", "")
        assert result is None
        repo.connection.execute.assert_not_called()

    def test_create_user_invalid_name_too_short_returns_none(self):
        """create_user returns None when name has len < 2."""
        repo = UserRepository(MagicMock())
        result = repo.create_user("a@b.co", "A")
        assert result is None
        repo.connection.execute.assert_not_called()

    def test_create_user_exception_rollback_and_returns_none(self):
        """create_user rolls back and returns None when execute raises."""
        conn = MagicMock()
        conn.execute.side_effect = Exception("DB error")

        repo = UserRepository(conn)
        result = repo.create_user("user@example.com", "Bob")

        assert result is None
        conn.rollback.assert_called_once()


class TestValidateEmail:
    """Tests for UserRepository._validate_email (static)."""

    def test_valid_email(self):
        """Valid emails return True."""
        assert UserRepository._validate_email("a@b.co") is True
        assert UserRepository._validate_email("user@example.com") is True
        assert UserRepository._validate_email("user.name+tag@domain.org") is True

    def test_invalid_email_empty(self):
        """Empty string returns False."""
        assert UserRepository._validate_email("") is False

    def test_invalid_email_no_at(self):
        """Missing @ returns False."""
        assert UserRepository._validate_email("invalid") is False

    def test_invalid_email_bad_tld(self):
        """Invalid TLD returns False."""
        assert UserRepository._validate_email("a@b") is False
