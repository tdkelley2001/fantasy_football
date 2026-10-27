"""Local application-service boundary for the accepted analytical engine."""

from fantasy_football.app.http import create_app
from fantasy_football.app.service import ApplicationService

__all__ = ("ApplicationService", "create_app")
