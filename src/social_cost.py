"""
social_cost.py — Social & Health Cost of Gas Combustion (Phase 3 §6).

Per-therm adders applied to gas consumption. Informational — never on the utility bill.
  climate_rate: EPA 2023 SC-CO2 central + ~2% upstream CH4 leakage  (~$1.07/therm)
  health_rate:  CPUC D.24-07-015 / E3 2022 outdoor air-quality adder (~$1.23/therm)
"""
from dataclasses import dataclass


@dataclass
class SocialCostConfig:
    climate_enabled: bool  = True
    climate_rate:    float = 1.07   # $/therm — EPA 2023 SC-CO2 + 2% CH4 leakage
    health_enabled:  bool  = True
    health_rate:     float = 1.23   # $/therm — CPUC D.24-07-015 / E3 2022

    @property
    def climate_eff(self) -> float:
        """Effective climate $/therm (0 when disabled)."""
        return self.climate_rate if self.climate_enabled else 0.0

    @property
    def health_eff(self) -> float:
        """Effective health $/therm (0 when disabled)."""
        return self.health_rate if self.health_enabled else 0.0

    @property
    def total_rate(self) -> float:
        """Combined effective $/therm."""
        return self.climate_eff + self.health_eff
