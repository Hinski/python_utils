import pandas as pd
import matplotlib.pyplot as plt

FILE = "/Volumes/Extreme SSD/WASCAL_2_KAYORO/Kay_CR1000_2021_2023_final.csv"

# --- Einlesen ---
df = pd.read_csv(
    FILE,
    index_col=0,              # erste Spalte = Zeit
    parse_dates=True,         # Datetime parsen
    na_values=["", "NA"]     # leere Felder als NaN
)

# manchmal heißt die erste Spalte 'Unnamed: 0'
df.index.name = "datetime"

# alles numerisch erzwingen (wichtig bei CR1000 Exports)
df = df.apply(pd.to_numeric, errors="coerce")

print("Verfügbare Variablen:")
print(df.columns.tolist())


# --- Variablen hier auswählen ---
vars_to_plot = [
    "H_Flux_sc_8_Ost_Avg",
    "H_Flux_sc_8_West_Avg",
    "H_Flux_sc_8_Mitte_Avg"
]



# --- Subplots ---
n = len(vars_to_plot)
fig, axes = plt.subplots(n, 1, figsize=(14, 3*n), sharex=True)

# Falls nur eine Variable geplottet wird
if n == 1:
    axes = [axes]

for ax, var in zip(axes, vars_to_plot):
    ax.plot(df.index, df[var])
    ax.set_ylabel(var)
    ax.set_ylim(-400,1000)
    ax.grid(True)

axes[-1].set_xlabel("Time")

plt.tight_layout()
plt.show()



# --- Plot ---
#df[vars_to_plot].plot(figsize=(12,6))
#plt.xlabel("Time")
#plt.ylabel("Value")
#plt.title("Selected variables")
#plt.tight_layout()
#plt.show()
