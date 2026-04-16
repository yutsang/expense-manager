"""Shared test fixtures and environment setup."""
from __future__ import annotations

import os

# Set required env vars before any app module imports Settings
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-chars-long!!")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://aegis:aegis@localhost:5432/aegis_test")
os.environ.setdefault("ENVIRONMENT", "testing")
