# SEMDR: Smart Energy Management and Demand Response

SEMDR (Smart Energy Management and Demand Response) is an advanced energy optimization framework built on DRAF, specifically designed for real-time IoT-integrated demand response systems in commercial buildings, hotels, and industrial facilities.

## Overview

SEMDR combines the mathematical optimization power of DRAF with real-time IoT data streams to enable automated, intelligent energy management and demand response. The system integrates seamlessly with AWS IoT infrastructure to provide cloud-native energy optimization.

### Key Features

- **Real-time IoT Integration**: Direct integration with AWS IoT Core, Timestream, and Lambda
- **High-Resolution Optimization**: 1-minute to 60-minute time resolution for responsive control
- **Automated Demand Response**: Intelligent load shedding, HVAC flexibility, and battery dispatch
- **Cloud-Native Architecture**: Built for AWS with scalable, serverless components
- **Multi-Device Support**: Smart meters, temperature sensors, battery monitors, weather stations
- **Advanced Analytics**: Real-time data validation, quality checks, and performance monitoring

## Architecture

### SEMDR System Components

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   IoT Devices   │───▶│   AWS IoT Core   │───▶│   SEMDR DRAF    │
│                 │    │                  │    │   Optimization  │
│ • Smart Meters  │    │ • Device Shadow  │    │                 │
│ • Temp Sensors  │    │ • Rules Engine   │    │ • Energy Model  │
│ • Occupancy     │    │ • Message Router │    │ • DR Algorithm  │
│ • Battery BMS   │    │                  │    │ • Cost Optimizer│
│ • Weather       │    └──────────────────┘    └─────────────────┘
│ • PV Inverters  │             │                        │
└─────────────────┘             ▼                        ▼
                    ┌──────────────────┐    ┌─────────────────┐
                    │   AWS Services   │    │   Control       │
                    │                  │    │   Signals       │
                    │ • Timestream DB  │    │                 │
                    │ • Lambda Proc.   │◀───│ • Load Shedding │
                    │ • S3 Storage     │    │ • HVAC Adjust   │
                    │ • RDS Database   │    │ • Battery Ctrl  │
                    └──────────────────┘    └─────────────────┘
```

### AWS IoT Infrastructure Integration

SEMDR leverages the existing AWS IoT infrastructure:

- **AWS IoT Core**: Device connectivity and message routing
- **AWS Timestream**: Time-series data storage for sensor readings
- **AWS Lambda**: Real-time data processing and SEMDR triggering
- **Amazon RDS**: Configuration and results storage
- **Amazon S3**: Raw data backup and historical storage

## Quick Start

### 1. Installation

```bash
# Install DRAF with SEMDR components
pip install -r requirements.txt

# Configure AWS credentials
aws configure
```

### 2. Basic SEMDR Example

```python
from draf import CaseStudy, Scenario
from draf.components.semdr_components import (
    SEMDRElectricDemand,
    SEMDRHVAC,
    SEMDRBattery,
    SEMDRPV,
    SEMDRGrid,
    SEMDRMain
)

# Create case study with high-resolution optimization
cs = CaseStudy(
    name="SEMDR_Hotel",
    freq="5min",  # 5-minute resolution
    consider_invest=True
)

# Set rolling horizon for real-time optimization
cs.set_rolling_horizon(horizon_hours=6)

# Create scenario
sc = Scenario(cs=cs, name="RealTime_DR")

# Add SEMDR components with IoT device IDs
sc.add_component(SEMDRElectricDemand(
    annual_energy=2e6,
    demand_flexibility=0.08,
    iot_device_id="smart_meter_001"
))

sc.add_component(SEMDRHVAC(
    heating_cap=600,
    cooling_cap=500,
    comfort_deadband=2.0,
    temp_sensor_ids=["temp_001", "temp_002", "temp_003"]
))

sc.add_component(SEMDRBattery(
    allow_new=True,
    battery_monitor_id="battery_bms_001"
))

sc.add_component(SEMDRPV(
    P_CAPx=200,
    weather_station_id="weather_001"
))

sc.add_component(SEMDRGrid(
    selected_tariff="RTP",
    smart_meter_id="smart_meter_001"
))

sc.add_component(SEMDRMain())

# Solve optimization
sc.solve()
```

### 3. IoT Data Integration

```python
from draf.components.semdr_components import SEMDRIoTIntegration

# Initialize IoT manager
iot_manager = SEMDRIoTManager(
    aws_region="us-east-1",
    timestream_db="semdr_iot_db"
)

# Fetch real-time device data
demand_data = iot_manager.fetch_device_data(
    device_id="smart_meter_001",
    start_time=datetime.now() - timedelta(hours=6),
    end_time=datetime.now(),
    measurement_fields=["power", "voltage", "current"]
)

# Transform to DRAF format
demand_series = SEMDRIoTIntegration.transform_iot_to_draf(
    demand_data, target_frequency="5min"
)

# Set as demand input
sc.components[0].p_el = demand_series['power']
```

## SEMDR Components

### SEMDRElectricDemand
- Real-time smart meter integration
- Configurable load shedding (5-15% flexibility)
- Guest comfort penalty modeling
- IoT device schema generation

### SEMDRHVAC
- Multi-zone temperature control
- Thermal mass modeling for load shifting
- Occupancy-based demand adjustment
- Comfort constraint optimization

### SEMDRBattery
- Battery health protection (cycle limits)
- State-of-charge monitoring
- Peak shaving and load shifting
- IoT-based battery management system integration

### SEMDRPV
- Weather-corrected generation forecasting
- Real-time efficiency monitoring
- Inverter performance tracking
- Self-consumption vs feed-in optimization

### SEMDRGrid
- Real-time pricing integration
- Demand charge optimization
- Grid quality monitoring
- Smart meter data processing

### SEMDRMain
- Cost-optimized objective function
- Energy balance constraints
- IoT schema coordination
- Demand response signal generation

## IoT Device Integration

### Supported Device Types

| Device Type | Measurements | Frequency | Purpose |
|-------------|-------------|-----------|---------|
| Smart Meter | power, voltage, current, frequency | 1min | Demand monitoring & control |
| Temperature Sensors | temperature, humidity, pressure | 1min | HVAC optimization |
| Occupancy Sensors | is_occupied, occupancy_count | 1min | Demand adjustment |
| Battery BMS | voltage, current, soc, temperature | 1min | Battery management |
| Weather Station | solar_irradiance, temperature, humidity, wind_speed | 1min | PV forecasting |
| PV Inverter | ac_power, dc_power, efficiency | 1min | Generation monitoring |

### AWS IoT Topic Structure

```
devices/{device_id}/{measurement_type}/measurement
semdr/control/{device_id}/demand_response
```

### Data Schema Example

```json
{
  "device_id": "smart_meter_001",
  "timestamp": "2024-12-19T10:30:00Z",
  "measurements": {
    "power": 450.2,
    "voltage": 230.1,
    "current": 1.96,
    "frequency": 50.02
  },
  "data_format": "semdr_v1",
  "location": "main_electrical_room",
  "building_id": "hotel_main"
}
```

## Demand Response Capabilities

### Load Shedding
- **Capability**: 5-15% of total demand
- **Duration**: 15 minutes to 4 hours
- **Trigger**: High electricity prices or grid signals
- **Penalty**: €100-200/MWh for guest comfort impact

### HVAC Flexibility
- **Temperature Range**: ±2-3°C from setpoint
- **Thermal Mass**: 4-8 hours of thermal inertia
- **Zones**: Multi-zone independent control
- **Comfort Priority**: Guest areas prioritized

### Battery Dispatch
- **Cycling**: 1.5-2.5 cycles per day maximum
- **Peak Shaving**: Automatic during high-demand periods
- **Grid Services**: Frequency regulation capability
- **Health Monitoring**: Real-time SOC and temperature tracking

## Real-Time Operation

### Rolling Horizon Optimization

```python
# Set 6-hour rolling optimization window
cs.set_rolling_horizon(horizon_hours=6)

# Optimization runs every 15 minutes with:
# - Previous 1 hour: actual data
# - Next 5 hours: forecasted data
```

### Automated Control Loop

1. **Data Collection** (every minute)
   - Fetch IoT sensor readings
   - Validate data quality
   - Update forecasts

2. **Optimization** (every 15 minutes)
   - Run SEMDR optimization
   - Generate control signals
   - Update device setpoints

3. **Control Dispatch** (real-time)
   - Send commands to IoT devices
   - Monitor execution
   - Log performance

## Performance & Scalability

### Optimization Performance
- **5-minute resolution**: <30 seconds solve time
- **15-minute resolution**: <10 seconds solve time
- **Memory usage**: <2GB for 24-hour horizon
- **Scalability**: Up to 100 IoT devices per instance

### AWS Infrastructure Scaling
- **IoT Core**: 1M+ concurrent device connections
- **Timestream**: 1TB+ time-series data per day
- **Lambda**: Auto-scaling based on message volume
- **RDS**: Multi-AZ deployment for high availability

## Deployment

### AWS Infrastructure Setup

```bash
# Deploy using CDK
cd iot_infrastructure
cdk deploy -c env=prod

# Or using Terraform
cd terraform_semdr
terraform workspace select prod
terraform apply -var-file="prod.tfvars"
```

### SEMDR Application Deployment

```bash
# Install SEMDR
pip install draf[semdr]

# Configure environment
export AWS_REGION=us-east-1
export TIMESTREAM_DB=semdr_iot_db
export SEMDR_CONFIG_PATH=/etc/semdr/config.yaml

# Run SEMDR service
python -m semdr.service --config production
```

### Docker Deployment

```dockerfile
FROM python:3.11-slim

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY draf/ /app/draf/
WORKDIR /app

CMD ["python", "-m", "semdr.service"]
```

## Monitoring & Alerting

### Key Performance Indicators (KPIs)

- **Energy Cost Reduction**: 15-25% vs baseline
- **Peak Demand Reduction**: 10-30% during DR events
- **Guest Comfort Maintenance**: <5% comfort complaints
- **System Availability**: >99.5% uptime
- **IoT Data Quality**: >95% valid readings

### Alerting Conditions

- IoT device offline >5 minutes
- Data quality <90% for >15 minutes
- Optimization failure >2 consecutive runs
- Demand response event non-compliance
- Battery temperature >45°C

## Integration Examples

### Complete IoT Integration Example

```bash
# Run the comprehensive SEMDR IoT example
cd draf
python examples/semdr_iot_integration.py
```

This example demonstrates:
- AWS IoT service connectivity
- Real-time data fetching from Timestream
- Multi-device sensor integration
- Automated demand response signal dispatch
- Performance monitoring and alerting

### Legacy Hotel System Integration

```python
# Backward compatibility with existing hotel components
from draf.components import HotelElectricDemand  # Maps to SEMDRElectricDemand

# Existing hotel code continues to work
sc.add_component(HotelElectricDemand(annual_energy=2e6))
```

## Contributing

SEMDR is built on the DRAF framework and follows the same contribution guidelines:

1. Fork the repository
2. Create feature branch (`git checkout -b feature/semdr-enhancement`)
3. Add tests for new IoT integrations
4. Submit pull request with AWS infrastructure updates

## Support

- **Documentation**: [SEMDR Wiki](link-to-wiki)
- **Issues**: [GitHub Issues](link-to-issues)
- **Discussions**: [GitHub Discussions](link-to-discussions)
- **Email**: semdr-support@neura-energy.com

## License

SEMDR is released under the same license as DRAF. See LICENSE file for details.

---

**SEMDR** - Transforming energy management through intelligent IoT integration and real-time optimization. 