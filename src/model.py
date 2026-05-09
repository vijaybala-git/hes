import mesa
import numpy as np
import json
import os
from energy_consumer import EnergyConsumer
from energy_price import EnergyPrice, DEFAULT_MONTHLY_ELEC_PRICES, DEFAULT_MONTHLY_GAS_PRICES

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# Category keys used in device JSON — order matters for stacked charts (bottom → top)
CATEGORY_ORDER = ["Baseload", "WaterHeating", "HVAC_Cooling", "HVAC_Heating"]
CATEGORY_LABELS = {
    "Baseload":     "Baseload",
    "WaterHeating": "Water Heating",
    "HVAC_Cooling": "Cooling",
    "HVAC_Heating": "Heating",
}


class HomeSimulator(mesa.Agent):
    """
    Represents a single home containing a collection of EnergyConsumer devices.
    Aggregates device-level outputs into home-level OpEx and CapEx totals,
    and tracks annual cost history broken down by device category.

    Parameters
    ----------
    model : HESModel
    config : dict
        Parsed JSON home configuration.
    name : str
        Display name (e.g. "Baseline Home").
    overrides : dict, optional
        Per-device attribute overrides applied after loading from JSON.
        Format: {"Device Name": {"efficiency": 3.5, "age": 2}, ...}
    """

    def __init__(self, model, config, name="Home", overrides=None):
        super().__init__(model)
        self.name = name
        self.config = config
        self.devices = []

        for eq in config.get("equipment", []):
            device = EnergyConsumer(
                model=self.model,
                name=eq["name"],
                category=eq["category"],
                annual_load=eq["annual_load"],
                seasonality=eq["seasonality"],
                fuel_mix=eq["fuel_mix"],
                efficiency=eq.get("efficiency", 1.0),
                installation_cost=eq.get("installation_cost", 0),
                lifespan=eq.get("lifespan", 15),
                current_age=eq.get("current_age", 0),
            )
            self.devices.append(device)

        # Apply UI overrides (slider-adjusted values land here)
        if overrides:
            for device in self.devices:
                if device.name in overrides:
                    for attr, value in overrides[device.name].items():
                        setattr(device, attr, value)

        # --- Cumulative OpEx ---
        self.cum_gas_cost  = 0.0
        self.cum_elec_cost = 0.0
        self.total_cum_cost = 0.0

        # --- Last-year monthly breakdown ---
        self.last_year_gas_cost  = np.zeros(12)
        self.last_year_elec_cost = np.zeros(12)

        # --- CapEx by simulation year: {year: total_usd} ---
        self.capex_by_year = {}

        # --- Annual cost history by device category ---
        # {category_key: [year1_cost, year2_cost, ...]}
        # Categories follow CATEGORY_ORDER; populated in step()
        self.cost_history_by_category = {cat: [] for cat in CATEGORY_ORDER}

    def step(self):
        current_year = self.model.steps  # Mesa 3: 1-indexed

        total_monthly_gas_cost  = np.zeros(12)
        total_monthly_elec_cost = np.zeros(12)
        year_capex = 0.0

        for device in self.devices:
            device.step()
            dev_gas_cost  = device.history['gas_cost'][-1]
            dev_elec_cost = device.history['elec_cost'][-1]
            total_monthly_gas_cost  += dev_gas_cost
            total_monthly_elec_cost += dev_elec_cost

            # Accumulate this device's annual cost into its category bucket
            annual_cost = float(np.sum(dev_gas_cost) + np.sum(dev_elec_cost))
            cat = device.category
            if cat in self.cost_history_by_category:
                self.cost_history_by_category[cat].append(annual_cost)
            else:
                # Unknown category — collect under "Baseload" as fallback
                self.cost_history_by_category["Baseload"].append(annual_cost)

            for event_year, event_cost in device.capex_events:
                if event_year == current_year:
                    year_capex += event_cost

        self.last_year_gas_cost  = total_monthly_gas_cost
        self.last_year_elec_cost = total_monthly_elec_cost

        self.cum_gas_cost  += np.sum(total_monthly_gas_cost)
        self.cum_elec_cost += np.sum(total_monthly_elec_cost)
        self.total_cum_cost = self.cum_gas_cost + self.cum_elec_cost

        if year_capex > 0:
            self.capex_by_year[current_year] = (
                self.capex_by_year.get(current_year, 0.0) + year_capex
            )

    @property
    def annual_cost(self):
        """Total energy cost for the most recent simulation year (USD)."""
        return float(np.sum(self.last_year_gas_cost) + np.sum(self.last_year_elec_cost))


class HESModel(mesa.Model):
    """
    Top-level simulation model for the Home Electrification Simulator.

    Loads baseline and electrified home configurations from JSON, verifies they
    share the same location and building specs, runs annual simulation steps,
    and collects outputs for the UI.

    Parameters
    ----------
    gas_esc : float
        Annual gas price escalation rate (e.g. 0.04 = 4%/year).
    elec_esc : float
        Annual electricity price escalation rate (e.g. 0.03 = 3%/year).
    baseline_overrides : dict, optional
        UI slider overrides for baseline home devices.
    electrified_overrides : dict, optional
        UI slider overrides for electrified home devices.
    """

    def __init__(self, gas_esc=0.04, elec_esc=0.03,
                 baseline_overrides=None, electrified_overrides=None):
        super().__init__()

        # --- Energy price models ---
        self.elec_price = EnergyPrice("electricity", DEFAULT_MONTHLY_ELEC_PRICES, elec_esc)
        self.gas_price  = EnergyPrice("gas",         DEFAULT_MONTHLY_GAS_PRICES,  gas_esc)

        self.current_monthly_elec_prices = DEFAULT_MONTHLY_ELEC_PRICES.copy()
        self.current_monthly_gas_prices  = DEFAULT_MONTHLY_GAS_PRICES.copy()
        self.current_elec_rate = float(np.mean(self.current_monthly_elec_prices))
        self.current_gas_rate  = float(np.mean(self.current_monthly_gas_prices))

        # --- Load home configurations ---
        self.baseline_home    = self._load_home("baseline_home.json",    "Baseline Home",    baseline_overrides)
        self.electrified_home = self._load_home("electrified_home.json", "Electrified Home", electrified_overrides)

        # --- Verify both homes share the same location and building specs ---
        b_loc   = self.baseline_home.config.get("location", {})
        e_loc   = self.electrified_home.config.get("location", {})
        b_specs = self.baseline_home.config.get("building_specs", {})
        e_specs = self.electrified_home.config.get("building_specs", {})
        if b_loc != e_loc:
            raise ValueError(
                f"Baseline and electrified homes must share the same location.\n"
                f"  Baseline:    {b_loc}\n  Electrified: {e_loc}"
            )
        if b_specs != e_specs:
            raise ValueError(
                f"Baseline and electrified homes must share the same building specs.\n"
                f"  Baseline:    {b_specs}\n  Electrified: {e_specs}"
            )

        # Expose for UI display (read-only)
        self.location       = b_loc
        self.building_specs = b_specs

        # --- Model-level aggregate ---
        self.opex_delta = 0.0

        # --- DataCollector: one row per simulation year ---
        self.datacollector = mesa.DataCollector(
            model_reporters={
                "Baseline Cum Cost":       lambda m: m.baseline_home.total_cum_cost,
                "Electrified Cum Cost":    lambda m: m.electrified_home.total_cum_cost,
                "Opex Delta":              lambda m: m.opex_delta,
                "Baseline Annual Cost":    lambda m: m.baseline_home.annual_cost,
                "Electrified Annual Cost": lambda m: m.electrified_home.annual_cost,
                "Elec Rate":               lambda m: m.current_elec_rate,
                "Gas Rate":                lambda m: m.current_gas_rate,
            }
        )

    def _load_home(self, filename, name, overrides):
        config_path = os.path.join(_DATA_DIR, filename)
        with open(config_path, "r") as f:
            config = json.load(f)
        return HomeSimulator(self, config, name=name, overrides=overrides)

    def step(self):
        year_index = self.steps - 1  # 0-based for escalation

        self.current_monthly_elec_prices = self.elec_price.get_monthly_prices(year_index)
        self.current_monthly_gas_prices  = self.gas_price.get_monthly_prices(year_index)
        self.current_elec_rate = float(np.mean(self.current_monthly_elec_prices))
        self.current_gas_rate  = float(np.mean(self.current_monthly_gas_prices))

        self.baseline_home.step()
        self.electrified_home.step()

        self.opex_delta = (self.baseline_home.total_cum_cost
                          - self.electrified_home.total_cum_cost)

        self.datacollector.collect(self)
