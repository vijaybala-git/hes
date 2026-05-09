import numpy as np


# ---------------------------------------------------------------------------
# Bay Area (PG&E) 2025 monthly baseline prices
# ---------------------------------------------------------------------------
# Electricity: higher in summer (TOU demand peaks Jun-Sep), $/MMBtu
DEFAULT_MONTHLY_ELEC_PRICES = np.array([
    70.0,  # Jan
    70.0,  # Feb
    68.0,  # Mar
    68.0,  # Apr
    70.0,  # May
    75.0,  # Jun
    80.0,  # Jul
    80.0,  # Aug
    75.0,  # Sep
    70.0,  # Oct
    68.0,  # Nov
    70.0,  # Dec
], dtype=float)

# Gas: higher in winter (heating season), lower in summer, $/MMBtu
DEFAULT_MONTHLY_GAS_PRICES = np.array([
    18.0,  # Jan
    17.0,  # Feb
    15.0,  # Mar
    13.0,  # Apr
    11.0,  # May
    10.0,  # Jun
    10.0,  # Jul
    10.0,  # Aug
    11.0,  # Sep
    13.0,  # Oct
    16.0,  # Nov
    18.0,  # Dec
], dtype=float)


class EnergyPrice:
    """
    Models the price trajectory of a single fuel type over a simulation horizon.

    Phase 1 model: simple compound escalation applied uniformly to all months.
        price(month, year) = monthly_base_prices[month] * (1 + escalation_rate) ^ year

    Designed for extension in later phases:
      - Phase 2: price shocks (year-specific multipliers)
      - Phase 2: state/utility-specific rate schedules
      - Phase 3: TOU rate structures tied to monthly load profiles

    Parameters
    ----------
    fuel_type : str
        "electricity" or "gas" — used for labelling only.
    monthly_base_prices : array-like, shape (12,)
        Base prices for Jan-Dec in $/MMBtu. Year 0 (first simulation year)
        uses these values before any escalation is applied.
    annual_escalation_rate : float
        Annual compound escalation rate, e.g. 0.03 = 3% per year.
    """

    def __init__(self, fuel_type, monthly_base_prices, annual_escalation_rate=0.0):
        if len(monthly_base_prices) != 12:
            raise ValueError(
                f"EnergyPrice '{fuel_type}': monthly_base_prices must have "
                f"12 values, got {len(monthly_base_prices)}."
            )
        if annual_escalation_rate < -1.0:
            raise ValueError(
                f"EnergyPrice '{fuel_type}': escalation_rate must be > -1.0, "
                f"got {annual_escalation_rate}."
            )

        self.fuel_type = fuel_type
        self.monthly_base_prices = np.array(monthly_base_prices, dtype=float)
        self.annual_escalation_rate = annual_escalation_rate

    def get_monthly_prices(self, year_index):
        """
        Returns a 12-element array of prices for a given simulation year.

        Parameters
        ----------
        year_index : int
            0-indexed simulation year. Year 0 returns the base prices with
            no escalation applied.

        Returns
        -------
        np.ndarray, shape (12,)
            Prices in $/MMBtu for each month of that year.
        """
        return self.monthly_base_prices * ((1 + self.annual_escalation_rate) ** year_index)

    def get_mean_annual_price(self, year_index):
        """
        Returns the simple mean of monthly prices for a given year ($/MMBtu).
        Useful for summary charts and DataCollector reporters.
        """
        return float(np.mean(self.get_monthly_prices(year_index)))

    def get_price_series(self, n_years):
        """
        Returns a (n_years, 12) array of monthly prices over the full horizon.
        Useful for the Electricity/Gas Pricing charts in the UI.

        Parameters
        ----------
        n_years : int
            Total number of simulation years.

        Returns
        -------
        np.ndarray, shape (n_years, 12)
        """
        return np.array([self.get_monthly_prices(y) for y in range(n_years)])

    def get_annual_mean_series(self, n_years):
        """
        Returns a 1-D array of mean annual prices over the full horizon.
        Convenience wrapper around get_price_series for line charts.
        """
        return self.get_price_series(n_years).mean(axis=1)
