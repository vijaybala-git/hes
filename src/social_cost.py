"""
social_cost.py — Social & Health Cost of Gas Combustion (Phase 3 §6; citations Phase 6 §3a).

Per-therm adders applied to gas consumption. Informational — never on the utility bill.

The default climate rate ($1.07/therm) is two cited sub-components (Phase 6 §3a):
  • SC-CO2 combustion  $0.97/therm — EIA 5.306 kg CO2/therm × EPA 2023 central $190/tCO2
    (Rennert et al. 2022, Nature; EPA SC-GHG 2023 Report).
  • SC-CH4 leakage adder $0.10/therm — EPA SC-CH4 2023 (~$1,600/short ton CH4) × ~2%
    upstream/pipeline leakage of the therm's gas.
  Total = $1.07/therm (no numeric change from Phase 3 — the split just makes the sources explicit).

  health_rate:  CPUC D.24-07-015 / E3 2022 outdoor air-quality adder (~$1.23/therm)
"""
from dataclasses import dataclass

# Cited decomposition of the default climate rate (Phase 6 §3a) — for docs/help & the slider
# anchors. Their sum equals the SocialCostConfig.climate_rate default of $1.07/therm.
SC_CO2_COMBUSTION = 0.97   # $/therm — EIA 5.306 kgCO2/therm × EPA 2023 $190/tCO2
SC_CH4_LEAKAGE    = 0.10   # $/therm — EPA SC-CH4 2023 × ~2% pipeline leakage


@dataclass
class SocialCostConfig:
    climate_enabled: bool  = True
    climate_rate:    float = 1.07   # $/therm — SC-CO2 $0.97 (EPA 2023) + SC-CH4 $0.10 (2% leak)
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
