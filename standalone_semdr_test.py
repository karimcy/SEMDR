#!/usr/bin/env python3
"""
Standalone SEMDR Component Test

Test SEMDR components directly without full DRAF framework dependencies.
"""

import sys
import os
import pandas as pd
import numpy as np

# Import directly from standalone components
from standalone_semdr_components import (
    SEMDRElectricDemand,
    SEMDRHVAC,
    SEMDRBattery,
    SEMDRPV,
    SEMDRGrid,
    SEMDRMain,
    SEMDRIoTIntegration
)

def test_semdr_components_standalone():
    """Test SEMDR components by importing directly from the file"""
    print("🔧 Testing SEMDR components standalone...")
    
    try:
        # Test component creation
        demand = SEMDRElectricDemand(
            annual_energy=2e6,
            demand_flexibility=0.10,
            iot_device_id="test_meter_001"
        )
        
        hvac = SEMDRHVAC(
            heating_cap=500,
            cooling_cap=400,
            temp_sensor_ids=["temp_001", "temp_002"]
        )
        
        battery = SEMDRBattery(
            E_CAPx=0,
            allow_new=True,
            battery_monitor_id="battery_001"
        )
        
        pv = SEMDRPV(
            P_CAPx=200,
            weather_station_id="weather_001"
        )
        
        grid = SEMDRGrid(
            selected_tariff="TOU",
            smart_meter_id="meter_001"
        )
        
        main = SEMDRMain()
        
        print("   ✅ All SEMDR components created successfully")
        
        # Test IoT schema generation
        demand_schema = demand.get_iot_data_schema()
        assert demand_schema["device_id"] == "test_meter_001"
        assert "power" in demand_schema["expected_fields"]
        
        hvac_schema = hvac.get_iot_data_schema()
        assert len(hvac_schema["temperature_sensors"]) == 2
        
        battery_schema = battery.get_iot_data_schema()
        assert battery_schema["device_id"] == "battery_001"
        assert "soc" in battery_schema["expected_fields"]
        
        print("   ✅ IoT schema generation working")
        
        # Test system schema generation
        components = [demand, hvac, battery, pv, grid]
        system_schema = main.get_system_iot_schema(components)
        
        assert "system_name" in system_schema
        assert system_schema["system_name"] == "SEMDR"
        assert "device_schemas" in system_schema
        
        print("   ✅ System schema generation working")
        print(f"   📊 System includes {len(system_schema['device_schemas'])} component schemas")
        
        return True
        
    except Exception as e:
        print(f"   ❌ SEMDR standalone test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_iot_integration_helpers():
    """Test IoT integration helper functions"""
    print("📡 Testing IoT integration helpers...")
    
    try:
        # Test data transformation
        test_data = pd.DataFrame({
            'time': pd.date_range('2024-01-01', periods=60, freq='1min'),
            'measure_name': ['power'] * 60,
            'value': 400 + 50 * np.sin(np.arange(60) * 2 * np.pi / 60)
        })
        
        transformed = SEMDRIoTIntegration.transform_iot_to_draf(test_data, "15min")
        assert isinstance(transformed, pd.DataFrame)
        assert len(transformed) == 4  # 60 minutes / 15 minutes
        
        # Test query generation
        query = SEMDRIoTIntegration.create_timestream_query(
            "test_device", "electrical", "2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z"
        )
        assert "semdr_iot_db" in query
        assert "test_device" in query
        
        # Test data validation
        validation = SEMDRIoTIntegration.validate_iot_data(
            pd.DataFrame({'power': [400, 450, 420], 'voltage': [230, 228, 232]}),
            {"expected_fields": ["power", "voltage"]}
        )
        assert "valid" in validation
        assert validation["valid"] == True
        
        print("   ✅ IoT integration helpers working")
        return True
        
    except Exception as e:
        print(f"   ❌ IoT integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_demand_response_logic():
    """Test demand response logic"""
    print("⚡ Testing demand response logic...")
    
    try:
        # Create components with demand response capabilities
        demand = SEMDRElectricDemand(
            annual_energy=2e6,
            demand_flexibility=0.15,
            iot_device_id="meter_001"
        )
        
        hvac = SEMDRHVAC(
            heating_cap=500,
            cooling_cap=400,
            temp_sensor_ids=["temp_001", "temp_002"],
            hvac_control_id="hvac_ctrl_001"
        )
        
        battery = SEMDRBattery(
            E_CAPx=100,  # 100 kWh battery
            allow_new=False,
            battery_monitor_id="battery_001"
        )
        
        # Test demand response signal generation
        dr_signal = demand.generate_demand_response_signal(
            current_load=450,  # kW
            target_reduction=0.10,  # 10% reduction
            duration_minutes=60
        )
        
        assert "signal_type" in dr_signal
        assert dr_signal["signal_type"] == "load_reduction"
        assert dr_signal["target_reduction_kw"] == 45  # 10% of 450 kW
        
        # Test HVAC flexibility calculation
        hvac_flexibility = hvac.calculate_hvac_flexibility(
            current_temp=22.0,
            setpoint=21.0,
            outdoor_temp=30.0
        )
        
        assert "flexibility_kw" in hvac_flexibility
        assert hvac_flexibility["flexibility_kw"] > 0
        
        # Test battery dispatch optimization
        battery_dispatch = battery.optimize_battery_dispatch(
            current_soc=0.6,
            grid_price=0.15,  # $/kWh
            forecast_prices=[0.12, 0.18, 0.20, 0.16]
        )
        
        assert "action" in battery_dispatch
        assert battery_dispatch["action"] in ["charge", "discharge", "hold"]
        
        print("   ✅ Demand response logic working")
        return True
        
    except Exception as e:
        print(f"   ❌ Demand response test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run standalone SEMDR tests"""
    print("🧪 Standalone SEMDR Component Test")
    print("=" * 50)
    
    tests = [
        test_semdr_components_standalone,
        test_iot_integration_helpers,
        test_demand_response_logic
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 SEMDR components are working correctly!")
        print("\n💡 Key features validated:")
        print("   ✅ Component creation and configuration")
        print("   ✅ IoT device schema generation")
        print("   ✅ Data transformation utilities")
        print("   ✅ Demand response logic")
        print("   ✅ System integration capabilities")
        
        print("\n🚀 SEMDR is ready for deployment!")
        print("   📋 Next steps:")
        print("   1. Deploy AWS IoT infrastructure")
        print("   2. Configure device connections")
        print("   3. Set up real-time data streams")
        print("   4. Initialize demand response automation")
    else:
        print("❌ Some SEMDR component tests failed")
        print("   🔧 Review the error messages above for troubleshooting")

if __name__ == "__main__":
    main() 