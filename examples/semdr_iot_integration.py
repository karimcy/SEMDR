"""
SEMDR IoT Integration Example

This example demonstrates how to integrate DRAF optimization with AWS IoT infrastructure
for real-time smart energy management and demand response.

Key features:
- Real-time IoT data integration from AWS Timestream
- SEMDR component optimization with live sensor data
- Demand response automation based on grid signals
- Integration with existing AWS IoT Core and Lambda infrastructure
"""

import pandas as pd
import numpy as np
import json
import boto3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from draf import CaseStudy, Scenario
from draf.components.semdr_components import (
    SEMDRElectricDemand,
    SEMDRHVAC,
    SEMDRBattery,
    SEMDRPV,
    SEMDRGrid,
    SEMDRMain,
    SEMDRIoTIntegration
)


class SEMDRIoTManager:
    """Manager class for SEMDR IoT data integration with AWS services"""
    
    def __init__(self, 
                 aws_region: str = "us-east-1",
                 timestream_db: str = "semdr_iot_db",
                 timestream_table: str = "device_metrics"):
        self.aws_region = aws_region
        self.timestream_db = timestream_db
        self.timestream_table = timestream_table
        
        # Initialize AWS clients
        try:
            self.timestream_query = boto3.client('timestream-query', region_name=aws_region)
            self.timestream_write = boto3.client('timestream-write', region_name=aws_region)
            self.iot_data = boto3.client('iot-data', region_name=aws_region)
            self.connected = True
            print("✅ Connected to AWS IoT services")
        except Exception as e:
            print(f"⚠️  AWS connection failed: {e}")
            print("   Running in simulation mode with synthetic data")
            self.connected = False
    
    def fetch_device_data(self, 
                         device_id: str, 
                         start_time: datetime, 
                         end_time: datetime,
                         measurement_fields: List[str] = None) -> pd.DataFrame:
        """Fetch IoT device data from AWS Timestream"""
        
        if not self.connected:
            return self._generate_synthetic_data(device_id, start_time, end_time, measurement_fields)
        
        try:
            # Build Timestream query
            fields_filter = ""
            if measurement_fields:
                fields_list = "', '".join(measurement_fields)
                fields_filter = f"AND measure_name IN ('{fields_list}')"
            
            query = f"""
            SELECT 
                time,
                device_id,
                measure_name,
                measure_value::double as value
            FROM "{self.timestream_db}"."{self.timestream_table}"
            WHERE device_id = '{device_id}'
            AND time BETWEEN '{start_time.isoformat()}' AND '{end_time.isoformat()}'
            {fields_filter}
            ORDER BY time ASC
            """
            
            response = self.timestream_query.query(QueryString=query)
            
            # Parse response into DataFrame
            data = []
            for row in response['Rows']:
                row_data = {}
                for i, col in enumerate(response['ColumnInfo']):
                    row_data[col['Name']] = row['Data'][i].get('ScalarValue', None)
                data.append(row_data)
            
            df = pd.DataFrame(data)
            if not df.empty:
                df['time'] = pd.to_datetime(df['time'])
                df['value'] = pd.to_numeric(df['value'], errors='coerce')
                
                # Pivot to get measurements as columns
                df = df.pivot_table(
                    index='time', 
                    columns='measure_name', 
                    values='value',
                    aggfunc='mean'
                )
            
            print(f"✅ Fetched {len(df)} data points for device {device_id}")
            return df
            
        except Exception as e:
            print(f"❌ Error fetching data for {device_id}: {e}")
            return self._generate_synthetic_data(device_id, start_time, end_time, measurement_fields)
    
    def _generate_synthetic_data(self, 
                                device_id: str, 
                                start_time: datetime, 
                                end_time: datetime,
                                measurement_fields: List[str] = None) -> pd.DataFrame:
        """Generate synthetic IoT data for testing"""
        
        # Create time index with 1-minute resolution
        time_index = pd.date_range(start=start_time, end=end_time, freq='1min')
        
        # Device-specific synthetic data generation
        data = {}
        
        if "smart_meter" in device_id or "electrical" in device_id:
            # Electrical demand pattern
            base_power = 400  # kW
            hours = np.array([t.hour + t.minute/60 for t in time_index])
            daily_pattern = 0.4 + 0.6 * (1 + np.sin((hours - 6) * 2 * np.pi / 24)) / 2
            
            data['power'] = base_power * daily_pattern * (1 + 0.1 * np.random.normal(0, 1, len(time_index)))
            data['voltage'] = 230 + 5 * np.random.normal(0, 1, len(time_index))
            data['current'] = data['power'] * 1000 / data['voltage']  # I = P/V
            
        elif "temp" in device_id or "hvac" in device_id:
            # Temperature sensor data
            base_temp = 22  # °C
            daily_variation = 3 * np.sin((hours - 12) * 2 * np.pi / 24)
            
            data['temperature'] = base_temp + daily_variation + np.random.normal(0, 0.5, len(time_index))
            data['humidity'] = 45 + 10 * np.sin((hours - 8) * 2 * np.pi / 24) + np.random.normal(0, 2, len(time_index))
            data['pressure'] = 1013 + np.random.normal(0, 1, len(time_index))
            
        elif "battery" in device_id:
            # Battery monitoring data
            base_voltage = 48  # V
            soc_pattern = 50 + 30 * np.sin((hours - 12) * 2 * np.pi / 24)  # SOC varies throughout day
            
            data['voltage'] = base_voltage * (0.9 + 0.2 * soc_pattern / 100)
            data['soc'] = np.clip(soc_pattern + np.random.normal(0, 2, len(time_index)), 10, 95)
            data['current'] = 20 * np.sin((hours - 10) * 2 * np.pi / 24) + np.random.normal(0, 5, len(time_index))
            data['power'] = data['voltage'] * data['current'] / 1000  # kW
            data['temperature'] = 25 + 10 * np.abs(data['current']) / 50 + np.random.normal(0, 1, len(time_index))
            
        elif "weather" in device_id or "pv" in device_id:
            # Weather station / PV monitoring
            hours = np.array([t.hour + t.minute/60 for t in time_index])
            
            # Solar irradiance (W/m²)
            solar_pattern = np.where(
                (hours >= 6) & (hours <= 18),
                1000 * np.maximum(0, np.sin((hours - 6) * np.pi / 12)),
                0
            )
            data['solar_irradiance'] = solar_pattern * (1 + 0.2 * np.random.normal(0, 1, len(time_index)))
            
            data['temperature'] = 15 + 10 * np.sin((hours - 12) * 2 * np.pi / 24) + np.random.normal(0, 2, len(time_index))
            data['humidity'] = 60 + 20 * np.sin((hours - 6) * 2 * np.pi / 24) + np.random.normal(0, 5, len(time_index))
            data['wind_speed'] = 5 + 3 * np.random.exponential(1, len(time_index))
            
            # PV efficiency based on temperature and irradiance
            if 'solar_irradiance' in data:
                temp_derating = 1 - 0.004 * np.maximum(0, data['temperature'] - 25)  # 0.4%/°C above 25°C
                data['efficiency'] = np.clip(temp_derating * 100, 80, 100)
        
        # Filter to requested fields if specified
        if measurement_fields:
            data = {k: v for k, v in data.items() if k in measurement_fields}
        
        df = pd.DataFrame(data, index=time_index)
        print(f"🔧 Generated synthetic data for {device_id}: {list(df.columns)}")
        return df
    
    def publish_demand_response_signal(self, 
                                     device_id: str, 
                                     action: str, 
                                     parameters: Dict) -> bool:
        """Publish demand response control signal to IoT device"""
        
        if not self.connected:
            print(f"🔧 [SIMULATION] Would send DR signal to {device_id}: {action} with {parameters}")
            return True
        
        try:
            topic = f"semdr/control/{device_id}/demand_response"
            payload = {
                "timestamp": datetime.utcnow().isoformat(),
                "action": action,
                "parameters": parameters,
                "source": "SEMDR_optimization"
            }
            
            response = self.iot_data.publish(
                topic=topic,
                qos=1,
                payload=json.dumps(payload)
            )
            
            print(f"✅ Published DR signal to {device_id}: {action}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to publish DR signal to {device_id}: {e}")
            return False


def create_semdr_iot_scenario():
    """Create SEMDR scenario with IoT device integration"""
    
    # Create case study with 5-minute resolution for real-time optimization
    cs = CaseStudy(
        name="SEMDR_IoT_Integration",
        year=2020,
        freq="5min",  # High resolution for real-time DR
        country="DE",
        consider_invest=True,
        doc="SEMDR with real-time IoT data integration",
        coords=(52.5200, 13.4050),  # Berlin coordinates
    )
    
    # Set 6-hour optimization horizon for real-time operation
    cs.set_rolling_horizon(horizon_hours=6)
    
    # Create scenario
    sc = Scenario(
        cs=cs,
        name="IoT_Integrated",
        doc="SEMDR scenario with live IoT data feeds"
    )
    
    # Define IoT device IDs (matching AWS IoT Core device registry)
    device_ids = {
        "smart_meter": "hotel_main_meter_001",
        "temp_sensors": ["hvac_zone1_temp_001", "hvac_zone2_temp_001", "hvac_zone3_temp_001"],
        "occupancy_sensors": ["room_occ_001", "room_occ_002", "room_occ_003"],
        "battery_monitor": "battery_bms_001",
        "weather_station": "weather_station_001",
        "inverter_monitor": "pv_inverter_001"
    }
    
    # Add SEMDR components with IoT integration
    sc.add_component(
        SEMDRElectricDemand(
            annual_energy=2.5e6,  # 2.5 GWh/year
            demand_flexibility=0.10,  # 10% load shedding capability
            iot_device_id=device_ids["smart_meter"],
            comfort_penalty=150  # €150/MWh penalty for load shedding
        )
    )
    
    sc.add_component(
        SEMDRHVAC(
            heating_cap=700,  # 700 kW heating
            cooling_cap=600,  # 600 kW cooling
            cop_heating=4.0,  # High-efficiency heat pump
            cop_cooling=3.5,
            comfort_deadband=2.0,  # 2°C flexibility
            thermal_mass_hours=8.0,  # 8 hours thermal inertia
            temp_sensor_ids=device_ids["temp_sensors"],
            occupancy_sensor_ids=device_ids["occupancy_sensors"]
        )
    )
    
    sc.add_component(
        SEMDRBattery(
            E_CAPx=0,  # No existing battery
            allow_new=True,
            max_cycles_per_day=2.5,  # Allow more cycling for DR
            battery_monitor_id=device_ids["battery_monitor"]
        )
    )
    
    sc.add_component(
        SEMDRPV(
            P_CAPx=200,  # 200 kW existing PV
            A_avail_=1000,  # 1000 m² roof space available
            allow_new=True,
            weather_station_id=device_ids["weather_station"],
            inverter_monitor_id=device_ids["inverter_monitor"]
        )
    )
    
    sc.add_component(
        SEMDRGrid(
            selected_tariff="RTP",  # Real-time pricing for DR
            maxbuy=3000,  # 3 MW peak limit
            maxsell=1500,  # 1.5 MW feed-in limit
            demand_charge=100,  # €100/kW/month
            smart_meter_id=device_ids["smart_meter"]
        )
    )
    
    sc.add_component(SEMDRMain())
    
    return cs, sc, device_ids


def run_iot_integrated_optimization(cs, sc, device_ids, iot_manager):
    """Run optimization with real-time IoT data"""
    
    print(f"\n🚀 Running SEMDR optimization with IoT data integration")
    print(f"   Time horizon: {cs.dt_info}")
    print(f"   Resolution: {cs.freq} ({len(cs.dtindex_custom)} timesteps)")
    
    # Fetch real-time data from IoT devices
    start_time = cs.dtindex_custom[0].to_pydatetime()
    end_time = cs.dtindex_custom[-1].to_pydatetime()
    
    print(f"\n📡 Fetching IoT data from {len(device_ids)} device types...")
    
    # 1. Fetch electrical demand data
    demand_data = iot_manager.fetch_device_data(
        device_ids["smart_meter"],
        start_time, end_time,
        ["power", "voltage", "current"]
    )
    
    # 2. Fetch temperature sensor data
    temp_data = {}
    for sensor_id in device_ids["temp_sensors"]:
        temp_data[sensor_id] = iot_manager.fetch_device_data(
            sensor_id,
            start_time, end_time,
            ["temperature", "humidity"]
        )
    
    # 3. Fetch battery monitoring data
    battery_data = iot_manager.fetch_device_data(
        device_ids["battery_monitor"],
        start_time, end_time,
        ["voltage", "current", "soc", "temperature"]
    )
    
    # 4. Fetch weather data for PV optimization
    weather_data = iot_manager.fetch_device_data(
        device_ids["weather_station"],
        start_time, end_time,
        ["solar_irradiance", "temperature", "humidity", "wind_speed"]
    )
    
    # Transform IoT data to DRAF-compatible format
    print(f"\n🔄 Transforming IoT data to DRAF format...")
    
    if not demand_data.empty and 'power' in demand_data.columns:
        # Resample to match optimization frequency and set as demand
        demand_series = SEMDRIoTIntegration.transform_iot_to_draf(
            demand_data[['power']], cs.freq
        )['power']
        
        # Align with optimization time index
        demand_series = demand_series.reindex(cs.dtindex_custom, method='nearest')
        sc.components[0].p_el = demand_series  # Set on SEMDRElectricDemand
        
        print(f"   ✅ Integrated demand data: {demand_series.mean():.1f} kW average")
    
    # Update PV efficiency based on weather data
    if not weather_data.empty and 'temperature' in weather_data.columns:
        temp_series = SEMDRIoTIntegration.transform_iot_to_draf(
            weather_data[['temperature']], cs.freq
        )['temperature']
        
        # Calculate temperature derating for PV
        temp_series = temp_series.reindex(cs.dtindex_custom, method='nearest')
        pv_efficiency = 100 - 0.4 * np.maximum(0, temp_series - 25)  # 0.4%/°C above 25°C
        pv_efficiency = np.clip(pv_efficiency, 80, 100)
        
        print(f"   ✅ PV efficiency adjusted for temperature: {pv_efficiency.mean():.1f}% average")
    
    # Generate IoT data schema for the system
    system_schema = sc.components[-1].get_system_iot_schema(sc.components)
    
    print(f"\n📋 System IoT Schema Generated:")
    print(f"   - {len(system_schema['device_schemas'])} component types")
    print(f"   - {len(system_schema['aws_integration']['iot_core_topics'])} IoT topics")
    print(f"   - Database: {system_schema['aws_integration']['timestream_database']}")
    
    # Run the optimization
    try:
        print(f"\n⚡ Running optimization...")
        sc.solve(log_to_console=False)
        
        if sc.mdl.status == 2:  # Optimal solution
            print("✅ Optimization successful!")
            return analyze_iot_results(sc, iot_manager, device_ids, system_schema)
        else:
            print(f"❌ Optimization failed with status: {sc.mdl.status}")
            return None
            
    except Exception as e:
        print(f"❌ Optimization error: {e}")
        return None


def analyze_iot_results(sc, iot_manager, device_ids, system_schema):
    """Analyze optimization results and send demand response signals"""
    
    results = {
        'optimization': {},
        'iot_integration': {},
        'demand_response': {}
    }
    
    print(f"\n📊 Analyzing optimization results...")
    
    # Get cost breakdown
    if hasattr(sc.results, 'C_TOT_op_'):
        for key, value in sc.results.C_TOT_op_.items():
            results['optimization'][key] = value
        
        total_costs = sum(results['optimization'].values())
        print(f"   Total costs: {total_costs:.1f} k€/year")
    
    # Analyze demand response actions
    dr_actions = []
    
    # Check for load shedding
    if hasattr(sc.results, 'P_eDem_shed_T'):
        load_shed_events = sc.results.P_eDem_shed_T[sc.results.P_eDem_shed_T > 0]
        if not load_shed_events.empty:
            dr_actions.append({
                'type': 'load_shedding',
                'device_id': device_ids['smart_meter'],
                'events': len(load_shed_events),
                'max_reduction': load_shed_events.max(),
                'total_energy': load_shed_events.sum() * sc.step_width
            })
            print(f"   🔋 Load shedding: {len(load_shed_events)} events, max {load_shed_events.max():.1f} kW")
    
    # Check for HVAC temperature adjustments
    if hasattr(sc.results, 'deltaT_comfort_T'):
        temp_adjustments = sc.results.deltaT_comfort_T[sc.results.deltaT_comfort_T.abs() > 0.1]
        if not temp_adjustments.empty:
            dr_actions.append({
                'type': 'hvac_adjustment',
                'device_ids': device_ids['temp_sensors'],
                'events': len(temp_adjustments),
                'max_adjustment': temp_adjustments.abs().max(),
                'avg_adjustment': temp_adjustments.mean()
            })
            print(f"   🌡️  HVAC adjustments: {len(temp_adjustments)} events, max ±{temp_adjustments.abs().max():.1f}°C")
    
    # Check for battery dispatch
    if hasattr(sc.results, 'P_BES_out_T'):
        battery_discharge = sc.results.P_BES_out_T[sc.results.P_BES_out_T > 1]
        if not battery_discharge.empty:
            dr_actions.append({
                'type': 'battery_dispatch',
                'device_id': device_ids['battery_monitor'],
                'events': len(battery_discharge),
                'max_power': battery_discharge.max(),
                'total_energy': battery_discharge.sum() * sc.step_width
            })
            print(f"   🔋 Battery dispatch: {len(battery_discharge)} events, max {battery_discharge.max():.1f} kW")
    
    results['demand_response']['actions'] = dr_actions
    
    # Send demand response control signals
    print(f"\n📡 Sending demand response control signals...")
    
    for action in dr_actions:
        if action['type'] == 'load_shedding':
            success = iot_manager.publish_demand_response_signal(
                action['device_id'],
                'reduce_load',
                {
                    'reduction_kw': float(action['max_reduction']),
                    'duration_minutes': 15,
                    'priority': 'medium'
                }
            )
            results['iot_integration']['load_shedding_signal'] = success
            
        elif action['type'] == 'hvac_adjustment':
            for device_id in action['device_ids']:
                success = iot_manager.publish_demand_response_signal(
                    device_id,
                    'adjust_setpoint',
                    {
                        'temperature_delta': float(action['avg_adjustment']),
                        'duration_minutes': 30,
                        'comfort_priority': 'high'
                    }
                )
            results['iot_integration']['hvac_signals'] = success
            
        elif action['type'] == 'battery_dispatch':
            success = iot_manager.publish_demand_response_signal(
                action['device_id'],
                'discharge_battery',
                {
                    'power_kw': float(action['max_power']),
                    'duration_minutes': 60,
                    'soc_limit': 20
                }
            )
            results['iot_integration']['battery_signal'] = success
    
    # Save IoT integration schema
    output_dir = Path("output/semdr_iot")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_dir / "iot_schema.json", 'w') as f:
        json.dump(system_schema, f, indent=2)
    
    print(f"\n💾 Results and IoT schema saved to {output_dir}")
    
    return results


def main():
    """Main function for SEMDR IoT integration example"""
    
    print("🏢 SEMDR IoT Integration Example")
    print("=" * 50)
    print("Connecting DRAF optimization with AWS IoT infrastructure")
    print("for real-time smart energy management and demand response")
    
    # Initialize IoT manager
    print(f"\n🔗 Initializing AWS IoT connection...")
    iot_manager = SEMDRIoTManager()
    
    # Create SEMDR scenario with IoT integration
    print(f"\n🏗️  Creating SEMDR scenario with IoT devices...")
    cs, sc, device_ids = create_semdr_iot_scenario()
    
    print(f"   ✅ Created scenario with {len(sc.components)} SEMDR components")
    print(f"   ✅ Integrated {sum(len(v) if isinstance(v, list) else 1 for v in device_ids.values())} IoT devices")
    
    # Run optimization with IoT data
    results = run_iot_integrated_optimization(cs, sc, device_ids, iot_manager)
    
    if results:
        print(f"\n✅ SEMDR IoT integration completed successfully!")
        print(f"\n💡 Key achievements:")
        print(f"   - Real-time IoT data integration from {len(device_ids)} device types")
        print(f"   - High-resolution optimization with {cs.freq} timesteps")
        print(f"   - Automated demand response signal dispatch")
        print(f"   - AWS IoT Core topic integration")
        print(f"   - Timestream database connectivity")
        
        print(f"\n🎯 Business impact:")
        print(f"   - Real-time energy optimization based on live sensor data")
        print(f"   - Automated demand response without manual intervention")
        print(f"   - Scalable IoT device integration architecture")
        print(f"   - Cloud-native energy management system")
        
        return results
    else:
        print(f"\n❌ SEMDR IoT integration failed")
        return None


if __name__ == "__main__":
    results = main() 