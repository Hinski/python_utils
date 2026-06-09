from typing import Union
#########################################################################################################################
    #########################################################################################################################
    # Speicheränderung berechnen
def storage_change(ah: pd.Series,           # absolute humidity
                   T: pd.Series,            # Air temperature
                   zm: float,               # measurement height
                   veg_h: Union[float, pd.Series],         # vegetation height
                   Ts: pd.Series,           # Soil temperature
                   start: str,
                   end: str
                  )-> pd.DataFrame:

    # --- Common start and end ---
    ah = ah[start:end]
    T = T[start:end]
    veg_h = veg_h[start:end]
    Ts = Ts.sort_index()
    Ts = Ts.loc[(Ts.index >= start) & (Ts.index <= end)]
    dt = T.index.to_series().diff().dt.total_seconds()


    # ---- dSl Änderung des latenten Wärmespeichers ----

    def calculate_rhov(ah,T):
        T_kelvin = T + 273.15
        rhov = (ah*100) / (461.5*T_kelvin)
        return rhov
    rhov = calculate_rhov(ah,T)

    def calculate_dSl(rhov,zm):
        L = 2.5e6   #latent heat of evaporation [J/kg]
        dSl = L * zm * (rhov.diff()/dt)
        return dSl
    dSl = calculate_dSl(rhov,zm)


    # ---- dSh Änderung des sensiblen Wärmespeichers ----

    def calculate_dSh(T,zm):
        pa = 1.225 #[kg/m3] dichte trockener luft
        cp = 1005  # Spezifische Wärmekapazität der trockenen Luft in J/(kg*K)
        dSh = pa * cp * zm * (T.diff()/dt)
        return dSh
    dSh = calculate_dSh(T,zm)


    # ---- dSb Änderung des Biomassespeichers berechnen ----

    def calculate_dSb(Ts,zh):
        Ts_kelvin = Ts + 273.15
        cb = 17 #[J/(kg K)]
        mv = 0.8 * zh
        dSb = cb * mv * (Ts_kelvin.diff()/dt)
        return dSb

    dSb = calculate_dSb(Ts,veg_h)

    storage_change = pd.DataFrame({
        "dSl": dSl,
        "dSh": dSh,
        "dSb": dSb,
    })
    return storage_change
