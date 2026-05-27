# -*- coding: utf-8 -*-

from numba import njit

import numpy as np
import Utils.climateProcess as cp
# import climateProcess as cp
import numba
import math

Lh_vap =  2426  # J.g-1  Heat of vaporization of sweat at 30deg C
density = 1      # density for sweat conversion factor



class rider:
    def __init__(self, Location, person_condition, flag = 'exposure'):
        # =============================================================================
        # Rider parameter initialization
        # =============================================================================
        
        '''
        Mass: Body mass (kg)
        Height: Body height (m)
        AD: Du Bois body surface area (m2)
        Tsk_C: Mean skin temperature (deg C)
        A_eff: Effective body radiative area (dimensionless)
        Emm_sk: Clothing-weighted emissivity (dimensionless)
        Icl: Clothing insulation value (Iclo)
        Re_cl: Clothing evaporative resistance (m2.kPa/W)
        METS: Metabolic heat production (W/kg)
        Work: External mechanical work (W/g) (set 0 in this application)
        wmax_condition: Max skin wettedness for HEAT-Lim (dimensionless)
        smax_rate: Max sustained sweating rate (L/hr)
        '''
        self.Mass = 69.8
        self.Height = 1.7
        # self.Tsk_C = 35
        self.A_eff = 0.73
        self.Work = 0
        self.smax_rate = 0.75
        self.AD = self.AD_from_mass_height()  # Compute body surface area from mass and height
        self.Emm_sk = 0.95                    # Default emissivity for skin and clothing        
        self.w_max = self.wmax(person_condition)  # Max skin wettedness

        self.METS = 2.8                  # Zhang(2024) Urban food delivery services as extreme heat adaptation



    def cal_Tsk_C(self, Ta_C: float, MRT_C: float, RH: float) -> float:
        '''
        Calculate mean skin temperature based on metabolic rate.
        Returns
        -------
        Tsk_C : float
            Mean skin temperature (deg C).
        '''
        M = self.met_to_watts(Ta_C)
        Psa_kPa = cp.Psa_kPa_from_TaC(Ta_C)
        Pv_kPa = cp.Pv_kPa_from_Psa_RH(Psa_kPa, RH)
        Tsk_C = 12.17 + 0.194 * Pv_kPa + 0.020*Ta_C + 0.044 * MRT_C + 0.005346 * M + 0.513 * 36.8 - 0.253 * 7
        return Tsk_C
    
    def cal_Icl(self, Ta_C: float) -> float:
        if Ta_C <= -20:
            Icl = 2.35
        elif Ta_C <= -10:
            Icl = 2.2
        elif Ta_C <= 0:
            Icl = 2.0
        elif Ta_C <= 10:
            Icl = 1.5
        elif Ta_C <= 20:
            Icl = 0.8
        elif Ta_C <= 30:
            Icl = 0.5
        else:
            Icl = 0.36
        return Icl        
    
    def cal_Re_cl(self, Ta_C: float) -> float:
        '''
        Calculate clothing evaporative resistance from Icl.
        Parameters
        ----------
        Icl : float
            Clothing insulation value (Iclo).
        Returns
        -------
        Re_cl : float
            Clothing evaporative resistance (m2.kPa/W).
        '''
        Icl = self.cal_Icl(Ta_C)
        Icl_m2K_W = Icl * 0.155
        im = 0.30                            # Clothing permeability index (dimensionless)
        L = 16.5                             
        Re_cl = Icl_m2K_W / (im * L)          
        return Re_cl

    def met_calibration(self, Ta: float) -> float:
        '''
        Adjust metabolic rate based on ambient temperature.
        Parameters
        ----------
        Ta : float
            Air temperature (deg C).
        Returns
        -------
        M : float
            Adjusted metabolic rate (METS).
        ''' 
        if(Ta <= 30):
            return self.METS
        else:
            return self.METS * (0.0012 * Ta**2 - 0.0693 * Ta + 1.9955)

    def met_to_watts(self, Ta: float) -> float:
        '''
        Convert metabolic rate to watts.
        Parameters
        ----------
        Ta : float
            Air temperature (deg C).
        Returns
        -------
        W : float
            Metabolic power in watts.
        '''
        M = self.met_calibration(Ta)
        return M * self.Mass * 1.225  # W

    def AD_from_mass_height(self) -> float:  
        '''Compute body surface area using Du Bois formula.
        Returns
        -------
        AD : float
            Body surface area (m2).
        '''
        ad = 0.202 * ((self.Mass**0.425) * (self.Height**0.725))
        return ad
# =============================================================================
# Heat transfer calculations
# =============================================================================

    def fcl_from_Icl(self, Ta_C: float) -> float:
        '''Estimate clothing area factor (dimensionless) from insulation.'''
        Icl = self.cal_Icl(Ta_C)
        fcl = 1 + (0.31*Icl)
        return fcl

    def Rcl_from_Icl(self, Ta_C: float) -> float:
        '''Estimate clothing dry heat resistance from Icl (1 clo = 0.155 m2.deg C/W).'''
        Icl = self.cal_Icl(Ta_C)
        Rcl = 0.155 * Icl
        return Rcl

    def hr_cof_from_radiant_features(self, Ta_C: float, MRT_C: float, RH: float) -> float:
        '''Estimate radiative heat transfer coefficient.
        Returns
        -------
        hr_cof : float
            Radiative heat transfer coefficient (W.m-2.K-1)
        '''
        Tsk_C = self.cal_Tsk_C(Ta_C, MRT_C, RH)
        sigma_sb = 5.67E-08  # Stefan-Boltzmann constant W.m-2.K-4
        # SVF = 1  # Sky view factor
        hr_cof = 4 * self.Emm_sk * sigma_sb * self.A_eff * ((273.2 + (Tsk_C + MRT_C) / 2)**3)
        return hr_cof

    def h_coef_and_t0(self, MRT_C:float, Av_ms:float, Ta_C:float, RH: float) -> tuple[float, float]:
        '''Calculate combined heat transfer coefficient and operative temperature.'''
        hr_cof = self.hr_cof_from_radiant_features(Ta_C, MRT_C, RH)
        hc_cof = cp.hc_cof_from_Av(Av_ms)   # Convective coefficient from wind speed
        h_cof = hc_cof + hr_cof
        t0 = (MRT_C * hr_cof + Ta_C * hc_cof) / h_cof  # Operative temperature
        return h_cof, t0

    def Dry_Heat_Loss_c_plus_r(self, MRT_C:float,Av_ms:float, Ta_C:float, RH: float) -> float:
        '''This function  estimates combined dry heat loss via convection and radiation.
        Parameters
        ----------
        to_C : float
            Operative temperature in degrees Celsius
        h_cof:float
            combined convective heat transfer coefficient in W.m-2.K-1
        
        Returns
        -------
        Dry_Heat_Loss: float
            combined dry heat loss via convection and radiation in W'''    
        fcl	= self.fcl_from_Icl(Ta_C)
        Rcl	= self.Rcl_from_Icl(Ta_C)
        Tsk_C	= self.cal_Tsk_C(Ta_C, MRT_C, RH)
        Ad	= self.AD
        h_cof, t0_C = self.h_coef_and_t0(MRT_C, Av_ms, Ta_C, RH)
        
        Dry_Heat_Loss_AD = (Tsk_C-t0_C)/(Rcl+(1/(h_cof*fcl)))
        
        Dry_Heat_Loss = Dry_Heat_Loss_AD * Ad #Convertion from w.M-2 to W
        return Dry_Heat_Loss

    def Cres_from_M_Ta(self,Ta_C:float) -> float:
        '''This function estimates the respiratory heat loss via convection, using
        ASHRAE 1997 in W/m2 units, then we need to multiply by surface area to
        obtain the heat flux in W.  
        
        Parameters
        ----------
        M : float
            Rate of metabolic energy expenditure in W
        Ta_C: float
            Ambient temperature in degrees Celsius
        Ad : float
            Corporal surface area in m2
            
        Returns
        -------
        Cres : float 
            Respiratory heat loss via convection in W'''   
        MET_in_watt = self.met_to_watts(Ta_C)
        Ad = self.AD 
        Cres = 0.0014 * MET_in_watt * (34 - Ta_C) * Ad
        return Cres

    def Eres_from_M_Pa(self, RH:float,Ta_C:float) -> float:
        '''This function estimates Latent respiratory heat loss.
        ASHRAE 1997 in W/m2 units, then multiply by surface area to obtain
        the heat flux in W.
        
        Parameters
        ----------
        M : float
            Rate of metabolic energy expenditure in W
        Ta_C: float
            Ambient temperature in degrees Celsius
        RH : float
            Relative humidity in percentage
        Returns
        -------
        Eres : float
            Respiratory heat loss via evaporation in W'''    
        MET_in_watt = self.met_to_watts(Ta_C)
        Ad = self.AD
        Psa_kPa = cp.Psa_kPa_from_TaC(Ta_C)
        Pv_kPa = cp.Pv_kPa_from_Psa_RH(Psa_kPa, RH)
        Eres = 0.0173*MET_in_watt*(5.86618428-Pv_kPa)*Ad
        return Eres

# =============================================================================
# Estimation of Evaporation required and ambiental possible
# =============================================================================
    def Ereq_from_HeatFluxes(self, Ta_C:float, MRT_C:float, Av_ms:float, RH: float) -> float:
    
        '''This function estimates the amount of evaporative heat loss required for heat balance.
        
        Ereq  = (M - Wk) - (C+R) - (Cres + Eres)	
        Ereq = Hprod - Dry_Heat_Loss - CEplus_res
        
        Parameters
        ----------
        M : float
            If W is correspond to internal heat production in W, otherwise to metabolic rate in W
        W : float
            External work done for human body in W
        Dry_Heat_Loss: float
            Heat dry heat transfer by radiation and convection trough the skin in W
        Cres : float
            Dry respiratory heat loss by convection in W
        Eres : float
            Latent respiratory heat loss in W
        
        Returns
        -------
        Ereq : float
            Rate of evaporation  in watts required for heat balance to whole body'''    
        
        MET_in_watt = self.met_to_watts(Ta_C)
        Work = self.Work
        Hprod = MET_in_watt - Work
        Dry_Heat_Loss = self.Dry_Heat_Loss_c_plus_r(MRT_C, Av_ms, Ta_C, RH)
        Cres = self.Cres_from_M_Ta(Ta_C)
        Eres = self.Eres_from_M_Pa(RH, Ta_C)
        CEplus_res = Cres + Eres
        Ereq = Hprod  - Dry_Heat_Loss - CEplus_res
        return Ereq
    
    def he_cof(self, Av_ms:float) -> float:
        '''This function estimates the evaporative heat transfer coefficient using the
        Lewis relation (16.5 K/kPa).
        
        Parameters
        ----------
        hc_cof : float
            Convective heat transfer coefficient in W/m2.K
        Returns
        -------
        he_cof : float
            Evaporative heat transfer coefficient in W/m2.kPa'''    
        #As in partitional calorimetry model excel spreadsheet from Ollie Jay
        LR	= 16.5	    # K.kPa-1	Lewis Relation.
        hc_cof = cp.hc_cof_from_Av(Av_ms)
        he_cof =hc_cof*LR
        return he_cof

    def wmax(self, person_condition: str) -> float: 
        '''This function provide the maximum skin wettedness depending on the chareacteristic
        set in the personal profile file:
        
        ISO:
        Unacclimated = 0.85
        Acclimatied = 1.00
        
        Ravanelli et al. MSSE (2018):
        Untrained & Unacclimated = 0.72
        Trained & Unacclimated = 0.84
        Trained & Acclimated = 0.95
        
        Morris 2021
        0.85 for the YNG model (Candas et al., 1979a);
        0.65 for the OLD model
        
        NOTE: This is a factor to be improved in the future once there is more data
        arounf from thermal physiologist.
            
        Parameters
        ----------
        person condition : str
            Describe if the person is acclimatized or not. Also if have sweating impairments or not.
        
        Returns
        -------
        wmax : float
            Maximum skin wettednes'''
        if   person_condition == 'Unacclimated':  wmax = 0.85
        elif person_condition == 'fully acclimated':   wmax = 1
        elif person_condition == 'Untrained & Unacclimated':  wmax = 0.72
        elif person_condition == 'Trained & Unacclimated':  wmax = 0.84
        elif person_condition == 'Trained & Acclimated':  wmax = 0.95
        elif person_condition == 'YNG_Morris_2021':  wmax = 0.85
        elif person_condition == 'OLD_Morris_2021':  wmax = 0.65
        else: 
            print('Invalid "person_condition"')
        return wmax

    def Emax_env_wettedness_sweat(self, RH:float, Ta_C:float, Av_ms: float, MRT_C: float) -> float:
        '''This function estimates the maximum evaporative heat loss for a given thermal environment 
        and clothing, also known as the biophysical evaporative heat loss.
        
        Parameters
        ----------
        Psk_s : float
            Vapor pressure at the skin surface while saturated with sweat in kPa
        Pv_kPa : float
            Ambient vapour pressure in kPa
        Re_cl : float
            Evaporative resistance of clothing in m2.kPa.W-1
        he_cof : float
            Evaporative heat transfer coefficient in W.m-2.kPa-1
        Icl : float
            
        AD : float
            Dubois surface corporal area in m2
        
        Returns
        -------
        Emax_env: float
            Biophysical evaporative heat loss (cause by ambient environment and the
            clothes people wear) in Watts
        '''

        Tsk_C = self.cal_Tsk_C(Ta_C, MRT_C, RH)
        Icl = self.cal_Icl(Ta_C)
        AD = self.AD
        he_cof = self.he_cof(Av_ms)
        Psk_s = cp.Psa_kPa_from_TaC(Tsk_C)
        Psa_kPa = cp.Psa_kPa_from_TaC(Ta_C)
        Pv_kPa = cp.Pv_kPa_from_Psa_RH(Psa_kPa, RH)
        Re_cl = self.cal_Re_cl(Ta_C)
        fcl	= self.fcl_from_Icl(Ta_C)	                                             #Ratio of clothed body surface to nude body surface (dimensionless)
        wmax = self.w_max
        Emax_env_AD = (Psk_s-Pv_kPa)/(Re_cl+(1/(he_cof*fcl)))            
        # Evaporative heat loss limited by environment
        Emax_env = Emax_env_AD*AD
        Emax_wettedness = Emax_env * wmax
        # Evaporative heat loss limited by sweat rate
        Smax = self.smax_rate
        
        Ereq = self.Ereq_from_HeatFluxes(Ta_C, MRT_C, Av_ms, RH)
        wreq = Ereq/Emax_env
        r = np.where(wreq<1, 1-((wreq**2)/2),0.5)
        r = np.where(r>1,1,r)
        Emax_sweat_rate = ((Smax*Lh_vap*density)/3.6)*r
        # print(f"Emax_env: {Emax_env:.2f} W, Emax_wettedness: {Emax_wettedness:.2f} W, Emax_sweat_rate: {Emax_sweat_rate:.2f} W, r: {r:.2f}")
        return min(Emax_env, Emax_wettedness, Emax_sweat_rate), r

    def heat_storage_in_the_period(self, RH:float, Ta_C:float, Av_ms: float, MRT_C: float, TimeExposure_hr:float) -> float:     
        '''This function estimates the heat storage capacity of the human body.
        This is a function of the body mass and the heat capacity of the human body.    
        Parameters
        '''
        Emax,r = self.Emax_env_wettedness_sweat(RH, Ta_C, Av_ms, MRT_C)
        Ereq = self.Ereq_from_HeatFluxes(Ta_C, MRT_C, Av_ms, RH)
        # Heat_storage_rate = max(Ereq - Emax, 0)                              
        Heat_storage_rate = Ereq - Emax
        return Heat_storage_rate * TimeExposure_hr * 3600
    
    def sweat_in_the_period(self, RH:float, Ta_C:float, Av_ms: float, MRT_C: float, TimeExposure_hr:float) -> float:     
        '''This function estimates the heat storage capacity of the human body.
        This is a function of the body mass and the heat capacity of the human body.    
        Parameters
        '''
        Emax,r = self.Emax_env_wettedness_sweat(RH, Ta_C, Av_ms, MRT_C)
        Ereq   = self.Ereq_from_HeatFluxes(Ta_C, MRT_C, Av_ms, RH)
        ES = min(Ereq, Emax)
        S = ES / r / (Lh_vap*density) * TimeExposure_hr * 3600 / 1000
        return max(S,0)

    def q_remove(self, RH:float, Ta_C:float, Av_ms: float, MRT_C: float, TimeExposure_hr:float) -> float:
        '''
        Estimate heat dissipation during cycling in cold environments using ISO 11079 IREQ model.
        Parameters
        ----------
        RH : float
            Relative humidity (%).
        Ta_C : float
            Ambient air temperature (deg C).
        Av_ms : float
            Wind speed (m/s).
        MRT_C : float
            Mean radiant temperature (deg C).
        TimeExposure_hr : float
            Duration of exposure in hours.
        Returns
        -------
        S : float
            Heat dissipation power in cold conditions (W).
        '''
        # Metabolic and environmental parameters setup
        Icl = self.cal_Icl(Ta_C)          # Clothing insulation (1 clo = 0.155 m2K/W)
        M = (self.METS + 1.5) * 58.15     # Metabolic energy production (W/m2)
        W = 0                             # External work (normally 0 W/m2)
        Ta = Ta_C                          # Ambient temperature (deg C)
        Tr = MRT_C                         # Mean radiant temperature (deg C)
        p = 8                              # Air permeability (l/m2s)
        w = 8                              # Walking speed (m/s)
        v = max(0.4, min(Av_ms,18))        # Relative air velocity (0.4 to 18 m/s)
        rh = RH                             # Relative humidity (%)
        Icl = Icl * 0.155                 # Clothing insulation (1 clo = 0.155 W/m2K)
        AD = self.AD                        # Body surface area (m2)

        # Limit parameters to realistic ranges
        M = max(58, min(M, 400))
        w = max(0.0052*(M-58), min(w, 1.2))
        v = max(0.4, min(v, 18))

        Ia = 0.092 * math.exp(-0.15*v - 0.22*w) - 0.0045  # Air convective thermal resistance

        for calculation in [2]:  # 1: minimal, 2: neutral
            # --- Skin temperature and wettedness ---
            if calculation == 1:
                Tsk = 33.34 - 0.0354*M
                wetness = 0.06
            else:
                Tsk = 35.7 - 0.0285*M
                wetness = 0.001*M

            # --- Vapor pressure calculation ---
            Tex = 29 + 0.2 * Tsk
            Psks = cp.Psa_kPa_from_TaC(Tex)  # Saturated vapor pressure at skin surface
            Pex = cp.Psa_kPa_from_TaC(Ta_C)  # Saturated vapor pressure in ambient air
            Pa = cp.Pv_kPa_from_Psa_RH(Pex, RH)  # Actual vapor pressure at skin

            # --- DLE iterative solution ---
            Tcl = Ta
            hr = 3
            S = -40
            ArAdu = self.AD
            factor = 500
            Iclr = Icl

            while True:
                fcl = 1 + 1.197*Iclr
                Iclr = ((Icl + 0.085/fcl) * (0.54*math.exp(-0.15*v - 0.22*w) * p**0.075 - 0.06*math.log(p) + 0.5) - (Ia)/fcl)
                Rt = (0.06/0.38) * (Ia + Iclr)
                E = wetness*(Psks-Pa)/Rt
                Hres = 1.73e-2*M*(Pex-Pa) + 1.4e-3*M*(Tex-Ta)
                Tcl = Tsk - Iclr*(M - W - E - Hres - S)
                hr = 5.67e-8*0.95*ArAdu*(math.exp(4*math.log(273+Tcl)) - math.exp(4*math.log(273+Tr))) / (Tcl-Tr)
                hc = 1/Ia - hr
                R = fcl * hr * (Tcl-Tr)
                C = fcl * hc * (Tcl-Ta)
                Balance = M - W - E - Hres - R - C - S
                if abs(Balance) <= 0.01:
                    break
                if Balance > 0:
                    S += factor
                    factor /= 2
                else:
                    S -= factor
        S = min(round(S, 2), 0)
        return S * TimeExposure_hr * 3600 * AD  # Convert to total heat dissipation in Joules

    def q_recovery(self, RH:float, Ta_C:float, Av_ms: float, MRT_C: float, TimeExposure_hr:float) -> float:
        '''
        Estimate core temperature recovery power during indoor rest.
        Parameters
        ----------
        RH : float
            Indoor relative humidity (%).
        Ta_C : float
            Indoor air temperature (deg C).
        Av_ms : float
            Indoor air velocity (m/s).
        MRT_C : float
            Indoor mean radiant temperature (deg C).
        TimeExposure_hr : float
            Duration of exposure in hours.
        Returns
        -------
        S : float
            Heat recovery power (W).
        '''
        Icl = self.cal_Icl(Ta_C)
        M = 58.15 * 1.5         # Metabolic energy production (W/m2)
        W = 0                   # Mechanical work rate (normally 0 W/m2)
        Ta = 25                 # Ambient air temperature for indoor recovery
        Tr = 25                 # Mean radiant temperature
        p = 8                   # Air permeability (l/m2s)
        w = 8                   # Walking speed or equivalent movement
        v = max(0.4, min(Av_ms,18))  # Relative air velocity
        rh = RH                 # Relative humidity (%)
        Icl = (Icl-0.5) * 0.155 # Clothing insulation
        AD = self.AD            # Body surface area

        # Limit parameters to realistic ranges
        M = max(58, min(M, 400))
        w = max(0.0052*(M-58), min(w, 1.2))
        v = max(0.4, min(v, 18))
        Ia = 0.092 * math.exp(-0.15*v - 0.22*w) - 0.0045  # Air convective thermal resistance

        for calculation in [2]:  # 1: minimal, 2: neutral
            if calculation == 1:
                Tsk = 33.34 - 0.0354*M
                wetness = 0.06
            else:
                Tsk = 35.7 - 0.0285*M
                wetness = 0.001*M

            Tex = 29 + 0.2 * Tsk
            Psks = cp.Psa_kPa_from_TaC(Tex)  # Saturated vapor pressure at skin
            Pex = cp.Psa_kPa_from_TaC(Ta_C)  # Ambient saturated vapor pressure
            Pa = cp.Pv_kPa_from_Psa_RH(Pex, RH)  # Actual vapor pressure at skin

            Tcl = Ta
            hr = 3
            S = -40
            ArAdu = self.AD
            factor = 100
            Iclr = Icl

            while True:
                fcl = 1 + 1.197*Iclr
                Iclr = ((Icl+0.085/fcl)*(0.54*math.exp(-0.15*v-0.22*w)*p**0.075 - 0.06*math.log(p)+0.5) - (Ia)/fcl)
                Rt = (0.06/0.38)*(Ia + Iclr)
                E = wetness*(Psks-Pa)/Rt
                Hres = 1.73e-2*M*(Pex-Pa) + 1.4e-3*M*(Tex-Ta)
                Tcl = Tsk - Iclr*(M - W - E - Hres - S)
                hr = 5.67e-8*0.95*ArAdu*(math.exp(4*math.log(273+Tcl)) - math.exp(4*math.log(273+Tr))) / (Tcl-Tr)
                hc = 1/Ia - hr
                R = fcl* hr *(Tcl-Tr)
                C = fcl* hc *(Tcl-Ta)
                Balance = M - W - E - Hres - R - C - S
                if abs(Balance) <= 0.01:
                    break
                if Balance > 0:
                    S += factor
                    factor /= 2
                else:
                    S -= factor
        S = max(round(S,2),0)
        return S * TimeExposure_hr * 3600 * AD  # Total recovery heat in Joules 

    def heat_dissipation_in_the_period(self, RH:float, Ta_C:float, Av_ms: float, MRT_C: float, TimeExposure_hr:float) -> float:     
        '''
        Compute total heat dissipation over a period including cold exposure and indoor recovery.
        Returns net energy loss in Joules.
        '''
        Q_REMOVE = self.q_remove(RH, Ta_C, Av_ms, MRT_C, TimeExposure_hr)
        Q_RECOVERY = self.q_recovery(RH, 25, 0.5, 25, 1 - TimeExposure_hr)
        Heat_dissipation = - (Q_REMOVE + Q_RECOVERY)
        return Heat_dissipation

if __name__ == "__main__":
    rider1 = rider("Shanghai", "YNG_Morris_2021")
    print(rider1.cal_Tsk_C(38, 70, 40))
    print(rider1.cal_Icl(38))
    print(rider1.cal_Re_cl(38))
    
    # print(rider1.Dry_Heat_Loss_c_plus_r(70, 7, 35))
    # print(rider1.Cres_from_M_Ta(35))
    # print(rider1.Eres_from_M_Pa(50, 35))
    print(rider1.Ereq_from_HeatFluxes(38, 70, 7, 40))
    # print(rider1.he_cof(7))
    # print(rider1.wmax)
    
    print(rider1.Emax_env_wettedness_sweat(40, 38, 7, 70))
    print(rider1.heat_storage_in_the_period(40, 38, 7.06, 70, 0.8))
    # print(rider1.sweat_in_the_period(47, 37.8, 7.06, 70.55, 1))
    # print(rider1.Ereq_from_HeatFluxes(37.8, 70.55, 7, 47))
    rider2 = rider("Harbin", "YNG_Morris_2021")
    # print(rider2.Tsk_C)
    print(rider2.cal_Tsk_C(-20, -20, 70))
    # print(rider2.cal_Icl(-20))
    # print(rider2.cal_Re_cl(-20))
    # print(rider2.heat_dissipation_in_the_period(70, -25, 7, -25, 0.8))
    
