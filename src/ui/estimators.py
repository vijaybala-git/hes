"""ui/estimators.py — display-only consumption estimators (not used in the simulation).

Phase 4.5 leaf module: pure functions extracted verbatim from app.py. NOTE
`_apply_ev_efficiency_preset` stays in app.py because it writes a reactive (not pure).
"""
from ui.theme import KWH_PER_THERM


def _est_gas_furnace(afue: float, ua: int, annual_hdd: int = 1910) -> float:
    return annual_hdd * 24 * ua / (afue * 100_000)

def _est_hp_hvac_heating(cop: float, ua: int, annual_hdd: int = 1910) -> float:
    return annual_hdd * 24 * ua / (cop * 3412)

def _est_hp_hvac_cooling(seer: float, ua: int, annual_cdd: int = 340) -> float:
    return annual_cdd * 24 * ua / (seer * 1000)

def _est_gas_wh(uef: float, daily_gal: int,
                avg_inlet_f: float = 60.0, setpoint_f: float = 120.0) -> float:
    return daily_gal * 365 * 8.33 * (setpoint_f - avg_inlet_f) * 0.00001 / uef

def _est_hpwh(uef: float, daily_gal: int,
              avg_inlet_f: float = 60.0, setpoint_f: float = 120.0) -> float:
    return daily_gal * 365 * 8.33 * (setpoint_f - avg_inlet_f) * 0.000293 / uef

def _est_gas_dryer(therms_per_cycle: float, loads_per_week: int) -> float:
    return therms_per_cycle * loads_per_week * 52

def _est_hp_dryer(kwh_per_cycle: float, loads_per_week: int) -> float:
    return kwh_per_cycle * loads_per_week * 52

def _est_gas_cooktop(therms_per_meal: float, meals_per_week: int) -> float:
    return therms_per_meal * meals_per_week * 52

def _est_induction(kwh_per_meal: float, meals_per_week: int) -> float:
    return kwh_per_meal * meals_per_week * 52

def _est_ev_kwh(miles: int, kwh_per_mile: float,
                charging_eff: float = 0.90) -> float:
    return miles * kwh_per_mile / charging_eff

def _kwh_eq(therms: float) -> float:
    return therms * KWH_PER_THERM
