"""Read-only southbound adapters that normalize equipment data for Aelora."""

from .fronius import FroniusJsonAdapter
from .sunspec import SunSpecModbusFixtureAdapter

__all__ = ["FroniusJsonAdapter", "SunSpecModbusFixtureAdapter"]
