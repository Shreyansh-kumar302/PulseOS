"""
Database Connection
===================
Lightweight database interface. Currently a mock implementation.
Replace the body of `connect()` and `query()` with a real driver
(e.g. SQLAlchemy, asyncpg) when persistence is introduced.
"""
from config import DATABASE_URI


class DatabaseConnection:
    """Manages database connection and simple operations."""

    def __init__(self, db_uri: str = None):
        self.db_uri = db_uri or DATABASE_URI
        self.connected = False

    def connect(self) -> bool:
        self.connected = True
        return True

    def query(self, sql: str, params=None) -> list:
        """Execute a query (mock implementation — returns empty list)."""
        if not self.connected:
            self.connect()
        return []
