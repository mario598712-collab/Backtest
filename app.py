# app.py — Dos estrategias en pestañas (ruta relativa) con resumen anual y mensual
# ---------------------------------------------------------------
# Requisitos: ver requirements.txt
# Ejecución local: streamlit run app.py
# ---------------------------------------------------------------

import pandas as pd
import numpy as np
import streamlit as st
import altair as alt
from pathlib import Path

st.set_page_config(page_title="Estrategias • Recomendado y Medio", layout="wide")
st.title("📈 Estrategias con riesgo Recomendado y Medio (2 archivos)")

st.caption(
    "Cada pestaña carga un archivo Excel distinto con hojas **RECOMENDADO** y **MEDIO**. "
    "Se muestran KPIs, gráfico de % anual, y resumen mensual."
)

# =============================
# RUTAS RELATIVAS DE TUS ARCHIVOS
# =============================
BASE = Path(__file__).parent
RUTA_ESTRAT_1 = BASE / "data" / "STREAMLIT.xlsx"
RUTA_ESTRAT_2 = BASE / "data" / "STREAMLIT_2.xlsx"

# =============================
# UTILIDADES
# =============================

def _parse_time(df: pd.DataFrame) -> pd.DataFrame:
    if "Time" in df.columns:
        df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
        df["AÑO"] = df["Time"].dt.year
        df["YEAR"] = df["AÑO"]
        df["YM"] = df["Time"].dt.to_period("M").astype(str)
    elif "AÑO" in df.columns:
        df["YEAR"] = pd.to_numeric(df["AÑO"], errors="coerce")
    else:
        df["YEAR"] = np.nan
    return df


def _ensure_profit(df: pd.DataFrame) -> pd.DataFrame:
    if "PROFIT" in df.columns:
        df["PROFIT"] = pd.to_numeric(df["PROFIT"], errors="coerce").fillna(0.0)
    elif "Profit" in df.columns:
        df.rename(columns={"Profit": "PROFIT"}, inplace=True)
        df["PROFIT"] = pd.to_numeric(df["PROFIT"], errors="coerce").fillna(0.0)
    elif "Balance" in df.columns:
        if "Time" in df.columns:
            df = df.sort_values("Time").reset_index(drop=True)
        else:
            df = df.reset_index(drop=True)
        bal = pd.to_numeric(df["Balance"], errors="coerce").fillna(method="ffill").fillna(0.0)
        df["PROFIT"] = bal.diff().fillna(bal)
    else:
        df["PROFIT"] = 0.0
    return df


def _equity_series(df: pd.DataFrame) -> pd.Series:
    if "Balance" in df.columns:
        eq = pd.to_numeric(df["Balance"], errors="coerce").fillna(method="ffill").fillna(0.0)
    else:
        eq = pd.to_numeric(df["PROFIT"], errors="coerce").fillna(0.0).cumsum()
    return eq


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
    tmp["YM"] = tmp["Time"].dt.to_period("M").astype(str)
    g = tmp.groupby("YM")
    ret = ((g["EQUITY"].last() / g["EQUITY"].first()) - 1.0) * 100.0
    out = ret.reset_index().rename(columns={"EQUITY": "monthly_pct", 0: "monthly_pct"})
    out.columns = ["YM", "monthly_pct"]
    return out


def _load_data_from_path(ruta_excel: Path) -> pd.DataFrame:
    xl = pd.ExcelFile(ruta_excel, engine="openpyxl")  # 👈 engine forzado
    present = {s.lower(): s for s in xl.sheet_names}
    load_order = []
    for key, label in [("recomendado", "Recomendado"), ("medio", "Medio")]:
        if key in present:
            load_order.append((present[key], label))
    if not load_order:
        st.error(f"No encontré hojas 'RECOMENDADO' o 'MEDIO' en: {ruta_excel.name}")
        st.stop()
    frames = []
    for sheet_orig, label in load_order:
        df = pd.read_excel(xl, sheet_name=sheet_orig, engine="openpyxl")  # 👈 engine forzado
        df = _parse_time(df)
        df = _ensure_profit(df)
        df["RIESGO"] = label
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def _render_dashboard(data: pd.DataFrame, nombre: str):
    st.header(nombre)

    # --- Filtros ---
    st.sidebar.markdown(f"### Filtros — {nombre}")
    riesgos = list(data["RIESGO"].dropna().unique())
    riesgo = st.sidebar.selectbox(f"Perfil de riesgo ({nombre})", options=riesgos, index=0, key=f"riesgo_{nombre}")

    df_risk = data[data["RIESGO"] == riesgo].copy()
    if df_risk["YEAR"].notna().any():
        y_min, y_max = int(df_risk["YEAR"].min()), int(df_risk["YEAR"].max())
        y1, y2 = st.sidebar.slider(f"Rango de años ({nombre})", y_min, y_max, (y_min, y_max), key=f"years_{nombre}")
        df_risk = df_risk[(df_risk["YEAR"] >= y1) & (df_risk["YEAR"] <= y2)]

    if "Time" in df_risk.columns:
        df_risk = df_risk.sort_values("Time").reset_index(drop=True)

    # --- KPIs ---
    pnl = pd.to_numeric(df_risk["PROFIT"], errors="coerce").fillna(0.0)
    trades = int(len(pnl))
    winrate = float((pnl > 0).mean() * 100) if trades else 0.0

    equity = _equity_series(df_risk)
    max_dd_pct = _max_drawdown_pct(equity)

    monthly = _monthly_returns_pct(df_risk)
    avg_monthly_pct = float(monthly["monthly_pct"].mean()) if not monthly.empty else 0.0

    annual = _annual_returns_pct(df_risk)
    avg_annual_pct = float(annual["annual_pct"].mean()) if not annual.empty else 0.0
    max_annual_gain = float(annual["annual_pct"].max()) if not annual.empty else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Operaciones", f"{trades:,}")
    c2.metric("Win rate", f"{winrate:.1f}%")
    c3.metric("Ganancia prom. por Mes", f"{avg_monthly_pct:.1f}%")
    c4.metric("Ganancia prom. por Año", f"{avg_annual_pct:.1f}%")
    c5.metric("Máx. ganancia anual", f"{max_annual_gain:.1f}%")

    c6, _ = st.columns([1, 3])
    with c6:
        st.metric("Máx. drawdown", f"{max_dd_pct:.1f}%")

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
                tooltip=[alt.Tooltip("YEAR:O", title="Año"),
                         alt.Tooltip("annual_pct:Q", title="%", format=".1f")],
            )
            .properties(height=340)
        )
        labels = (
            alt.Chart(annual_sorted)
            .mark_text(dy=-6)
            .encode(x="YEAR:O", y="annual_pct:Q",
                    text=alt.Text("annual_pct:Q", format=".0f"))
        )
        st.altair_chart(chart + labels, use_container_width=True)
    else:
        st.info("No fue posible calcular el rendimiento anual. Verifica que haya columna de fecha (`Time`) o de año (`AÑO`).")

    st.divider()

    # --- Resumen mensual ---
    st.subheader("Resumen mensual")
    if "Time" in df_risk.columns and not df_risk.empty:
        tmp = df_risk.sort_values("Time").copy()
        tmp["YM"] = tmp["Time"].dt.to_period("M")
        grp = tmp.groupby("YM")
        total_trades_m = grp.size().rename("Total de trades")
        winrate_m = (
            grp["PROFIT"].apply(lambda x: (pd.to_numeric(x, errors="coerce").fillna(0.0) > 0).mean() * 100)
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
# PESTAÑAS DE ESTRATEGIAS
# =============================

def _safe_load(path: Path):
    try:
        return _load_data_from_path(path)
    except Exception as e:
        st.warning(f"No se pudo cargar {path.name}: {e}")
        return None

data1 = _safe_load(RUTA_ESTRAT_1)
data2 = _safe_load(RUTA_ESTRAT_2)

if data1 is None and data2 is None:
    st.stop()

if data1 is not None and data2 is not None:
    tab1, tab2 = st.tabs(["Estrategia 1", "Estrategia 2"])
    with tab1:
        _render_dashboard(data1, nombre="Estrategia 1")
    with tab2:
        _render_dashboard(data2, nombre="Estrategia 2")
elif data1 is not None:
    _render_dashboard(data1, nombre="Estrategia 1")
else:
    _render_dashboard(data2, nombre="Estrategia 2")
