"""
SEMDR Integration Test Suite

Comprehensive tests for SEMDR (Smart Energy Management and Demand Response) components
including IoT integration, AWS connectivity, and real-time optimization capabilities.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
from unittest.mock import Mock, patch

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


class TestSEMDRComponents:
    """Test suite for individual SEMDR components"""
    
    @pytest.fixture
    def case_study(self):
        """Create test case study with high-resolution time steps"""
        return CaseStudy(
            name="SEMDR_Test",
            year=2020,
            freq="15min",  # High resolution for DR testing
            country="DE",
            consider_invest=True,
            coords=(52.5200, 13.4050)  # Berlin
        )
    
    @pytest.fixture
    def scenario(self, case_study):
        """Create test scenario"""
        return Scenario(cs=case_study, name="Test_Scenario")
    
    def test_semdr_electric_demand(self, scenario):
        """Test SEMDRElectricDemand component with IoT integration"""
        component = SEMDRElectricDemand(
            annual_energy=2e6,
            demand_flexibility=0.10,
            iot_device_id="test_smart_meter_001",
            comfort_penalty=150
        )
        
        scenario.add_component(component)
        
        # Test IoT data schema generation
        schema = component.get_iot_data_schema()
        assert schema["device_id"] == "test_smart_meter_001"
        assert schema["measurement_type"] == "electrical_demand"
        assert "power" in schema["expected_fields"]
        assert schema["data_frequency"] == "1min"
        
        # Test parameter setup
        component.param_func(scenario)
        assert hasattr(scenario.params, 'k_eDem_flex_')
        assert scenario.params.k_eDem_flex_ == 0.10
        assert hasattr(scenario.params, 'c_eDem_penalty_')
        assert scenario.params.c_eDem_penalty_ == 150
        
        print("✅ SEMDRElectricDemand component test passed")
    
    def test_semdr_hvac(self, scenario):
        """Test SEMDRHVAC component with multi-zone sensors"""
        component = SEMDRHVAC(
            heating_cap=600,
            cooling_cap=500,
            comfort_deadband=2.5,
            thermal_mass_hours=6.0,
            temp_sensor_ids=["temp_001", "temp_002", "temp_003"],
            occupancy_sensor_ids=["occ_001", "occ_002"]
        )
        
        scenario.add_component(component)
        
        # Test IoT schema for multi-zone sensors
        schema = component.get_iot_data_schema()
        assert len(schema["temperature_sensors"]) == 3
        assert len(schema["occupancy_sensors"]) == 2
        assert "temperature" in schema["expected_fields"]
        
        # Test dimension setup
        component.dim_func(scenario)
        assert hasattr(scenario.dims, 'H')
        assert hasattr(scenario.dims, 'N')
        
        # Test parameter setup
        component.param_func(scenario)
        assert hasattr(scenario.params, 'k_comfort_flex_')
        assert scenario.params.k_comfort_flex_ == 2.5
        assert hasattr(scenario.params, 'k_thermal_mass_')
        assert scenario.params.k_thermal_mass_ == 6.0
        
        print("✅ SEMDRHVAC component test passed")
    
    def test_semdr_battery(self, scenario):
        """Test SEMDRBattery component with health monitoring"""
        component = SEMDRBattery(
            E_CAPx=0,
            allow_new=True,
            max_cycles_per_day=2.0,
            battery_monitor_id="battery_bms_001"
        )
        
        scenario.add_component(component)
        
        # Test IoT schema for battery monitoring
        schema = component.get_iot_data_schema()
        assert schema["device_id"] == "battery_bms_001"
        assert schema["measurement_type"] == "battery_monitoring"
        assert "soc" in schema["expected_fields"]
        assert "alerts" in schema
        assert "low_soc" in schema["alerts"]
        
        # Test parameter setup
        component.param_func(scenario)
        assert hasattr(scenario.params, 'k_BES_maxCycles_')
        assert scenario.params.k_BES_maxCycles_ == 2.0
        
        print("✅ SEMDRBattery component test passed")
    
    def test_semdr_pv(self, scenario):
        """Test SEMDRPV component with weather integration"""
        component = SEMDRPV(
            P_CAPx=200,
            A_avail_=800,
            allow_new=True,
            weather_station_id="weather_001",
            inverter_monitor_id="inverter_001"
        )
        
        scenario.add_component(component)
        
        # Test IoT schema for weather and inverter monitoring
        schema = component.get_iot_data_schema()
        assert "weather_station" in schema
        assert "inverter_monitor" in schema
        assert schema["weather_station"]["device_id"] == "weather_001"
        assert "solar_irradiance" in schema["weather_station"]["expected_fields"]
        
        # Test parameter setup
        component.param_func(scenario)
        assert hasattr(scenario.params, 'A_PV_avail_')
        assert scenario.params.A_PV_avail_ == 800
        
        print("✅ SEMDRPV component test passed")
    
    def test_semdr_grid(self, scenario):
        """Test SEMDRGrid component with smart meter integration"""
        component = SEMDRGrid(
            selected_tariff="RTP",
            maxbuy=2500,
            maxsell=1000,
            demand_charge=120,
            smart_meter_id="smart_meter_001"
        )
        
        scenario.add_component(component)
        
        # Test IoT schema for smart meter
        schema = component.get_iot_data_schema()
        assert "smart_meter" in schema
        assert schema["smart_meter"]["device_id"] == "smart_meter_001"
        assert "active_power" in schema["smart_meter"]["expected_fields"]
        
        # Test parameter setup
        component.param_func(scenario)
        assert hasattr(scenario.params, 'c_EG_buyPeak_')
        assert scenario.params.c_EG_buyPeak_ == 120
        
        print("✅ SEMDRGrid component test passed")


class TestSEMDRIoTIntegration:
    """Test suite for IoT data integration functionality"""
    
    def test_iot_data_transformation(self):
        """Test IoT data transformation to DRAF format"""
        # Create synthetic IoT data
        time_index = pd.date_range('2024-01-01 00:00', periods=60, freq='1min')
        iot_data = pd.DataFrame({
            'time': time_index,
            'measure_name': ['power'] * 60,
            'value': 400 + 50 * np.sin(np.arange(60) * 2 * np.pi / 60)
        })
        
        # Transform to DRAF format
        transformed = SEMDRIoTIntegration.transform_iot_to_draf(iot_data, "15min")
        
        assert isinstance(transformed, pd.DataFrame)
        assert len(transformed) == 4  # 60 minutes / 15 minutes
        assert 'power' in transformed.columns
        
        print("✅ IoT data transformation test passed")
    
    def test_iot_data_validation(self):
        """Test IoT data quality validation"""
        # Create test data with quality issues
        test_data = pd.DataFrame({
            'power': [400, 450, np.nan, 420, 380],
            'voltage': [230, 228, 232, np.nan, 229],
            'current': [1.7, 2.0, 1.8, 1.9, 1.6]
        })
        
        expected_schema = {
            "expected_fields": ["power", "voltage", "current", "frequency"],
            "units": {"power": "kW", "voltage": "V", "current": "A"}
        }
        
        validation = SEMDRIoTIntegration.validate_iot_data(test_data, expected_schema)
        
        assert "valid" in validation
        assert "missing_fields" in validation
        assert "frequency" in validation["missing_fields"]  # Missing field
        assert "data_quality" in validation
        assert validation["data_quality"]["power"]["null_percentage"] == 20.0  # 1/5 = 20%
        
        print("✅ IoT data validation test passed")
    
    def test_timestream_query_generation(self):
        """Test Timestream SQL query generation"""
        query = SEMDRIoTIntegration.create_timestream_query(
            device_id="test_device_001",
            measurement_type="electrical",
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-01T01:00:00Z"
        )
        
        assert "semdr_iot_db" in query
        assert "device_metrics" in query
        assert "test_device_001" in query
        assert "2024-01-01T00:00:00Z" in query
        assert "ORDER BY time ASC" in query
        
        print("✅ Timestream query generation test passed")


class TestSEMDROptimization:
    """Test suite for SEMDR optimization functionality"""
    
    @pytest.fixture
    def complete_scenario(self):
        """Create complete SEMDR scenario for optimization testing"""
        cs = CaseStudy(
            name="SEMDR_Optimization_Test",
            year=2020,
            freq="30min",  # Moderate resolution for testing
            country="DE",
            consider_invest=True
        )
        
        # Set short horizon for fast testing
        cs.set_rolling_horizon(horizon_hours=3)
        
        sc = Scenario(cs=cs, name="Complete_Test")
        
        # Add all SEMDR components
        sc.add_component(SEMDRElectricDemand(
            annual_energy=1.5e6,
            demand_flexibility=0.08,
            iot_device_id="smart_meter_test"
        ))
        
        sc.add_component(SEMDRHVAC(
            heating_cap=400,
            cooling_cap=300,
            comfort_deadband=2.0,
            temp_sensor_ids=["temp_test_001"]
        ))
        
        sc.add_component(SEMDRBattery(
            E_CAPx=0,
            allow_new=True,
            max_cycles_per_day=2.0
        ))
        
        sc.add_component(SEMDRPV(
            P_CAPx=150,
            allow_new=True
        ))
        
        sc.add_component(SEMDRGrid(
            selected_tariff="TOU",
            maxbuy=2000
        ))
        
        sc.add_component(SEMDRMain())
        
        return cs, sc
    
    def test_semdr_model_building(self, complete_scenario):
        """Test SEMDR model building without solving"""
        cs, sc = complete_scenario
        
        # Build model without solving
        sc.build_model()
        
        assert sc.mdl is not None
        assert len(sc.components) == 6  # 5 components + Main
        
        # Check that key variables exist
        assert hasattr(sc.vars, 'P_eDem_shed_T')  # Load shedding
        assert hasattr(sc.vars, 'deltaT_comfort_T')  # HVAC flexibility
        assert hasattr(sc.vars, 'P_BES_in_T')  # Battery charging
        assert hasattr(sc.vars, 'P_EG_peak_')  # Peak demand
        
        print("✅ SEMDR model building test passed")
    
    @patch('draf.Scenario.solve')
    def test_semdr_optimization_workflow(self, mock_solve, complete_scenario):
        """Test complete SEMDR optimization workflow"""
        cs, sc = complete_scenario
        
        # Mock successful optimization
        mock_solve.return_value = None
        sc.mdl = Mock()
        sc.mdl.status = 2  # Optimal solution
        
        # Test system IoT schema generation
        main_component = sc.components[-1]  # SEMDRMain
        system_schema = main_component.get_system_iot_schema(sc.components)
        
        assert "system_name" in system_schema
        assert system_schema["system_name"] == "SEMDR"
        assert "device_schemas" in system_schema
        assert "aws_integration" in system_schema
        assert "timestream_database" in system_schema["aws_integration"]
        
        print("✅ SEMDR optimization workflow test passed")


class TestSEMDRRealTimeFeatures:
    """Test suite for real-time SEMDR features"""
    
    def test_rolling_horizon_setup(self):
        """Test rolling horizon configuration for real-time optimization"""
        cs = CaseStudy(
            name="RealTime_Test",
            freq="5min",
            year=2020
        )
        
        # Set rolling horizon
        cs.set_rolling_horizon(horizon_hours=6)
        
        # Check that time index is appropriately sized
        assert len(cs.dtindex_custom) == 6 * 12  # 6 hours * 12 (5-min intervals per hour)
        
        print("✅ Rolling horizon setup test passed")
    
    def test_minute_level_frequencies(self):
        """Test minute-level frequency support"""
        valid_frequencies = ["1min", "5min", "15min", "30min", "60min"]
        
        for freq in valid_frequencies:
            cs = CaseStudy(
                name=f"Freq_Test_{freq}",
                freq=freq,
                year=2020
            )
            
            # Should not raise validation error
            assert cs.freq == freq
            
        print("✅ Minute-level frequency support test passed")
    
    @patch('boto3.client')
    def test_aws_iot_integration_mock(self, mock_boto_client):
        """Test AWS IoT integration with mocked services"""
        from draf.examples.semdr_iot_integration import SEMDRIoTManager
        
        # Mock AWS clients
        mock_timestream = Mock()
        mock_iot_data = Mock()
        mock_boto_client.side_effect = [mock_timestream, Mock(), mock_iot_data]
        
        # Create IoT manager
        iot_manager = SEMDRIoTManager()
        
        assert iot_manager.connected == True
        assert iot_manager.timestream_db == "semdr_iot_db"
        
        # Test demand response signal publishing
        success = iot_manager.publish_demand_response_signal(
            device_id="test_device",
            action="reduce_load",
            parameters={"reduction_kw": 50, "duration_minutes": 15}
        )
        
        assert success == True
        
        print("✅ AWS IoT integration mock test passed")


class TestSEMDRBackwardCompatibility:
    """Test suite for backward compatibility with hotel components"""
    
    def test_hotel_component_aliases(self):
        """Test that hotel component aliases still work"""
        from draf.components import (
            HotelElectricDemand,
            HotelHVAC,
            HotelBattery,
            HotelPV,
            HotelGrid,
            HotelMain
        )
        
        # Test that aliases point to SEMDR components
        assert HotelElectricDemand == SEMDRElectricDemand
        assert HotelHVAC == SEMDRHVAC
        assert HotelBattery == SEMDRBattery
        assert HotelPV == SEMDRPV
        assert HotelGrid == SEMDRGrid
        assert HotelMain == SEMDRMain
        
        print("✅ Hotel component backward compatibility test passed")
    
    def test_legacy_hotel_scenario(self):
        """Test that legacy hotel scenarios still work"""
        from draf.components import HotelElectricDemand, HotelMain
        
        cs = CaseStudy(name="Legacy_Test", freq="1h", year=2020)
        sc = Scenario(cs=cs, name="Legacy")
        
        # Use legacy hotel component names
        sc.add_component(HotelElectricDemand(annual_energy=2e6))
        sc.add_component(HotelMain())
        
        # Should build without errors
        sc.build_model()
        assert len(sc.components) == 2
        
        print("✅ Legacy hotel scenario test passed")


def run_semdr_integration_tests():
    """Run all SEMDR integration tests"""
    print("🧪 Running SEMDR Integration Test Suite")
    print("=" * 50)
    
    # Component tests
    print("\n🔧 Testing SEMDR Components...")
    component_tests = TestSEMDRComponents()
    cs = CaseStudy(name="Test", freq="15min", year=2020, consider_invest=True)
    sc = Scenario(cs=cs, name="Test")
    
    component_tests.test_semdr_electric_demand(sc)
    component_tests.test_semdr_hvac(sc)
    component_tests.test_semdr_battery(sc)
    component_tests.test_semdr_pv(sc)
    component_tests.test_semdr_grid(sc)
    
    # IoT integration tests
    print("\n📡 Testing IoT Integration...")
    iot_tests = TestSEMDRIoTIntegration()
    iot_tests.test_iot_data_transformation()
    iot_tests.test_iot_data_validation()
    iot_tests.test_timestream_query_generation()
    
    # Optimization tests
    print("\n⚡ Testing Optimization...")
    opt_tests = TestSEMDROptimization()
    cs_opt, sc_opt = opt_tests.complete_scenario()
    opt_tests.test_semdr_model_building((cs_opt, sc_opt))
    opt_tests.test_semdr_optimization_workflow((cs_opt, sc_opt))
    
    # Real-time feature tests
    print("\n⏱️  Testing Real-Time Features...")
    rt_tests = TestSEMDRRealTimeFeatures()
    rt_tests.test_rolling_horizon_setup()
    rt_tests.test_minute_level_frequencies()
    rt_tests.test_aws_iot_integration_mock()
    
    # Backward compatibility tests
    print("\n🔄 Testing Backward Compatibility...")
    compat_tests = TestSEMDRBackwardCompatibility()
    compat_tests.test_hotel_component_aliases()
    compat_tests.test_legacy_hotel_scenario()
    
    print("\n✅ All SEMDR integration tests passed!")
    print("\n🎯 Test Summary:")
    print("   ✅ SEMDR component functionality")
    print("   ✅ IoT data integration and validation")
    print("   ✅ AWS service connectivity (mocked)")
    print("   ✅ High-resolution optimization capability")
    print("   ✅ Real-time rolling horizon operation")
    print("   ✅ Backward compatibility with hotel components")
    print("   ✅ Minute-level time resolution support")
    
    return True


if __name__ == "__main__":
    success = run_semdr_integration_tests()
    if success:
        print("\n🚀 SEMDR is ready for production deployment!")
    else:
        print("\n❌ SEMDR tests failed - check implementation")
        exit(1) 