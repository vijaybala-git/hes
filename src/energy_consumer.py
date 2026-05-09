import mesa
import numpy as np


class EnergyConsumer(mesa.Agent):
    """
    Base class for all energy-consuming devices in a home.

    Each device tracks its own annual energy load, seasonal distribution,
    fuel type, lifespan, and cost history. The model steps annually;
    monthly granularity comes from the seasonality vector applied inside
    each step.

    Energy unit: MMBtu (internal simulation unit throughout Phase 1).
    All cost outputs are in USD ($).

    Parameters
    ----------
    model : mesa.Model
        The parent HESModel. Must expose:
          - current_monthly_elec_prices : np.ndarray (12,)  $/MMBtu per month
          - current_monthly_gas_prices  : np.ndarray (12,)  $/MMBtu per month
          - steps : int  current simulation year (1-indexed, Mesa 3)
    name : str
        Human-readable device name (e.g. "Gas Furnace").
    category : str
        Device category (e.g. 'HVAC_Heating', 'WaterHeating', 'Baseload').
    annual_load : float
        Base energy load for a full year in MMBtu, before efficiency losses.
    seasonality : list[float]
        12-element list distributing annual_load across months (Jan-Dec).
        Must sum to 1.0 (+/-0.01 tolerance).
    fuel_mix : dict
        Fraction of load met by each fuel, e.g. {'gas': 1.0}.
    efficiency : float
        Conversion efficiency > 0. consumed_energy = load / efficiency.
        Use 1.0 for resistive loads; COP (e.g. 3.5) for heat pumps.
    installation_cost : float
        Replacement cost in USD, logged at end-of-life.
    lifespan : int
        Expected operational life in years.
    current_age : int
        Device age at simulation start (years).
    """

    def __init__(self, model, name, category, annual_load,
                 seasonality, fuel_mix, efficiency=1.0, installation_cost=0,
                 lifespan=15, current_age=0):
        super().__init__(model)

        # --- Validation ---
        if efficiency <= 0:
            raise ValueError(
                f"Device '{name}': efficiency must be > 0, got {efficiency}."
            )
        seasonality_arr = np.array(seasonality, dtype=float)
        if len(seasonality_arr) != 12:
            raise ValueError(
                f"Device '{name}': seasonality must have 12 values, "
                f"got {len(seasonality_arr)}."
            )
        total = seasonality_arr.sum()
        if not np.isclose(total, 1.0, atol=0.01):
            raise ValueError(
                f"Device '{name}': seasonality values must sum to 1.0, "
                f"got {total:.4f}."
            )

        # --- Identity ---
        self.name = name
        self.category = category

        # --- Lifecycle & CapEx ---
        self.is_active = True
        self.lifespan = lifespan
        self.age = current_age
        self.installation_cost = installation_cost
        self.capex_events = []  # list of (simulation_year, cost_usd)

        # --- Energy Profile ---
        self.annual_load = annual_load        # MMBtu
        self.seasonality = seasonality_arr
        self.efficiency = efficiency
        self.fuel_mix = fuel_mix

        # --- Monthly state (reset each step) ---
        self.monthly_elec_consumption = np.zeros(12)  # MMBtu
        self.monthly_gas_consumption  = np.zeros(12)  # MMBtu

        # --- Historical record (one entry per annual step) ---
        self.history = {
            'elec_consumption': [],  # list of 12-element arrays (MMBtu)
            'gas_consumption':  [],  # list of 12-element arrays (MMBtu)
            'elec_cost':        [],  # list of 12-element arrays (USD)
            'gas_cost':         [],  # list of 12-element arrays (USD)
        }

    def calculate_consumption(self):
        """
        Returns a 12-element array of monthly energy consumed (MMBtu).

        Formula: (annual_load * seasonality) / efficiency

        Subclasses can override for device-specific logic
        (e.g. weather-adjusted HVAC loads in Phase 3).
        """
        return (self.annual_load * self.seasonality) / self.efficiency

    def step(self):
        # Reset monthly arrays so stale values never carry forward
        self.monthly_elec_consumption = np.zeros(12)
        self.monthly_gas_consumption  = np.zeros(12)

        if not self.is_active:
            self._append_zeros_to_history()
            return

        # --- Age the device; trigger replacement at end-of-life ---
        self.age += 1
        if self.age >= self.lifespan:
            self.capex_events.append((self.model.steps, self.installation_cost))
            self.age = 0  # freshly installed; next step will age it to 1

        # --- Monthly energy consumption ---
        monthly_energy = self.calculate_consumption()

        self.monthly_elec_consumption = monthly_energy * self.fuel_mix.get('electricity', 0.0)
        self.monthly_gas_consumption  = monthly_energy * self.fuel_mix.get('gas', 0.0)

        # --- Monthly prices from model (12-element arrays, $/MMBtu) ---
        monthly_elec_prices = self.model.current_monthly_elec_prices
        monthly_gas_prices  = self.model.current_monthly_gas_prices

        # --- Record to history ---
        self.history['elec_consumption'].append(self.monthly_elec_consumption.copy())
        self.history['gas_consumption'].append(self.monthly_gas_consumption.copy())
        self.history['elec_cost'].append(self.monthly_elec_consumption * monthly_elec_prices)
        self.history['gas_cost'].append(self.monthly_gas_consumption  * monthly_gas_prices)

    def _append_zeros_to_history(self):
        """Appends zero arrays to history for an inactive device."""
        self.history['elec_consumption'].append(np.zeros(12))
        self.history['gas_consumption'].append(np.zeros(12))
        self.history['elec_cost'].append(np.zeros(12))
        self.history['gas_cost'].append(np.zeros(12))

    def annual_elec_cost(self, year):
        """Total electricity cost for a given history index (0-indexed)."""
        return float(np.sum(self.history['elec_cost'][year]))

    def annual_gas_cost(self, year):
        """Total gas cost for a given history index (0-indexed)."""
        return float(np.sum(self.history['gas_cost'][year]))
