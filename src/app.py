"""
Example: Code with issues for AI review to catch
This file contains intentional security and quality issues
"""

# Missing imports
# No type hints
# No docstrings

class UserManager:
    def __init__(self, db):
        self.db = db
             
    # SQL Injection vulnerability
    def get_user(self, user_id):
        query = f"SELECT *  FROM users WHERE id = {user_id}"  # VULNERABLE!
        return self.db.execute(query)

    # No input validation
    def create_user(self, email, password):
        # Storing password in plain text - SECURITY ISSUE!
        query = f"INSERT INTO users (email, password) VALUES ('{email}', '{password}')"
        return self.db.execute(query)

    # Complex method with no error handling
    def update_user_profile(self, user_id, data):
        user = self.get_user(user_id)
        # No null check - potential NoneType error
        user['email'] = data['email']
        user['name'] = data['name']
        user['age'] = data['age']
        user['address'] = data['address']
        user['phone'] = data['phone']
        # Repeating code
        self.db.execute(f"UPDATE users SET email='{user['email']}' WHERE id={user_id}")
        self.db.execute(f"UPDATE users SET name='{user['name']}' WHERE id={user_id}")
        self.db.execute(f"UPDATE users SET age='{user['age']}' WHERE id={user_id}")
        # No validation, no error handling
        return True

    # XSS vulnerability
    def render_user_profile(self, user_id):
        user = self.get_user(user_id)
        # Directly inserting user input into HTML - XSS risk!
        html = f"<div><h1>{user['name']}</h1><p>{user['bio']}</p></div>"
        return html

    # Hardcoded credentials
    def connect_to_api(self):
        api_key = "sk-1234567890abcdef"  # NEVER DO THIS!
        api_secret = "secret123"  # SECURITY ISSUE!
        return f"https://api.example.com?key={api_key}&secret={api_secret}"
