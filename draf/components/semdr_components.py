import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

import pandas as pd
import numpy as np
from gurobipy import GRB, Model, quicksum

from draf import Collectors, Dimensions, Params, Results, Scenario, Vars
from draf import helper as hp
from draf.abstract_component import Component
from draf.conventions import Descs
from draf.helper import conv, get_annuity_factor
from draf.prep import DataBase as db

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.WARN)


@dataclass
class SEMDRElectricDemand(Component):
    """SEMDR electricity demand with real-time IoT data integration"""

    p_el: Optional[pd.Series] = None
    profile: str = "H0"  # Hotel load profile
    annual_energy: float = 2e6  # Typical hotel: 2 GWh/year
    demand_flexibility: float = 0.05  # 5% load shedding capability
    iot_device_id: Optional[str] = None  # IoT device identifier for real-time data
    comfort_penalty: float = 100  # €/MWh penalty for load shedding

    def param_func(self, sc: Scenario):
        if self.p_el is None:
            sc.prep.P_eDem_T(profile=self.profile, annual_energy=self.annual_energy)
        else:
            sc.param("P_eDem_T", data=self.p_el, doc="SEMDR electricity demand", unit="kW_el")
        
        # Add demand response capability
        sc.param("k_eDem_flex_", data=self.demand_flexibility, doc="Demand flexibility factor")
        sc.param("c_eDem_penalty_", data=self.comfort_penalty, doc="Load shedding penalty cost", unit="€/MWh")
        
        # IoT integration parameters
        if self.iot_device_id:
            sc.param("device_id_eDem_", data=self.iot_device_id, doc="IoT device ID for demand monitoring")
        
        sc.var("P_eDem_shed_T", doc="Load shedding", unit="kW_el", ub=1000)
        sc.var("P_eDem_actual_T", doc="Actual demand after shedding", unit="kW_el")

    def model_func(self, sc: Scenario, m: Model, d: Dimensions, p: Params, v: Vars, c: Collectors):
        # Actual demand after load shedding
        m.addConstrs(
            (v.P_eDem_actual_T[t] == p.P_eDem_T[t] - v.P_eDem_shed_T[t] for t in d.T),
            "eDem_actual_demand"
        )
        
        # Base demand minus any load shedding
        c.P_EL_sink_T["eDem"] = lambda t: v.P_eDem_actual_T[t]
        
        # Limit load shedding to flexibility capacity
        m.addConstrs(
            (v.P_eDem_shed_T[t] <= p.k_eDem_flex_ * p.P_eDem_T[t] for t in d.T),
            "eDem_load_shed_limit"
        )
        
        # Cost penalty for load shedding (guest comfort impact)
        penalty_cost = quicksum(v.P_eDem_shed_T[t] * p.c_eDem_penalty_ for t in d.T)
        c.C_TOT_op_["eDem_penalty"] = penalty_cost * p.k__dT_ * conv("€", "k€", 1e-3)

    def get_iot_data_schema(self) -> Dict:
        """Return expected IoT data schema for integration"""
        return {
            "device_id": self.iot_device_id,
            "measurement_type": "electrical_demand",
            "expected_fields": ["power", "voltage", "current", "timestamp"],
            "topic_pattern": f"devices/{self.iot_device_id}/electrical/measurement",
            "data_frequency": "1min",  # Expected data frequency
            "units": {"power": "kW", "voltage": "V", "current": "A"}
        }


@dataclass 
class SEMDRHVAC(Component):
    """SEMDR HVAC system with IoT sensors and thermal mass modeling"""
    
    heating_cap: float = 500  # kW thermal
    cooling_cap: float = 400  # kW thermal  
    cop_heating: float = 3.5
    cop_cooling: float = 3.0
    comfort_deadband: float = 2.0  # °C flexibility for demand response
    thermal_mass_hours: float = 4.0  # Hours of thermal inertia
    temp_sensor_ids: Optional[List[str]] = None  # IoT temperature sensor IDs
    occupancy_sensor_ids: Optional[List[str]] = None  # IoT occupancy sensor IDs
    
    def dim_func(self, sc: Scenario):
        # Simplified temperature levels for hotel comfort
        sc.dim("H", data=["22/18"], doc="Heating temperature levels (supply/return) in °C")
        sc.dim("N", data=["7/12"], doc="Cooling temperature levels (supply/return) in °C")

    def param_func(self, sc: Scenario):
        # Heating demand
        sc.param(name="dQ_hDem_TH", fill=0, doc="SEMDR heating demand", unit="kW_th")
        if hasattr(sc.prep, 'dQ_hDem_T'):
            sc.params.dQ_hDem_TH.loc[:, sc.dims.H[0]] = sc.prep.dQ_hDem_T(annual_energy=3e5).values
        
        # Cooling demand  
        sc.param(name="dQ_cDem_TN", fill=0, doc="SEMDR cooling demand", unit="kW_th")
        if hasattr(sc.prep, 'dQ_cDem_T'):
            sc.params.dQ_cDem_TN.loc[:, sc.dims.N[0]] = sc.prep.dQ_cDem_T(annual_energy=2e5).values
            
        # HVAC system parameters
        sc.param("P_HVAC_heat_cap_", data=self.heating_cap, doc="Heating capacity", unit="kW_el")
        sc.param("P_HVAC_cool_cap_", data=self.cooling_cap, doc="Cooling capacity", unit="kW_el") 
        sc.param("COP_heat_", data=self.cop_heating, doc="Heating COP")
        sc.param("COP_cool_", data=self.cop_cooling, doc="Cooling COP")
        sc.param("k_comfort_flex_", data=self.comfort_deadband, doc="Comfort flexibility", unit="°C")
        sc.param("k_thermal_mass_", data=self.thermal_mass_hours, doc="Thermal mass time constant", unit="h")
        
        # IoT sensor integration
        if self.temp_sensor_ids:
            sc.param("temp_sensor_ids_", data=self.temp_sensor_ids, doc="Temperature sensor device IDs")
        if self.occupancy_sensor_ids:
            sc.param("occupancy_sensor_ids_", data=self.occupancy_sensor_ids, doc="Occupancy sensor device IDs")
        
        # Variables
        sc.var("P_HVAC_heat_T", doc="Heating power consumption", unit="kW_el")
        sc.var("P_HVAC_cool_T", doc="Cooling power consumption", unit="kW_el")
        sc.var("dQ_HVAC_heat_T", doc="Heating output", unit="kW_th")
        sc.var("dQ_HVAC_cool_T", doc="Cooling output", unit="kW_th")
        
        # Thermal comfort flexibility (temperature setpoint adjustment)
        sc.var("deltaT_comfort_T", doc="Temperature setpoint adjustment", unit="°C", 
               lb=-self.comfort_deadband, ub=self.comfort_deadband)
        
        # Thermal mass energy storage
        sc.var("E_thermal_T", doc="Thermal energy stored in building mass", unit="kWh_th")

    def model_func(self, sc: Scenario, m: Model, d: Dimensions, p: Params, v: Vars, c: Collectors):
        # Heat pump relationships
        m.addConstrs((v.dQ_HVAC_heat_T[t] == v.P_HVAC_heat_T[t] * p.COP_heat_ for t in d.T), "HVAC_heat_balance")
        m.addConstrs((v.dQ_HVAC_cool_T[t] == v.P_HVAC_cool_T[t] * p.COP_cool_ for t in d.T), "HVAC_cool_balance")
        
        # Capacity limits
        m.addConstrs((v.P_HVAC_heat_T[t] <= p.P_HVAC_heat_cap_ for t in d.T), "HVAC_heat_cap")
        m.addConstrs((v.P_HVAC_cool_T[t] <= p.P_HVAC_cool_cap_ for t in d.T), "HVAC_cool_cap")
        
        # Thermal mass energy balance (simplified)
        m.addConstrs(
            (v.E_thermal_T[t] == (0 if t == d.T[0] else v.E_thermal_T[t-1]) * (1 - 1/p.k_thermal_mass_)
             + (v.dQ_HVAC_heat_T[t] - v.dQ_HVAC_cool_T[t] - p.dQ_hDem_TH[t, "22/18"] + p.dQ_cDem_TN[t, "7/12"]) * p.k__dT_
             for t in d.T), "thermal_mass_balance"
        )
        
        # Demand response: flexible heating/cooling based on comfort deadband and thermal mass
        m.addConstrs(
            (v.dQ_HVAC_heat_T[t] >= p.dQ_hDem_TH[t, "22/18"] * (1 - 0.1 * v.deltaT_comfort_T[t] / p.k_comfort_flex_) 
             for t in d.T), "HVAC_heat_flexibility"
        )
        m.addConstrs(
            (v.dQ_HVAC_cool_T[t] >= p.dQ_cDem_TN[t, "7/12"] * (1 - 0.1 * (-v.deltaT_comfort_T[t]) / p.k_comfort_flex_) 
             for t in d.T), "HVAC_cool_flexibility"
        )
        
        # Connect to energy flows
        c.P_EL_sink_T["HVAC"] = lambda t: v.P_HVAC_heat_T[t] + v.P_HVAC_cool_T[t]
        c.dQ_heating_source_TH["HVAC"] = lambda t, h: v.dQ_HVAC_heat_T[t] if h == "22/18" else 0
        c.dQ_cooling_source_TN["HVAC"] = lambda t, n: v.dQ_HVAC_cool_T[t] if n == "7/12" else 0

    def get_iot_data_schema(self) -> Dict:
        """Return expected IoT data schema for HVAC sensors"""
        schema = {
            "measurement_type": "hvac_environmental",
            "expected_fields": ["temperature", "humidity", "pressure", "timestamp"],
            "data_frequency": "1min",
            "units": {"temperature": "°C", "humidity": "%", "pressure": "hPa"}
        }
        
        if self.temp_sensor_ids:
            schema["temperature_sensors"] = [
                {
                    "device_id": sensor_id,
                    "topic_pattern": f"devices/{sensor_id}/environmental/measurement",
                    "location": f"zone_{i+1}"
                } for i, sensor_id in enumerate(self.temp_sensor_ids)
            ]
        
        if self.occupancy_sensor_ids:
            schema["occupancy_sensors"] = [
                {
                    "device_id": sensor_id,
                    "topic_pattern": f"devices/{sensor_id}/occupancy/measurement",
                    "expected_fields": ["is_occupied", "occupancy_count", "timestamp"],
                    "location": f"zone_{i+1}"
                } for i, sensor_id in enumerate(self.occupancy_sensor_ids)
            ]
        
        return schema


@dataclass
class SEMDRBattery(Component):
    """SEMDR battery energy storage optimized for demand response with IoT monitoring"""

    E_CAPx: float = 0  # Existing capacity
    allow_new: bool = True
    max_cycles_per_day: float = 1.5  # Battery health protection
    battery_monitor_id: Optional[str] = None  # IoT device for battery monitoring

    def param_func(self, sc: Scenario):
        sc.param("E_BES_CAPx_", data=self.E_CAPx, doc="Existing battery capacity", unit="kWh_el")
        sc.param("k_BES_ini_", data=0.5, doc="Initial and final SOC")
        
        # SEMDR-specific battery parameters (more conservative for longevity)
        sc.param("eta_BES_ch_", data=0.95, doc="Charging efficiency")
        sc.param("eta_BES_dis_", data=0.95, doc="Discharging efficiency")
        sc.param("eta_BES_self_", data=0.001, doc="Self-discharge per hour")
        sc.param("k_BES_inPerCap_", data=0.5, doc="Max charging rate (C-rate)")
        sc.param("k_BES_outPerCap_", data=0.5, doc="Max discharging rate (C-rate)")
        
        # Cycle limit for battery health
        sc.param("k_BES_maxCycles_", data=self.max_cycles_per_day, doc="Max daily cycles")
        
        # IoT monitoring
        if self.battery_monitor_id:
            sc.param("battery_monitor_id_", data=self.battery_monitor_id, doc="Battery monitoring device ID")
        
        sc.var("E_BES_T", doc="Battery energy stored", unit="kWh_el")
        sc.var("P_BES_in_T", doc="Charging power", unit="kW_el")
        sc.var("P_BES_out_T", doc="Discharging power", unit="kW_el")
        sc.var("SOC_BES_T", doc="State of charge", unit="%", lb=0, ub=100)

        if sc.consider_invest:
            sc.param("z_BES_", data=int(self.allow_new), doc="If new capacity is allowed")
            sc.param("c_BES_inv_", data=800, doc="Battery investment cost", unit="€/kWh")  # Current Li-ion costs
            sc.param("k_BES_RMI_", data=0.02, doc="Annual maintenance factor")
            sc.param("N_BES_", data=15, doc="Battery lifetime", unit="years")
            sc.var("E_BES_CAPn_", doc="New capacity", unit="kWh_el")

    def model_func(self, sc: Scenario, m: Model, d: Dimensions, p: Params, v: Vars, c: Collectors):
        cap = p.E_BES_CAPx_ + v.E_BES_CAPn_ if sc.consider_invest else p.E_BES_CAPx_
        
        # Power limits
        m.addConstrs((v.P_BES_in_T[t] <= p.k_BES_inPerCap_ * cap for t in d.T), "BES_charge_limit")
        m.addConstrs((v.P_BES_out_T[t] <= p.k_BES_outPerCap_ * cap for t in d.T), "BES_discharge_limit")
        
        # Energy limits
        m.addConstrs((v.E_BES_T[t] <= cap for t in d.T), "BES_energy_limit")
        m.addConstr((v.E_BES_T[d.T[-1]] == p.k_BES_ini_ * cap), "BES_final_SOC")
        
        # State of charge calculation
        m.addConstrs((v.SOC_BES_T[t] == 100 * v.E_BES_T[t] / cap for t in d.T), "BES_SOC_calc")
        
        # Energy balance
        m.addConstrs(
            (v.E_BES_T[t] == (p.k_BES_ini_ * cap if t == d.T[0] else v.E_BES_T[t - 1])
             * (1 - p.eta_BES_self_ * p.k__dT_)
             + (v.P_BES_in_T[t] * p.eta_BES_ch_ - v.P_BES_out_T[t] / p.eta_BES_dis_) * p.k__dT_
             for t in d.T), "BES_energy_balance"
        )
        
        # Cycle limit constraint (simplified)
        total_throughput = quicksum(v.P_BES_in_T[t] + v.P_BES_out_T[t] for t in d.T) * p.k__dT_
        m.addConstr(total_throughput <= p.k_BES_maxCycles_ * cap * 2, "BES_cycle_limit")
        
        # Connect to power flows
        c.P_EL_source_T["BES"] = lambda t: v.P_BES_out_T[t]
        c.P_EL_sink_T["BES"] = lambda t: v.P_BES_in_T[t]
        
        if sc.consider_invest:
            m.addConstr((v.E_BES_CAPn_ <= p.z_BES_ * 2000), "BES_max_investment")  # Max 2MWh
            C_inv_ = v.E_BES_CAPn_ * p.c_BES_inv_ * conv("€", "k€", 1e-3)
            c.C_TOT_inv_["BES"] = C_inv_
            c.C_TOT_invAnn_["BES"] = C_inv_ * get_annuity_factor(r=p.k__r_, N=p.N_BES_)
            c.C_TOT_RMI_["BES"] = C_inv_ * p.k_BES_RMI_

    def get_iot_data_schema(self) -> Dict:
        """Return expected IoT data schema for battery monitoring"""
        if not self.battery_monitor_id:
            return {}
            
        return {
            "device_id": self.battery_monitor_id,
            "measurement_type": "battery_monitoring",
            "topic_pattern": f"devices/{self.battery_monitor_id}/battery/measurement",
            "expected_fields": ["voltage", "current", "power", "soc", "temperature", "timestamp"],
            "data_frequency": "1min",
            "units": {
                "voltage": "V",
                "current": "A", 
                "power": "kW",
                "soc": "%",
                "temperature": "°C"
            },
            "alerts": {
                "low_soc": {"threshold": 20, "unit": "%"},
                "high_temp": {"threshold": 45, "unit": "°C"},
                "over_current": {"threshold": "rated_capacity * 1.1", "unit": "A"}
            }
        }


@dataclass
class SEMDRPV(Component):
    """SEMDR photovoltaic system with IoT weather monitoring and feed-in management"""

    P_CAPx: float = 0
    A_avail_: float = 500  # Available roof area
    allow_new: bool = True
    weather_station_id: Optional[str] = None  # IoT weather monitoring device
    inverter_monitor_id: Optional[str] = None  # IoT inverter monitoring device

    def param_func(self, sc: Scenario):
        sc.param("P_PV_CAPx_", data=self.P_CAPx, doc="Existing PV capacity", unit="kW_peak")
        sc.prep.P_PV_profile_T(use_coords=True)
        sc.var("P_PV_total_T", doc="Total PV generation", unit="kW_el") 
        sc.var("P_PV_self_T", doc="Self-consumption", unit="kW_el")
        sc.var("P_PV_feedin_T", doc="Grid feed-in", unit="kW_el")
        sc.var("PV_efficiency_T", doc="Real-time PV efficiency", unit="%", lb=0, ub=120)
        
        sc.param("A_PV_PerPeak_", data=6.0, doc="PV area per kW", unit="m²/kW_peak")
        sc.param("A_PV_avail_", data=self.A_avail_, doc="Available roof area", unit="m²")

        # IoT monitoring
        if self.weather_station_id:
            sc.param("weather_station_id_", data=self.weather_station_id, doc="Weather monitoring device ID")
        if self.inverter_monitor_id:
            sc.param("inverter_monitor_id_", data=self.inverter_monitor_id, doc="Inverter monitoring device ID")

        if sc.consider_invest:
            sc.param("z_PV_", data=int(self.allow_new), doc="If new PV is allowed")
            sc.param("c_PV_inv_", data=1200, doc="PV investment cost", unit="€/kW_peak")
            sc.param("k_PV_RMI_", data=0.015, doc="Annual maintenance factor")
            sc.param("N_PV_", data=25, doc="PV lifetime", unit="years")
            sc.var("P_PV_CAPn_", doc="New PV capacity", unit="kW_peak")

    def model_func(self, sc: Scenario, m: Model, d: Dimensions, p: Params, v: Vars, c: Collectors):
        cap = p.P_PV_CAPx_ + v.P_PV_CAPn_ if sc.consider_invest else p.P_PV_CAPx_
        
        # PV efficiency tracking (default 100% if no real-time data)
        m.addConstrs((v.PV_efficiency_T[t] == 100 for t in d.T), "PV_default_efficiency")
        
        # PV generation split with efficiency factor
        m.addConstrs(
            (cap * p.P_PV_profile_T[t] * v.PV_efficiency_T[t] / 100 == v.P_PV_self_T[t] + v.P_PV_feedin_T[t] 
             for t in d.T), "PV_generation_split"
        )
        
        # Total generation for reporting
        m.addConstrs(
            (v.P_PV_total_T[t] == cap * p.P_PV_profile_T[t] * v.PV_efficiency_T[t] / 100 for t in d.T), 
            "PV_total_gen"
        )
        
        # Connect to power flows
        c.P_EL_source_T["PV"] = lambda t: v.P_PV_self_T[t]
        c.P_EG_sell_T["PV"] = lambda t: v.P_PV_feedin_T[t]

        if sc.consider_invest:
            m.addConstr(v.P_PV_CAPn_ <= p.z_PV_ * p.A_PV_avail_ / p.A_PV_PerPeak_, "PV_area_limit")
            C_inv_ = v.P_PV_CAPn_ * p.c_PV_inv_ * conv("€", "k€", 1e-3)
            c.C_TOT_inv_["PV"] = C_inv_
            c.C_TOT_invAnn_["PV"] = C_inv_ * get_annuity_factor(r=p.k__r_, N=p.N_PV_)
            c.C_TOT_RMI_["PV"] = C_inv_ * p.k_PV_RMI_

    def get_iot_data_schema(self) -> Dict:
        """Return expected IoT data schema for PV monitoring"""
        schema = {
            "measurement_type": "pv_system",
            "data_frequency": "1min"
        }
        
        if self.weather_station_id:
            schema["weather_station"] = {
                "device_id": self.weather_station_id,
                "topic_pattern": f"devices/{self.weather_station_id}/weather/measurement",
                "expected_fields": ["solar_irradiance", "temperature", "humidity", "wind_speed", "timestamp"],
                "units": {
                    "solar_irradiance": "W/m²",
                    "temperature": "°C",
                    "humidity": "%",
                    "wind_speed": "m/s"
                }
            }
        
        if self.inverter_monitor_id:
            schema["inverter_monitor"] = {
                "device_id": self.inverter_monitor_id,
                "topic_pattern": f"devices/{self.inverter_monitor_id}/inverter/measurement",
                "expected_fields": ["ac_power", "dc_power", "efficiency", "temperature", "timestamp"],
                "units": {
                    "ac_power": "kW",
                    "dc_power": "kW", 
                    "efficiency": "%",
                    "temperature": "°C"
                }
            }
        
        return schema


@dataclass
class SEMDRGrid(Component):
    """SEMDR grid connection with demand response tariffs and IoT smart meter integration"""

    c_buyPeak: float = 50.0
    selected_tariff: str = "TOU"  # Time-of-use more common for hotels
    maxsell: float = 500  # Limited feed-in
    maxbuy: float = 2000  # Peak demand limit
    demand_charge: float = 120  # €/kW/month demand charge
    smart_meter_id: Optional[str] = None  # IoT smart meter device ID
    grid_monitor_id: Optional[str] = None  # IoT grid quality monitor

    def param_func(self, sc: Scenario):
        sc.collector("P_EG_sell_T", doc="Electricity sold to grid", unit="kW_el")
        sc.param("c_EG_buyPeak_", data=self.c_buyPeak, doc="Peak demand charge", unit="€/kW_el/month")
        
        # Prepare tariff data
        if self.selected_tariff == "TOU":
            sc.prep.c_EG_TOU_T()
        else:
            sc.prep.c_EG_RTP_T()
            
        sc.param("c_EG_T", data=getattr(sc.params, f"c_EG_{self.selected_tariff}_T"), 
                doc="Electricity tariff", unit="€/kWh_el")
        sc.prep.c_EG_addon_()
        sc.prep.ce_EG_T()
        
        # IoT integration
        if self.smart_meter_id:
            sc.param("smart_meter_id_", data=self.smart_meter_id, doc="Smart meter device ID")
        if self.grid_monitor_id:
            sc.param("grid_monitor_id_", data=self.grid_monitor_id, doc="Grid quality monitor device ID")
        
        sc.var("P_EG_buy_T", doc="Grid electricity purchase", unit="kW_el")
        sc.var("P_EG_sell_T", doc="Grid electricity sale", unit="kW_el", ub=self.maxsell)
        sc.var("P_EG_peak_", doc="Monthly peak demand", unit="kW_el", ub=self.maxbuy)
        sc.var("P_EG_net_T", doc="Net grid power (positive = import)", unit="kW_el")

    def model_func(self, sc: Scenario, m: Model, d: Dimensions, p: Params, v: Vars, c: Collectors):
        # Net power calculation
        m.addConstrs(
            (v.P_EG_net_T[t] == v.P_EG_buy_T[t] - v.P_EG_sell_T[t] for t in d.T),
            "EG_net_power"
        )
        
        # Peak demand tracking
        m.addConstrs((v.P_EG_buy_T[t] <= v.P_EG_peak_ for t in d.T), "EG_peak_tracking")
        
        # Grid feed-in collection
        m.addConstrs(
            (v.P_EG_sell_T[t] == sum(x(t) for x in c.P_EG_sell_T.values()) for t in d.T), 
            "EG_feedin_collection"
        )

        # Connect to power flows
        c.P_EL_source_T["EG"] = lambda t: v.P_EG_buy_T[t]
        c.P_EL_sink_T["EG"] = lambda t: v.P_EG_sell_T[t]
        
        # Costs
        c.C_TOT_op_["EG_energy"] = (
            p.k__dT_ * p.k__PartYearComp_ * quicksum(
                v.P_EG_buy_T[t] * (p.c_EG_T[t] + p.c_EG_addon_) - v.P_EG_sell_T[t] * p.c_EG_T[t] * 0.7  # 70% feed-in tariff
                for t in d.T
            ) * conv("€", "k€", 1e-3)
        )
        c.C_TOT_op_["EG_demand"] = v.P_EG_peak_ * p.c_EG_buyPeak_ * 12 * conv("€", "k€", 1e-3)  # Monthly charge
        
        # Emissions
        c.CE_TOT_["EG"] = (
            p.k__dT_ * p.k__PartYearComp_ * quicksum(
                p.ce_EG_T[t] * (v.P_EG_buy_T[t] - v.P_EG_sell_T[t]) for t in d.T
            )
        )

    def get_iot_data_schema(self) -> Dict:
        """Return expected IoT data schema for grid monitoring"""
        schema = {
            "measurement_type": "grid_connection",
            "data_frequency": "1min"
        }
        
        if self.smart_meter_id:
            schema["smart_meter"] = {
                "device_id": self.smart_meter_id,
                "topic_pattern": f"devices/{self.smart_meter_id}/meter/measurement",
                "expected_fields": ["active_power", "reactive_power", "voltage", "current", "frequency", "timestamp"],
                "units": {
                    "active_power": "kW",
                    "reactive_power": "kVAr",
                    "voltage": "V",
                    "current": "A",
                    "frequency": "Hz"
                }
            }
        
        if self.grid_monitor_id:
            schema["grid_monitor"] = {
                "device_id": self.grid_monitor_id,
                "topic_pattern": f"devices/{self.grid_monitor_id}/grid/measurement",
                "expected_fields": ["voltage_thd", "current_thd", "power_factor", "timestamp"],
                "units": {
                    "voltage_thd": "%",
                    "current_thd": "%",
                    "power_factor": ""
                }
            }
        
        return schema


@dataclass
class SEMDRMain(Component):
    """Main optimization component for SEMDR energy system with IoT integration"""

    def param_func(self, sc: Scenario):
        # Core collectors (simplified for SEMDR)
        sc.collector("P_EL_source_T", doc="Electricity sources", unit="kW_el")
        sc.collector("P_EL_sink_T", doc="Electricity sinks", unit="kW_el")
        sc.collector("dQ_cooling_source_TN", doc="Cooling sources", unit="kW_th")
        sc.collector("dQ_cooling_sink_TN", doc="Cooling sinks", unit="kW_th")
        sc.collector("dQ_heating_source_TH", doc="Heating sources", unit="kW_th")
        sc.collector("dQ_heating_sink_TH", doc="Heating sinks", unit="kW_th")
        sc.collector("C_TOT_", doc="Total costs", unit="k€/a")
        sc.collector("C_TOT_op_", doc="Operating costs", unit="k€/a")
        sc.collector("CE_TOT_", doc="Carbon emissions", unit="kgCO2eq/a")

        if sc.consider_invest:
            sc.collector("C_TOT_inv_", doc="Investment costs", unit="k€")
            sc.collector("C_TOT_invAnn_", doc="Annualized investment costs", unit="k€/a")
            sc.collector("C_TOT_RMI_", doc="Maintenance costs", unit="k€/a")

        # Objective variables
        sc.var("C_TOT_", doc="Total costs", unit="k€/a", lb=-GRB.INFINITY)
        sc.var("C_TOT_op_", doc="Operating costs", unit="k€/a", lb=-GRB.INFINITY)
        sc.var("CE_TOT_", doc="Total emissions", unit="kgCO2eq/a", lb=-GRB.INFINITY)

        if sc.consider_invest:
            sc.param("k__r_", data=0.04, doc="Interest rate (lower for commercial)")
            sc.var("C_TOT_inv_", doc="Investment costs", unit="k€")
            sc.var("C_TOT_invAnn_", doc="Annualized investment costs", unit="k€/a")
            sc.var("C_TOT_RMI_", doc="Maintenance costs", unit="k€/a")

        # SEMDR-specific objective weighting (cost-focused with sustainability)
        sc.param("k_PTO_alpha_", data=0.1, doc="Emissions weighting (10%)")
        sc.param("k_PTO_C_", data=1, doc="Cost normalization")
        sc.param("k_PTO_CE_", data=1/5e3, doc="Emissions normalization")

    def model_func(self, sc: Scenario, m: Model, d: Dimensions, p: Params, v: Vars, c: Collectors):
        # Objective: minimize costs with emissions penalty
        m.setObjective(
            (1 - p.k_PTO_alpha_) * v.C_TOT_ * p.k_PTO_C_ + p.k_PTO_alpha_ * v.CE_TOT_ * p.k_PTO_CE_,
            GRB.MINIMIZE
        )

        # Cost balance
        m.addConstr(v.C_TOT_op_ == quicksum(c.C_TOT_op_.values()), "operating_costs")
        c.C_TOT_["op"] = v.C_TOT_op_

        if sc.consider_invest:
            m.addConstr(v.C_TOT_inv_ == quicksum(c.C_TOT_inv_.values()), "investment_costs")
            m.addConstr(v.C_TOT_RMI_ == quicksum(c.C_TOT_RMI_.values()), "maintenance_costs")
            m.addConstr(v.C_TOT_invAnn_ == quicksum(c.C_TOT_invAnn_.values()), "annualized_investment")
            c.C_TOT_op_["RMI"] = v.C_TOT_RMI_
            c.C_TOT_["inv"] = v.C_TOT_invAnn_

        m.addConstr(v.C_TOT_ == quicksum(c.C_TOT_.values()), "total_costs")
        m.addConstr(v.CE_TOT_ == p.k__PartYearComp_ * quicksum(c.CE_TOT_.values()), "total_emissions")

        # Energy balances
        m.addConstrs(
            (quicksum(x(t) for x in c.P_EL_source_T.values()) == 
             quicksum(x(t) for x in c.P_EL_sink_T.values()) for t in d.T),
            "electricity_balance"
        )

        # Thermal balances (if HVAC components are present)
        if hasattr(d, "N"):
            m.addConstrs(
                (quicksum(x(t, n) for x in c.dQ_cooling_source_TN.values()) == 
                 quicksum(x(t, n) for x in c.dQ_cooling_sink_TN.values()) for t in d.T for n in d.N),
                "cooling_balance"
            )

        if hasattr(d, "H"):
            m.addConstrs(
                (quicksum(x(t, h) for x in c.dQ_heating_source_TH.values()) == 
                 quicksum(x(t, h) for x in c.dQ_heating_sink_TH.values()) for t in d.T for h in d.H),
                "heating_balance"
            )

    def get_system_iot_schema(self, components: List[Component]) -> Dict:
        """Return complete IoT data schema for the entire SEMDR system"""
        system_schema = {
            "system_name": "SEMDR",
            "version": "1.0",
            "data_collection": {
                "base_frequency": "1min",
                "aggregation_levels": ["1min", "5min", "15min", "30min", "60min"],
                "retention_policy": {
                    "raw_data": "7 days",
                    "5min_aggregated": "30 days", 
                    "15min_aggregated": "1 year",
                    "hourly_aggregated": "5 years"
                }
            },
            "aws_integration": {
                "iot_core_topics": [],
                "timestream_database": "semdr_iot_db",
                "s3_bucket": "semdr-iot-data-bucket",
                "lambda_processor": "iot-rds-handler"
            },
            "device_schemas": {}
        }
        
        # Collect schemas from all components
        for component in components:
            if hasattr(component, 'get_iot_data_schema'):
                schema = component.get_iot_data_schema()
                if schema:
                    component_name = component.__class__.__name__
                    system_schema["device_schemas"][component_name] = schema
                    
                    # Extract topic patterns for AWS IoT Core
                    if "topic_pattern" in schema:
                        system_schema["aws_integration"]["iot_core_topics"].append(schema["topic_pattern"])
                    
                    # Extract topics from nested sensors
                    for key, value in schema.items():
                        if isinstance(value, list):
                            for item in value:
                                if isinstance(item, dict) and "topic_pattern" in item:
                                    system_schema["aws_integration"]["iot_core_topics"].append(item["topic_pattern"])
        
        return system_schema


# Component ordering for SEMDR system
semdr_order_restrictions = [
    ("SEMDRElectricDemand", {}),
    ("SEMDRHVAC", {}),
    ("SEMDRGrid", {"SEMDRPV"}),  # Grid collects PV feed-in
    ("SEMDRBattery", {}),
    ("SEMDRPV", {}),
    ("SEMDRMain", ["SEMDRElectricDemand", "SEMDRHVAC", "SEMDRGrid", "SEMDRBattery", "SEMDRPV"]),
]

# Set component order
from draf.helper import set_component_order_by_order_restrictions
set_component_order_by_order_restrictions(order_restrictions=semdr_order_restrictions, classes=globals())


# IoT Data Integration Helper Functions
class SEMDRIoTIntegration:
    """Helper class for SEMDR IoT data integration"""
    
    @staticmethod
    def create_timestream_query(device_id: str, measurement_type: str, start_time: str, end_time: str) -> str:
        """Generate Timestream query for device data"""
        return f"""
        SELECT 
            time,
            device_id,
            measure_name,
            measure_value::double as value
        FROM "semdr_iot_db"."device_metrics"
        WHERE device_id = '{device_id}'
        AND time BETWEEN '{start_time}' AND '{end_time}'
        AND measure_name IN (
            SELECT DISTINCT measure_name 
            FROM "semdr_iot_db"."device_metrics" 
            WHERE device_id = '{device_id}'
        )
        ORDER BY time ASC
        """
    
    @staticmethod
    def transform_iot_to_draf(iot_data: pd.DataFrame, target_frequency: str = "15min") -> pd.DataFrame:
        """Transform IoT data to DRAF-compatible format"""
        # Ensure datetime index
        if 'time' in iot_data.columns:
            iot_data['time'] = pd.to_datetime(iot_data['time'])
            iot_data = iot_data.set_index('time')
        
        # Pivot to get measurements as columns
        if 'measure_name' in iot_data.columns and 'value' in iot_data.columns:
            iot_data = iot_data.pivot_table(
                index=iot_data.index, 
                columns='measure_name', 
                values='value',
                aggfunc='mean'
            )
        
        # Resample to target frequency
        freq_map = {
            "1min": "1T",
            "5min": "5T", 
            "15min": "15T",
            "30min": "30T",
            "60min": "1H"
        }
        
        if target_frequency in freq_map:
            iot_data = iot_data.resample(freq_map[target_frequency]).mean()
        
        return iot_data
    
    @staticmethod
    def validate_iot_data(iot_data: pd.DataFrame, expected_schema: Dict) -> Dict:
        """Validate IoT data against expected schema"""
        validation_result = {
            "valid": True,
            "missing_fields": [],
            "extra_fields": [],
            "data_quality": {}
        }
        
        expected_fields = expected_schema.get("expected_fields", [])
        actual_fields = list(iot_data.columns)
        
        # Check for missing and extra fields
        validation_result["missing_fields"] = [f for f in expected_fields if f not in actual_fields]
        validation_result["extra_fields"] = [f for f in actual_fields if f not in expected_fields]
        
        # Data quality checks
        for field in expected_fields:
            if field in iot_data.columns:
                field_data = iot_data[field]
                validation_result["data_quality"][field] = {
                    "null_percentage": field_data.isnull().mean() * 100,
                    "min_value": field_data.min(),
                    "max_value": field_data.max(),
                    "mean_value": field_data.mean(),
                    "data_points": len(field_data)
                }
        
        # Set overall validity
        if validation_result["missing_fields"] or any(
            v["null_percentage"] > 10 for v in validation_result["data_quality"].values()
        ):
            validation_result["valid"] = False
        
        return validation_result 