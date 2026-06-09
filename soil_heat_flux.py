def Gsoil_calc(df, site):
    if site == 'Nazinga':
        vwc = (df['VW_1_Avg'] + df['VW_2_Avg'] + df['VW_3_Avg'])/3
        vwc = vwc.where((vwc > 0) & (vwc< 0.51))
        Ts = (df['TCAV_C_Avg(1) [DegC]'] + df['TCAV_C_Avg(2) [DegC]'] + df['TCAV_C_Avg(3) [DegC]'])/3
        Ts = Ts.rolling(window=3, center=True, min_periods=1).mean()   # smooth noise
        delta_Ts = Ts.diff().where(lambda x: x.abs() < 2)
        fm = 0.503
        fo = 0.033
        Cv = (1.9 * fm + 2.47 * fo + 4.12 * vwc) * 10**6
        G_raw = (df['H_Flux_sc_8_Mitte_Avg [W/m^2]'] +  df['H_Flux_sc_8_Ost_Avg [W/m^2]'])/2
        Gs = Cv * (delta_Ts/1800)*0.08
        G = G_raw + Gs
        G = G.where((G >= -400) & (G <= 400))
        G_df = {
            "G_raw": G_raw,
            "G": G,
            "Ts_3cm": Ts,
            "VWC": vwc,
            "Gs": Gs
                }

    elif site == 'Mole':
        vwc = (df['VWC_Avg'] + df['VWC_2_Avg'] + df['VWC_3_Avg'])/3
        vwc = vwc.where((vwc > 0) & (vwc< 0.51))
        Ts = (df['T_Avg'] + df['T_2_Avg'] + df['T_3_Avg'])/3
        Ts = Ts.rolling(window=3, center=True, min_periods=1).mean()   # smooth noise
        delta_Ts = Ts.diff().where(lambda x: x.abs() < 2)
        fm = 0.503
        fo = 0.033
        Cv = (1.9 * fm + 2.47 * fo + 4.12 * vwc) * 10**6
        G_raw = (df['H_Flux_8_Middle_Avg'] +  df['H_Flux_8_East_Avg'] + df['H_Flux_8_West_Avg'])/3
        Gs = Cv * (delta_Ts/1800)*0.08
        G = G_raw + Gs
        G = G.where((G >= -200) & (G <= 400))
        G_df = {
            "G_raw": G_raw,
            "G": G,
            "Ts_3cm": Ts,
            "VWC": vwc,
            "Gs": Gs
                }

    elif site == 'Kayoro':
        vwc = (df['VW_1_Avg'] + df['VW_2_Avg'] + df['VW_3_Avg'])/3
        vwc = vwc.where((vwc > 0) & (vwc< 0.51))
        Ts = df['TCAV_C_Avg(1) [DegC]']
        Ts = Ts.where((Ts > 0 ) & (Ts < 60))
        Ts = Ts.rolling(window=3, center=True, min_periods=1).mean()   # smooth noise
        delta_Ts = Ts.diff().where(lambda x: x.abs() < 2)
        fm = 0.5284
        fo = 0.0062
        Cv = (1.9 * fm + 2.47 * fo + 4.12 * vwc) * 10**6
        G_raw = (df['H_Flux_sc_8_Ost_Avg [W/m^2]'] +  df['H_Flux_sc_8_Mitte_Avg [W/m^2]'] +
             df['H_Flux_sc_8_West_Avg [W/m^2]'])/3
        Gs = Cv * (delta_Ts/1800)*0.08
        G = G_raw + Gs
        G = G.where((G >= -200) & (G <= 400))
        G_df = {
            "G_raw": G_raw,
            "G": G,
            "Ts_3cm": Ts,
            "VWC": vwc,
            "Gs": Gs,
            "Cv" : Cv
                }

    elif site == 'Sumbrungu':
        vwc = (df['VW_1_Avg'] + df['VW_3_Avg'] + df['VW_3_Avg'])/3
        vwc = vwc.where((vwc > 0) & (vwc< 0.51))
        Ts = (df['TCAV_C_Avg(1) [DegC]'] + df['TCAV_C_Avg(2) [DegC]'] + df['TCAV_C_Avg(3) [DegC]'])/3
        Ts = Ts.rolling(window=3, center=True, min_periods=1).mean()   # smooth noise
        delta_Ts = Ts.diff().where(lambda x: x.abs() < 2)
        fm = 0.5171
        fo = 0.016
        Cv = (1.9 * fm + 2.47 * fo + 4.12 * vwc) * 10**6
        G_raw = (df['H_Flux_sc_8_Mitte_Avg [W/m^2]'] +  df['H_Flux_sc_8_Ost_Avg [W/m^2]'] +
             df['H_Flux_sc_8_Ost_Avg [W/m^2]'])/3
        Gs = Cv * (delta_Ts/1800)*0.08
        G = G_raw + Gs
        G = G.where((G >= -200) & (G <= 400))
        G_df = {
            "G_raw": G_raw,
            "G": G,
            "Ts_3cm": Ts,
            "VWC": vwc,
            "Gs": Gs
                }

    elif site == 'Gorigo':
        vwc = (df['VW_1_Avg'] + df['VW_3_Avg'])/2
        vwc = vwc.where((vwc > 0) & (vwc< 0.51))
        Ts = df['TCAV_C_Avg(1)']
        Ts = Ts.rolling(window=3, center=True, min_periods=1).mean()   # smooth noise
        delta_Ts = Ts.diff().where(lambda x: x.abs() < 2)
        fm = 0.5171             # values taken from Sumbrugu
        fo = 0.016             # values taken from Sumbrugu
        Cv = (1.9 * fm + 2.47 * fo + 4.12 * vwc) * 10**6
        G_raw =  df['H_Flux_sc_8_Ost_Avg']         #(df['H_Flux_sc_8_Mitte_Avg'] +  df['H_Flux_sc_8_Ost_Avg'] +
        Gs = Cv * (delta_Ts/1800)*0.08
        G = G_raw + Gs
        G = G.where((G >= -200) & (G <= 400))
        G_df = {
            "G_raw": G_raw,
            "G": G,
            "Ts_3cm": Ts,
            "VWC": vwc,
            "Gs": Gs
                }

    elif site == 'Janga':
        vwc = df['SWC_1'] / 100       # the unit in the file is wrong
        #vwc = vwc.where((vwc > 0) & (vwc < 0.6))
        vwc = vwc.where((vwc > 0) & (vwc< 0.51))
        Ts = df['Tsoil_f']
        Ts = Ts.rolling(window=3, center=True, min_periods=1).mean()   # smooth noise
        delta_Ts = Ts.diff().where(lambda x: x.abs() < 2)
        #delta_Ts = Ts.diff()
        fm = 0.5171             # values taken from Sumbrugu
        fo = 0.016             # values taken from Sumbrugu
        Cv = (1.9 * fm + 2.47 * fo + 4.12 * vwc) * 10**6
        G_raw = (df['G_1'] +  df['G_2'] +
             df['G_3'])/3
        G_raw = G_raw.where((G_raw > -200) & (G_raw < 400))

        Gs = Cv * (delta_Ts/1800)*0.08
        G = G_raw + Gs
        G = G_raw + Gs
        G = G.where((G >= -400) & (G <= 400))
        G_df = {
            "G_raw": G_raw,
            "G": G,
            "Ts_3cm": Ts,
            "VWC": vwc,
            "Gs": Gs
                }
        G_df = pd.DataFrame(G_df)


    return pd.DataFrame(G_df)



