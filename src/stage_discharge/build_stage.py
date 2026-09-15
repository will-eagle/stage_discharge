import numpy as np

CONSTANTS = {'G': 9.81, 'psi2pa':6895}

def rho(t, convert_to_c = False):
    """
    Calculates the density of pure water (kg/m^3) at 1 atm 
    using the UNESCO 1981 / Millero & Poisson polynomial equation.
    
    Valid range: 0°C to 30°C (standard oceanographic/limnological limits).
    """
    if convert_to_c:
        t=(t-32)*(5/9)

    # UNESCO 1981 Coefficients for pure water
    a0 = 999.842594
    a1 = 6.793952e-2
    a2 = -9.095290e-3
    a3 = 1.001685e-4
    a4 = -1.120083e-6
    a5 = 6.536332e-9
    
    rho = a0 + (a1 * t) + (a2 * t**2) + (a3 * t**3) + (a4 * t**4) + (a5 * t**5)
    return rho

def calc_diff_pressure(abs, baro):
    return abs - baro

def calc_depth(diff, temp):
    depth = diff/(rho(temp)*CONSTANTS['G'])
    return depth

def psi2pascals(psi):
    return psi*CONSTANTS['psi2pa']