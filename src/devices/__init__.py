"""Phase 2 device class hierarchy — three computation methods, one interface."""
from devices.base import EnergyConsumer
from devices.seasonal import (
    SeasonalDevice, GasDryer, GasCooktop, HeatPumpDryer,
    InductionCooktop, LightsAndPlugs, Dishwasher, ElectricOven,
)
from devices.physics import (
    PhysicsDevice, GasFurnace, HeatPumpHVAC,
    GasWaterHeater, HeatPumpWaterHeater, CentralAC,
)
from devices.schedule import ScheduleDevice, EVCharger

__all__ = [
    "EnergyConsumer",
    "SeasonalDevice", "GasDryer", "GasCooktop", "HeatPumpDryer",
    "InductionCooktop", "LightsAndPlugs", "Dishwasher", "ElectricOven",
    "PhysicsDevice", "GasFurnace", "HeatPumpHVAC",
    "GasWaterHeater", "HeatPumpWaterHeater", "CentralAC",
    "ScheduleDevice", "EVCharger",
]
