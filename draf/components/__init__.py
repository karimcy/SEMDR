from .component_templates import *
from .user_defined_components import *
from .semdr_components import *

# SEMDR-specific convenience imports
from .semdr_components import (
    SEMDRElectricDemand,
    SEMDRHVAC, 
    SEMDRBattery,
    SEMDRPV,
    SEMDRGrid,
    SEMDRMain,
    SEMDRIoTIntegration
)

# Industrial components (keep for backward compatibility)
from .component_templates import (
    Main, cDem, hDem, eDem, EG, BES, PV, WT, HP, P2H, TES, HD,
    # Keep only essential industrial components, comment out complex ones
    # CHP, HOB, Fuel, DAC, Elc, H2S, FC, pDem, PP, PS, BEV
)

# Legacy hotel imports for backward compatibility
HotelElectricDemand = SEMDRElectricDemand
HotelHVAC = SEMDRHVAC
HotelBattery = SEMDRBattery
HotelPV = SEMDRPV
HotelGrid = SEMDRGrid
HotelMain = SEMDRMain
