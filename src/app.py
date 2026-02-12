"""
Example: Well-written Python code
This file demonstrates good coding practices
"""

from typing import List, Optional, Dict
import logging

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository for user data operations"""

    def __init__(self, connection):
        self.connection = connection
    
    def get_user(self, user_id):
        query = f"SELECT * FROM users WHERE id = {user_id}"  # VULNERABLE!
        return self.db.execute(query)

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """
        Safely retrieve user by ID using parameterized query

        Args:
            user_id: The user's ID

        Returns:
            User dictionary or None if not found
        """
        try:
            # Using parameterized query to prevent SQL injection
            query = "SELECT * FROM users WHERE id = ?"
            result = self.connection.execute(query, (user_id,))
            return result.fetchone()
        except Exception as e:
            logger.error(f"Error fetching user {user_id}: {e}")
            return None

    def create_user(self, email: str, name: str) -> Optional[int]:
        """
        Create a new user with validation

        Args:
            email: User's email address
            name: User's full name

        Returns:
            New user ID or None if creation failed
        """
        # Input validation
        if not self._validate_email(email):
            logger.warning(f"Invalid email format: {email}")
            return None

        if not name or len(name) < 2:
            logger.warning("Invalid name provided")
            return None

        try:
            query = "INSERT INTO users (email, name) VALUES (?, ?)"
            cursor = self.connection.execute(query, (email, name))
            self.connection.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            self.connection.rollback()
            return None

    @staticmethod
    def _validate_email(email: str) -> bool:
        """Validate email format"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
