"""
Pytest configuration and shared fixtures.
Adds repo root to sys.path so tests can import from src.
"""
import sys
from pathlib import Path

# Add repo root so "from src.app import ..." works when running from repo root
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
