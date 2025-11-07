# app.py — Una sola estrategia con resumen anual/mensual (archivo ligero)
# ---------------------------------------------------------------
# Requisitos: ver requirements.txt
# Ejecución local: streamlit run app.py
# ---------------------------------------------------------------

import pandas as pd
import numpy as np
import streamlit as st
import altair as alt
from pathlib import Path

st.set_page_config(page_title="Estrategia • Smart Investment", layout="wide")
st.title("📈 Estrategia Smart Investment")

st.caption(
    "Este dashboard lee un único Excel con hojas 'RECOMENDADO' y/o 'MEDIO'. "
    "Soporta columnas ligeras: Time, AÑO, DIVISA, Type, Order, LLAVE, Profit/PROFIT y/o Balance. "
    "El único filtro disponible es AÑO."
)

# =============================
# RUTA RELATIVA DE TU ARCHIVO
# =============================
BASE = Path(__file__).parent
RUTA_ESTRAT = BASE / "data" / "STREAMLIT.xlsx"  # 👈 Solo un archivo

# =============================
# UTILIDADES
# =============================

def _parse_time(df: pd.DataFrame) -> pd.DataFrame:
    if "Time" in df.columns:
        df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
        df["AÑO"]  = df["Time"].dt.year
        df["YEAR"] = df["AÑO"]
        df["YM"]   = df["Time"].dt.to_period("M").astype(str)
    elif "AÑO" in df.columns:
        df["YEAR"] = pd.to_numeric(df["AÑO"], errors="coerce")
    else:
        df["YEAR"] = np.nan
    return df

def _ensure_profit(df: pd.DataFrame) -> pd.DataFrame:
    if "PROFIT" in df.columns:
        df["PROFIT"] = pd.to_numeric(df["PROFIT"], errors="coerce").fillna(0.0)
        return df
    if "Profit" in df.columns:
        df = df.rename(columns={"Profit": "PROFIT"})
        df["PROFIT"] = pd.to_numeric(df["PROFIT"], errors="coerce").fillna(0.0)
        return df
    if "Balance" in df.columns:
        if "Time" in df.columns:
            df = df.sort_values("Time").reset_index(drop=True)
        else:
            df = df.reset_index(drop=True)
        bal = pd.to_numeric(df["Balance"], errors="coerce").ffill().fillna(0.0)
        df["PROFIT"] = bal.diff().fillna(bal)
        return df
    df["PROFIT"] = 0.0
    return df

def _equity_series(df: pd.DataFrame) -> pd.Series:
    if "Balance" in df.columns:
        return pd.to_numeric(df["Balance"], errors="coerce").ffill().fillna(0.0)
    return pd.to_numeric(df["PROFIT"], errors="coerce").fillna(0.0).cumsum()

def _max_drawdown_pct(equity: pd.Series) -> float:
    peak = equity.cummax().replace(0, np.nan)
    dd_pct = (equity / peak - 1.0) * 100.0
    m = dd_pct.min() if not dd_pct.empty else 0.0
    return abs(float(m)) if pd.notna(m) else 0.0

def _annual_returns_pct(df: pd.DataFrame) -> pd.DataFrame:
    if "YEAR" not in df.columns or df["YEAR"].isna().all():
        return pd.DataFrame({"YEAR": [], "annual_pct": []})
    if "Time" in df.columns:
        df = df.sort_values("Time")
    eq = _equity_series(df)
    df = df.copy()
    df["EQUITY"] = eq.values
    g = df.groupby("YEAR")
    ret = ((g["EQUITY"].last() / g["EQUITY"].first()) - 1.0) * 100.0
    out = ret.reset_index().rename(columns={"EQUITY": "annual_pct", 0: "annual_pct"})
    out.columns = ["YEAR", "annual_pct"]
    return out

def _monthly_returns_pct(df: pd.DataFrame) -> pd.DataFrame:
    if "Time" not in df.columns:
        return pd.DataFrame({"YM": [], "monthly_pct": []})
    tmp = df.sort_values("Time").copy()
    tmp["EQUITY"] = _equity_series(tmp).values
    tmp["YM"]     = tmp["Time"].dt.to_period("M").astype(str)
    g = tmp.groupby("YM")
    ret = ((g["EQUITY"].last() / g["EQUITY"].first()) - 1.0) * 100.0
    out = ret.reset_index().rename(columns={"EQUITY": "monthly_pct", 0: "monthly_pct"})
    out.columns = ["YM", "monthly_pct"]
    return out

def _load_data_from_path(ruta_excel: Path) -> pd.DataFrame:
    xl = pd.ExcelFile(ruta_excel, engine="openpyxl")
    present = {s.lower(): s for s in xl.sheet_names}

    load_order = []
    for key, label in [("recomendado", "Recomendado"), ("medio", "Medio")]:
        if key in present:
            load_order.append((present[key], label))
    if not load_order:
        first_sheet = xl.sheet_names[0]
        load_order = [(first_sheet, "Recomendado")]

    frames = []
    for sheet_orig, label in load_order:
        df = pd.read_excel(xl, sheet_name=sheet_orig, engine="openpyxl")
        df = _parse_time(df)
        df = _ensure_profit(df)
        df["RIESGO"] = label  # se conserva, no se usa para filtrar
        frames.append(df)

    return pd.concat(frames, ignore_index=True)

def _render_dashboard(data: pd.DataFrame, nombre: str = "Estrategia"):
    st.header(nombre)
    st.sidebar.markdown(f"### Filtro — {nombre}")

    df = data.copy()

    if df["YEAR"].notna().any():
        y_min, y_max = int(df["YEAR"].min()), int(df["YEAR"].max())
        y1, y2 = st.sidebar.slider("Rango de años", y_min, y_max, (y_min, y_max))
        df = df[(df["YEAR"] >= y1) & (df["YEAR"] <= y2)]
    else:
        st.sidebar.info("No hay columna de año. Asegura incluir 'Time' o 'AÑO'.")

    # --- KPIs ---
    pnl = pd.to_numeric(df["PROFIT"], errors="coerce").fillna(0.0)
    trades = int(len(pnl))
    winrate = float((pnl > 0).mean() * 100) if trades else 0.0

    equity = _equity_series(df)
    max_dd_pct = _max_drawdown_pct(equity)

    monthly = _monthly_returns_pct(df)
    avg_monthly_pct = float(monthly["monthly_pct"].mean()) if not monthly.empty else 0.0

    annual = _annual_returns_pct(df)
    max_annual_gain = float(annual["annual_pct"].max()) if not annual.empty else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Operaciones", f"{trades:,}")
    c2.metric("Win rate", f"{winrate:.1f}%")
    c3.metric("Ganancia prom. por Mes", f"{avg_monthly_pct:.1f}%")
    c4.metric("Máx. ganancia anual", f"{max_annual_gain:.1f}%")

    c5, _ = st.columns([1, 3])
    with c5:
        st.metric("Máx. drawdown", f"{max_dd_pct:.1f}%")

    # =============================
    # Simulador de inversión (nuevo)
    # =============================
    st.divider()
    st.subheader("Simulador de inversión con rendimiento promedio mensual")
    monto = st.number_input(
        "Monto a invertir (MXN)",
        min_value=0.0,
        value=0.0,
        step=100.0,
        format="%.2f",
        help="Ingresa el monto a invertir. Se multiplica por la ganancia promedio mensual del periodo filtrado."
    )

    if monthly.empty:
        st.info("No hay datos mensuales suficientes para calcular la ganancia promedio mensual.")
        rendimiento_mensual = 0.0
    else:
        rendimiento_mensual = monto * (avg_monthly_pct / 100.0)

    st.success(f"Ganancia promedio mensual: ${rendimiento_mensual:,.2f} MXN")

    st.divider()

    # --- Gráfico anual ---
    st.subheader("% Ganancia o Pérdida por Año")
    if not annual.empty:
        annual_sorted = annual.sort_values("YEAR")
        chart = (
            alt.Chart(annual_sorted)
            .mark_bar()
            .encode(
                x=alt.X("YEAR:O", title="Año"),
                y=alt.Y("annual_pct:Q", title="% Ganancia o Pérdida"),
                tooltip=[
                    alt.Tooltip("YEAR:O", title="Año"),
                    alt.Tooltip("annual_pct:Q", title="%", format=".1f")
                ],
            )
            .properties(height=340)
        )
        labels = (
            alt.Chart(annual_sorted)
            .mark_text(dy=-6)
            .encode(
                x="YEAR:O",
                y="annual_pct:Q",
                text=alt.Text("annual_pct:Q", format=".0f"))
        )
        st.altair_chart(chart + labels, use_container_width=True)
    else:
        st.info("No fue posible calcular el rendimiento anual. Asegúrate de incluir 'Time' o 'AÑO'.")

    st.divider()

    # --- Resumen mensual ---
    st.subheader("Resumen mensual")
    if "Time" in df.columns and not df.empty:
        tmp = df.sort_values("Time").copy()
        tmp["YM"] = tmp["Time"].dt.to_period("M")
        grp = tmp.groupby("YM")

        total_trades_m = grp.size().rename("Total de trades")
        winrate_m = (
            grp["PROFIT"]
            .apply(lambda x: (pd.to_numeric(x, errors="coerce").fillna(0.0) > 0).mean() * 100)
            .rename("% Trades positivos")
        )

        monthly_pct = _monthly_returns_pct(tmp)
        monthly_pct_index = pd.PeriodIndex(monthly_pct["YM"], freq="M")
        monthly_pct_series = monthly_pct.set_index(monthly_pct_index)["monthly_pct"].rename("% Ganancia o Pérdida Mes")

        monthly_table = (
            pd.concat([total_trades_m, winrate_m, monthly_pct_series], axis=1)
            .reset_index()
            .rename(columns={"YM": "Fecha Mes y año"})
            .sort_values("Fecha Mes y año")
        )
        monthly_table["Fecha Mes y año"] = monthly_table["Fecha Mes y año"].dt.to_timestamp()
        monthly_table["% Trades positivos"] = monthly_table["% Trades positivos"].round(2)
        monthly_table["% Ganancia o Pérdida Mes"] = monthly_table["% Ganancia o Pérdida Mes"].round(2)

        st.dataframe(monthly_table, use_container_width=True)
    else:
        st.info("Para el resumen mensual se requiere columna de fecha/hora en `Time`.")

# =============================
# CARGA Y RENDER
# =============================

def _safe_load(path: Path):
    try:
        return _load_data_from_path(path)
    except Exception as e:
        st.warning(f"No se pudo cargar {path.name}: {e}")
        return None

data = _safe_load(RUTA_ESTRAT)
if data is None:
    st.stop()

_render_dashboard(data, nombre="Estrategia")

#    Time  AÑO  DIVISA  Type  Order  LLAVE  Profit  PROFIT  Balance
