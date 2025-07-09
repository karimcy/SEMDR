#!/usr/bin/env python3
"""
Standalone SEMDR Components

Simplified version of SEMDR components for testing without full DRAF framework.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.WARN)


@dataclass
class SEMDRElectricDemand:
    """SEMDR electricity demand with real-time IoT data integration"""
    
    annual_energy: float = 2e6  # Typical hotel: 2 GWh/year
    demand_flexibility: float = 0.05  # 5% load shedding capability
    iot_device_id: Optional[str] = None  # IoT device identifier for real-time data
    comfort_penalty: float = 100  # €/MWh penalty for load shedding

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

    def generate_demand_response_signal(self, current_load: float, target_reduction: float, duration_minutes: int) -> Dict:
        """Generate demand response signal for load shedding"""
        target_reduction_kw = current_load * target_reduction
        
        return {
            "signal_type": "load_reduction",
            "target_reduction_kw": target_reduction_kw,
            "duration_minutes": duration_minutes,
            "priority": "medium",
            "comfort_impact": "minimal",
            "topic": f"devices/{self.iot_device_id}/control/demand_response",
            "timestamp": pd.Timestamp.now().isoformat()
        }


@dataclass 
class SEMDRHVAC:
    """SEMDR HVAC system with IoT sensors and thermal mass modeling"""
    
    heating_cap: float = 500  # kW thermal
    cooling_cap: float = 400  # kW thermal  
    cop_heating: float = 3.5
    cop_cooling: float = 3.0
    comfort_deadband: float = 2.0  # °C flexibility for demand response
    thermal_mass_hours: float = 4.0  # Hours of thermal inertia
    temp_sensor_ids: Optional[List[str]] = None  # IoT temperature sensor IDs
    occupancy_sensor_ids: Optional[List[str]] = None  # IoT occupancy sensor IDs
    hvac_control_id: Optional[str] = None  # IoT HVAC control device ID

    def __post_init__(self):
        if self.temp_sensor_ids is None:
            self.temp_sensor_ids = []
        if self.occupancy_sensor_ids is None:
            self.occupancy_sensor_ids = []

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

    def calculate_hvac_flexibility(self, current_temp: float, setpoint: float, outdoor_temp: float) -> Dict:
        """Calculate HVAC flexibility for demand response"""
        temp_diff = abs(current_temp - setpoint)
        flexibility_factor = max(0, (self.comfort_deadband - temp_diff) / self.comfort_deadband)
        
        # Estimate flexibility based on current operation
        if current_temp < setpoint:  # Heating mode
            base_power = self.heating_cap * 0.6  # Assume 60% capacity
            flexibility_kw = base_power * flexibility_factor * 0.5  # 50% can be shed
        else:  # Cooling mode
            base_power = self.cooling_cap * 0.7  # Assume 70% capacity  
            flexibility_kw = base_power * flexibility_factor * 0.4  # 40% can be shed
        
        return {
            "flexibility_kw": flexibility_kw,
            "duration_minutes": int(self.thermal_mass_hours * 60),
            "comfort_impact": "low" if flexibility_factor > 0.7 else "medium",
            "topic": f"devices/{self.hvac_control_id}/control/setpoint_adjust" if self.hvac_control_id else None
        }


@dataclass
class SEMDRBattery:
    """SEMDR battery energy storage optimized for demand response with IoT monitoring"""
    
    E_CAPx: float = 0  # Existing capacity
    allow_new: bool = True
    max_cycles_per_day: float = 1.5  # Battery health protection
    battery_monitor_id: Optional[str] = None  # IoT device for battery monitoring

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

    def optimize_battery_dispatch(self, current_soc: float, grid_price: float, forecast_prices: List[float]) -> Dict:
        """Simple battery dispatch optimization logic"""
        # Simple strategy: charge when prices are low, discharge when high
        avg_price = np.mean(forecast_prices)
        
        if current_soc < 0.2:  # Low SOC - must charge
            action = "charge"
            power_kw = min(50, self.E_CAPx * 0.5) if self.E_CAPx > 0 else 50
        elif current_soc > 0.9:  # High SOC - can discharge
            action = "discharge" if grid_price > avg_price else "hold"
            power_kw = min(50, self.E_CAPx * 0.5) if self.E_CAPx > 0 else 50
        elif grid_price < avg_price * 0.8:  # Low price - charge
            action = "charge"
            power_kw = min(30, self.E_CAPx * 0.3) if self.E_CAPx > 0 else 30
        elif grid_price > avg_price * 1.2:  # High price - discharge
            action = "discharge"
            power_kw = min(40, self.E_CAPx * 0.4) if self.E_CAPx > 0 else 40
        else:
            action = "hold"
            power_kw = 0
            
        return {
            "action": action,
            "power_kw": power_kw,
            "duration_minutes": 15,
            "topic": f"devices/{self.battery_monitor_id}/control/dispatch" if self.battery_monitor_id else None
        }


@dataclass
class SEMDRPV:
    """SEMDR photovoltaic system with IoT weather monitoring and feed-in management"""

    P_CAPx: float = 0
    A_avail_: float = 500  # Available roof area
    allow_new: bool = True
    weather_station_id: Optional[str] = None  # IoT weather monitoring device
    inverter_monitor_id: Optional[str] = None  # IoT inverter monitoring device

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
class SEMDRGrid:
    """SEMDR grid connection with demand response tariffs and IoT smart meter integration"""

    c_buyPeak: float = 50.0
    selected_tariff: str = "TOU"  # Time-of-use more common for hotels
    maxsell: float = 500  # Limited feed-in
    maxbuy: float = 2000  # Peak demand limit
    demand_charge: float = 120  # €/kW/month demand charge
    smart_meter_id: Optional[str] = None  # IoT smart meter device ID
    grid_monitor_id: Optional[str] = None  # IoT grid quality monitor

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
class SEMDRMain:
    """Main optimization component for SEMDR energy system with IoT integration"""

    def get_system_iot_schema(self, components: List) -> Dict:
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


class SEMDRIoTIntegration:
    """IoT integration helper functions for SEMDR"""
    
    @staticmethod
    def create_timestream_query(device_id: str, measurement_type: str, start_time: str, end_time: str) -> str:
        """Create AWS Timestream query for device data"""
        return f"""
        SELECT time, measure_name, measure_value::double as value
        FROM "semdr_iot_db"."device_data"
        WHERE device_id = '{device_id}'
        AND measurement_type = '{measurement_type}'
        AND time BETWEEN '{start_time}' AND '{end_time}'
        ORDER BY time ASC
        """
    
    @staticmethod
    def transform_iot_to_draf(iot_data: pd.DataFrame, target_frequency: str = "15min") -> pd.DataFrame:
        """Transform IoT data to DRAF-compatible format"""
        if iot_data.empty:
            return pd.DataFrame()
        
        # Ensure time column is datetime
        if 'time' in iot_data.columns:
            iot_data['time'] = pd.to_datetime(iot_data['time'])
            iot_data.set_index('time', inplace=True)
        
        # Pivot data if in measure_name/value format
        if 'measure_name' in iot_data.columns and 'value' in iot_data.columns:
            iot_data = iot_data.pivot_table(index='time', columns='measure_name', values='value', aggfunc='mean')
        
        # Resample to target frequency
        return iot_data.resample(target_frequency).mean()
    
    @staticmethod
    def validate_iot_data(iot_data: pd.DataFrame, expected_schema: Dict) -> Dict:
        """Validate IoT data against expected schema"""
        validation = {
            "valid": True,
            "missing_fields": [],
            "data_quality": {},
            "timestamp": pd.Timestamp.now().isoformat()
        }
        
        # Check required fields
        expected_fields = expected_schema.get("expected_fields", [])
        for field in expected_fields:
            if field not in iot_data.columns:
                validation["missing_fields"].append(field)
                validation["valid"] = False
        
        # Basic data quality checks
        for column in iot_data.columns:
            if column in expected_fields:
                null_count = iot_data[column].isnull().sum()
                total_count = len(iot_data)
                validation["data_quality"][column] = {
                    "null_percentage": (null_count / total_count * 100) if total_count > 0 else 0,
                    "min_value": float(iot_data[column].min()) if not iot_data[column].empty else None,
                    "max_value": float(iot_data[column].max()) if not iot_data[column].empty else None
                }
        
        return validation


# Backward compatibility aliases
HotelElectricDemand = SEMDRElectricDemand
HotelHVAC = SEMDRHVAC
HotelBattery = SEMDRBattery
HotelPV = SEMDRPV
HotelGrid = SEMDRGrid
HotelMain = SEMDRMain 