"""
Project Quant — Institutional Terminal & Research Dashboard.

A high-performance quantitative research terminal for backtesting, risk
analytics, and robustness testing with realistic market microstructure.
"""

from datetime import date, datetime, timedelta
import math
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import yfinance as yf

from app.domain import (
    BacktestEngine,
    BacktestResult,
    Bar,
    BollingerMeanReversionStrategy,
    DualMomentumStrategy,
    FibonacciRetracementStrategy,
    MACDCrossoverStrategy,
    RSIMeanReversionStrategy,
    Signal,
    SmaCrossoverStrategy,
    bollinger_bands,
    compute_metrics,
    deflated_sharpe_ratio,
    exponential_moving_average,
    fibonacci_retracement_levels,
    find_swing_range,
    macd,
    probabilistic_sharpe_ratio,
    relative_strength_index,
    run_monte_carlo_simulation,
    simple_moving_average,
)

# -----------------------------------------------------------------------------
# PAGE CONFIG & CUSTOM THEME
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Project Quant | Institutional Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    /* Dark Institutional Theme */
    .stApp {
        background-color: #0b0f19;
        color: #e2e8f0;
    }
    .metric-card {
        background: linear-gradient(135deg, #131b2e 0%, #172038 100%);
        border: 1px solid #2d3748;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.4);
    }
    .metric-title {
        font-size: 0.82rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #94a3b8;
    }
    .metric-value {
        font-size: 1.6rem;
        font-weight: 700;
        color: #38bdf8;
        margin-top: 4px;
    }
    .metric-positive {
        color: #10b981 !important;
    }
    .metric-negative {
        color: #ef4444 !important;
    }
    .badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        background-color: rgba(56, 189, 248, 0.15);
        color: #38bdf8;
        border: 1px solid rgba(56, 189, 248, 0.3);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #131b2e;
        border-radius: 6px 6px 0 0;
        padding: 10px 20px;
        color: #94a3b8;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1e293b !important;
        color: #38bdf8 !important;
        border-bottom: 2px solid #38bdf8;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# DATA PROVIDER UTILITIES
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def fetch_ticker_data(symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """Fetch OHLCV data from Yahoo Finance."""
    try:
        df = yf.download(symbol, start=start_date, end=end_date, progress=False)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]
        df = df.reset_index()
        # Normalize column names
        df.rename(
            columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            },
            inplace=True,
        )
        # Ensure correct datatypes
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float) if "volume" in df.columns else 0.0

        # Guarantee high >= low and open/close within range
        df["high"] = df[["open", "close", "high"]].max(axis=1)
        df["low"] = df[["open", "close", "low"]].min(axis=1)
        return df.sort_values("date").reset_index(drop=True)
    except Exception as e:
        st.error(f"Error fetching data for {symbol}: {e}")
        return None


def generate_synthetic_regime(regime_name: str, n_bars: int = 500) -> pd.DataFrame:
    """Generate realistic synthetic price paths for crisis and regime stress testing."""
    np.random.seed(42)
    dates = [date(2020, 1, 1) + timedelta(days=i) for i in range(n_bars)]
    
    if regime_name == "COVID Flash Crash (2020 Style)":
        # Steady uptrend -> sharp 35% collapse in 25 bars -> sharp V-recovery
        ret = np.random.normal(0.0008, 0.01, n_bars)
        ret[150:180] = np.random.normal(-0.025, 0.03, 30)  # Crash
        ret[180:230] = np.random.normal(0.015, 0.02, 50)   # Recovery
    elif regime_name == "High-Inflation Bear Market (2022 Style)":
        # Relentless downward grind with false relief rallies
        ret = np.random.normal(-0.0007, 0.015, n_bars)
    elif regime_name == "High Volatility Sideways / Chop":
        ret = np.sin(np.linspace(0, 10 * np.pi, n_bars)) * 0.01 + np.random.normal(0, 0.018, n_bars)
    else:  # Steady Bull Market
        ret = np.random.normal(0.0012, 0.009, n_bars)

    prices = 100.0 * np.exp(np.cumsum(ret))
    df = pd.DataFrame({
        "date": dates,
        "open": prices * (1 + np.random.normal(0, 0.002, n_bars)),
        "close": prices,
        "high": prices * (1 + np.abs(np.random.normal(0, 0.008, n_bars))),
        "low": prices * (1 - np.abs(np.random.normal(0, 0.008, n_bars))),
        "volume": np.random.uniform(1e6, 5e6, n_bars),
    })
    df["high"] = df[["open", "close", "high"]].max(axis=1)
    df["low"] = df[["open", "close", "low"]].min(axis=1)
    return df


def dataframe_to_bars(df: pd.DataFrame) -> List[Bar]:
    return [
        Bar(
            date=row["date"],
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0.0)),
        )
        for _, row in df.iterrows()
    ]


# -----------------------------------------------------------------------------
# SIDEBAR: PARAMETERS & CONFIGURATION
# -----------------------------------------------------------------------------
st.sidebar.markdown("## ⚡ **PROJECT QUANT**")
st.sidebar.markdown(
    "<span class='badge'>INSTITUTIONAL ENGINE</span> <span class='badge'>DSR v2.0</span>",
    unsafe_allow_html=True,
)
st.sidebar.markdown("---")

# Data Source Selection
data_mode = st.sidebar.radio(
    "Asset & Data Source",
    ["Yahoo Finance Live", "Crisis & Regime Stress Test", "Upload CSV"],
)

if data_mode == "Yahoo Finance Live":
    ticker = st.sidebar.text_input("Ticker Symbol", value="NVDA", help="e.g. NVDA, AAPL, SPY, BTC-USD, GC=F")
    col1, col2 = st.sidebar.columns(2)
    start_d = col1.date_input("Start Date", value=date.today() - timedelta(days=365 * 3))
    end_d = col2.date_input("End Date", value=date.today())
    df_raw = fetch_ticker_data(ticker.strip().upper(), start_d.isoformat(), end_d.isoformat())
    asset_label = ticker.upper()

elif data_mode == "Crisis & Regime Stress Test":
    regime = st.sidebar.selectbox(
        "Select Market Scenario",
        [
            "COVID Flash Crash (2020 Style)",
            "High-Inflation Bear Market (2022 Style)",
            "High Volatility Sideways / Chop",
            "Steady Bull Market",
        ],
    )
    bars_count = st.sidebar.slider("Historical Bars", 200, 1000, 500)
    df_raw = generate_synthetic_regime(regime, n_bars=bars_count)
    asset_label = f"Synthetic: {regime}"

else:
    uploaded = st.sidebar.file_uploader("Upload OHLCV CSV", type=["csv"])
    if uploaded is not None:
        df_raw = pd.read_csv(uploaded)
        df_raw["date"] = pd.to_datetime(df_raw["date"]).dt.date
        asset_label = "Uploaded Dataset"
    else:
        df_raw = None
        asset_label = "None"

st.sidebar.markdown("---")
st.sidebar.markdown("### 🎯 **Strategy Selection**")
strategy_name = st.sidebar.selectbox(
    "Algorithm",
    [
        "Dual Momentum (RSI + EMA Filter)",
        "MACD Momentum Crossover",
        "Bollinger Mean Reversion",
        "Fibonacci Retracement (61.8% / 23.6%)",
        "RSI Mean Reversion (Wilder's RSI)",
        "Fast / Slow SMA Crossover",
    ],
)

# Dynamic Strategy Hyperparameters
params = {}
if strategy_name == "Dual Momentum (RSI + EMA Filter)":
    params["ema_period"] = st.sidebar.slider("EMA Trend Filter Period", 10, 200, 50)
    params["rsi_period"] = st.sidebar.slider("RSI Period", 5, 30, 14)
    params["rsi_entry"] = st.sidebar.slider("RSI Pullback Entry Threshold", 20.0, 50.0, 35.0)
    params["rsi_exit"] = st.sidebar.slider("RSI Target Exit Threshold", 50.0, 90.0, 65.0)
    strat_obj = DualMomentumStrategy(**params)

elif strategy_name == "MACD Momentum Crossover":
    params["fast_period"] = st.sidebar.slider("Fast Period", 3, 30, 12)
    params["slow_period"] = st.sidebar.slider("Slow Period", 10, 60, 26)
    params["signal_period"] = st.sidebar.slider("Signal Period", 2, 20, 9)
    strat_obj = MACDCrossoverStrategy(**params)

elif strategy_name == "Bollinger Mean Reversion":
    params["period"] = st.sidebar.slider("Bollinger Period", 5, 50, 20)
    params["num_std"] = st.sidebar.slider("Std Dev Multiplier", 1.0, 3.5, 2.0, 0.1)
    params["exit_at_upper"] = st.sidebar.checkbox("Exit at Upper Band (vs Middle)", value=False)
    strat_obj = BollingerMeanReversionStrategy(**params)

elif strategy_name == "Fibonacci Retracement (61.8% / 23.6%)":
    params["lookback"] = st.sidebar.slider("Swing Lookback Window", 10, 100, 20)
    params["entry_level"] = st.sidebar.selectbox("Entry Fibonacci Level", [0.618, 0.786, 0.50], index=0)
    params["exit_level"] = st.sidebar.selectbox("Exit Fibonacci Level", [0.236, 0.382, 0.0], index=0)
    strat_obj = FibonacciRetracementStrategy(**params)

elif strategy_name == "RSI Mean Reversion (Wilder's RSI)":
    params["period"] = st.sidebar.slider("RSI Period", 5, 30, 14)
    params["oversold"] = st.sidebar.slider("Oversold Entry Level", 10.0, 45.0, 30.0)
    params["overbought"] = st.sidebar.slider("Overbought Exit Level", 55.0, 90.0, 70.0)
    params["deep_oversold"] = st.sidebar.slider("Stop-loss Level", 5.0, 25.0, 20.0)
    strat_obj = RSIMeanReversionStrategy(**params)

else:  # SMA Crossover
    params["fast_period"] = st.sidebar.slider("Fast SMA Period", 2, 50, 10)
    params["slow_period"] = st.sidebar.slider("Slow SMA Period", 10, 200, 50)
    strat_obj = SmaCrossoverStrategy(**params)

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ **Execution Microstructure & Friction**")
init_capital = st.sidebar.number_input("Initial Capital ($)", value=100_000.0, step=10_000.0)
pos_fraction = st.sidebar.slider("Position Sizing (Fraction of Capital)", 0.1, 1.0, 1.0, 0.05)
commission_pct = st.sidebar.slider("Broker Commission (%)", 0.0, 0.5, 0.08, 0.01)
slippage_bps = st.sidebar.slider("Execution Slippage (Basis Points)", 0, 50, 5, 1)
num_trials = st.sidebar.number_input(
    "Deflated Sharpe Num Trials (Overfitting Guard)", value=10, min_value=2, max_value=5000,
    help="How many strategy variations you tested. DSR penalizes Sharpe if you searched many parameters!"
)
risk_free_rate = st.sidebar.slider("Risk-Free Rate (%)", 0.0, 10.0, 3.5, 0.5) / 100.0


# -----------------------------------------------------------------------------
# RUN BACKTEST & PROCESS RESULTS
# -----------------------------------------------------------------------------
if df_raw is None or len(df_raw) < 10:
    st.warning("⚠️ Please provide valid historical market data to run the backtest.")
    st.stop()

bars = dataframe_to_bars(df_raw)
engine = BacktestEngine(
    initial_capital=init_capital,
    position_fraction=pos_fraction,
    commission_rate=commission_pct / 100.0,
    slippage_rate=slippage_bps / 10_000.0,
)

result: BacktestResult = engine.run(bars, strat_obj)
metrics: Dict[str, float] = compute_metrics(
    result, num_trials=num_trials, risk_free_rate=risk_free_rate
)


# -----------------------------------------------------------------------------
# HEADER METRIC CARDS
# -----------------------------------------------------------------------------
st.markdown(f"## 📊 Quantitative Terminal — `{asset_label}`")
st.markdown(
    f"**Strategy**: `{strategy_name}` | **Timeframe**: `{bars[0].date}` to `{bars[-1].date}` (`{len(bars)}` trading bars) | **Friction**: `{commission_pct}% comm` + `{slippage_bps} bps slip`"
)

kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)

def fmt_pct(val: float, is_pos_good: bool = True) -> str:
    color_class = "metric-positive" if val > 0 else ("metric-negative" if val < 0 else "")
    if not is_pos_good:
        color_class = "metric-negative" if val > 0 else "metric-positive"
    return f"<div class='metric-value {color_class}'>{val:+.2f}%</div>"

with kpi1:
    st.markdown(
        f"<div class='metric-card'><div class='metric-title'>Total Return</div>{fmt_pct(metrics['total_return_pct'])}</div>",
        unsafe_allow_html=True,
    )
with kpi2:
    st.markdown(
        f"<div class='metric-card'><div class='metric-title'>Sharpe Ratio</div><div class='metric-value'>{metrics['sharpe_ratio']:.2f}</div></div>",
        unsafe_allow_html=True,
    )
with kpi3:
    st.markdown(
        f"<div class='metric-card'><div class='metric-title'>Deflated Sharpe (DSR)</div><div class='metric-value'>{metrics.get('deflated_sharpe_ratio', 0.0):.1%}</div></div>",
        unsafe_allow_html=True,
    )
with kpi4:
    st.markdown(
        f"<div class='metric-card'><div class='metric-title'>Max Drawdown</div>{fmt_pct(-metrics['max_drawdown_pct'], is_pos_good=False)}</div>",
        unsafe_allow_html=True,
    )
with kpi5:
    st.markdown(
        f"<div class='metric-card'><div class='metric-title'>Win Rate</div><div class='metric-value'>{metrics['win_rate_pct']:.1f}% ({int(metrics['num_trades'])} trades)</div></div>",
        unsafe_allow_html=True,
    )
with kpi6:
    st.markdown(
        f"<div class='metric-card'><div class='metric-title'>Profit Factor</div><div class='metric-value'>{metrics['profit_factor']:.2f}</div></div>",
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# MAIN ANALYTICS TABS
# -----------------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📈 Price Action & Signals",
    "🌊 Equity Curve & Underwater DD",
    "🛡️ Institutional Risk Matrix",
    "🎲 Monte Carlo Robustness",
    "📋 Trade Audit Log",
    "📄 Institutional Tear Sheet",
])

# -----------------------------------------------------------------------------
# TAB 1: INTERACTIVE PRICE ACTION & SIGNALS
# -----------------------------------------------------------------------------
with tab1:
    st.markdown("### Interactive Candlestick Chart & Signal Execution")
    
    fig_price = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04,
        row_heights=[0.75, 0.25], subplot_titles=["OHLC Price Action & Trade Markers", "Volume"]
    )
    
    dates_list = [b.date for b in bars]
    closes = [b.close for b in bars]
    
    # Candlestick
    fig_price.add_trace(
        go.Candlestick(
            x=dates_list,
            open=[b.open for b in bars],
            high=[b.high for b in bars],
            low=[b.low for b in bars],
            close=closes,
            name="OHLC",
            increasing_line_color="#10b981",
            decreasing_line_color="#ef4444",
        ),
        row=1, col=1,
    )

    # Strategy-specific overlays
    if "SMA" in strategy_name:
        fast_sma = simple_moving_average(closes, params["fast_period"])
        slow_sma = simple_moving_average(closes, params["slow_period"])
        fig_price.add_trace(go.Scatter(x=dates_list, y=fast_sma, name=f"Fast SMA ({params['fast_period']})", line=dict(color="#38bdf8", width=1.5)), row=1, col=1)
        fig_price.add_trace(go.Scatter(x=dates_list, y=slow_sma, name=f"Slow SMA ({params['slow_period']})", line=dict(color="#f59e0b", width=1.5)), row=1, col=1)
    
    elif "Bollinger" in strategy_name:
        bands = bollinger_bands(bars, params["period"], params["num_std"])
        fig_price.add_trace(go.Scatter(x=dates_list, y=[b.upper for b in bands], name="Upper Band", line=dict(color="rgba(148, 163, 184, 0.5)", dash="dash")), row=1, col=1)
        fig_price.add_trace(go.Scatter(x=dates_list, y=[b.middle for b in bands], name="Middle Band", line=dict(color="#38bdf8", width=1)), row=1, col=1)
        fig_price.add_trace(go.Scatter(x=dates_list, y=[b.lower for b in bands], name="Lower Band", line=dict(color="rgba(148, 163, 184, 0.5)", dash="dash")), row=1, col=1)

    elif "Dual Momentum" in strategy_name:
        ema_vals = exponential_moving_average(closes, params["ema_period"])
        fig_price.add_trace(go.Scatter(x=dates_list, y=ema_vals, name=f"EMA Trend ({params['ema_period']})", line=dict(color="#f59e0b", width=2)), row=1, col=1)

    # Buy / Sell markers
    entry_dates = [t.entry_date for t in result.trades]
    entry_prices = [t.entry_price for t in result.trades]
    exit_dates = [t.exit_date for t in result.trades if t.exit_date is not None]
    exit_prices = [t.exit_price for t in result.trades if t.exit_price is not None]

    fig_price.add_trace(
        go.Scatter(
            x=entry_dates,
            y=entry_prices,
            mode="markers",
            marker=dict(symbol="triangle-up", size=12, color="#10b981", line=dict(width=1, color="#ffffff")),
            name="BUY Entry",
        ),
        row=1, col=1,
    )
    fig_price.add_trace(
        go.Scatter(
            x=exit_dates,
            y=exit_prices,
            mode="markers",
            marker=dict(symbol="triangle-down", size=12, color="#ef4444", line=dict(width=1, color="#ffffff")),
            name="SELL Exit",
        ),
        row=1, col=1,
    )

    # Volume
    fig_price.add_trace(
        go.Bar(x=dates_list, y=[b.volume for b in bars], name="Volume", marker_color="rgba(56, 189, 248, 0.3)"),
        row=2, col=1,
    )

    fig_price.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0b0f19",
        plot_bgcolor="#0f172a",
        margin=dict(l=20, r=20, t=30, b=20),
        height=600,
        xaxis_rangeslider_visible=False,
    )
    st.plotly_chart(fig_price, use_container_width=True)


# -----------------------------------------------------------------------------
# TAB 2: EQUITY CURVE & DRAWDOWN
# -----------------------------------------------------------------------------
with tab2:
    st.markdown("### Cumulative Portfolio Equity vs Buy & Hold Benchmark")
    
    eq_dates = [p.date for p in result.equity_curve]
    eq_vals = [p.equity for p in result.equity_curve]
    bench_vals = [p.equity for p in result.benchmark_equity_curve]

    # Calculate Drawdown series
    peak = eq_vals[0]
    dd_series = []
    for v in eq_vals:
        peak = max(peak, v)
        dd_series.append(((v - peak) / peak) * 100)

    fig_eq = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        row_heights=[0.7, 0.3], subplot_titles=["Portfolio Value ($)", "Underwater Drawdown (%)"]
    )

    # Strategy Equity
    fig_eq.add_trace(
        go.Scatter(x=eq_dates, y=eq_vals, name=f"Strategy: {strategy_name}", line=dict(color="#38bdf8", width=2.5)),
        row=1, col=1,
    )
    # Benchmark Equity
    fig_eq.add_trace(
        go.Scatter(x=eq_dates, y=bench_vals, name=f"Benchmark: Buy & Hold {asset_label}", line=dict(color="#94a3b8", width=1.5, dash="dot")),
        row=1, col=1,
    )
    # Drawdown
    fig_eq.add_trace(
        go.Scatter(
            x=eq_dates, y=dd_series, fill="tozeroy",
            name="Drawdown", line=dict(color="#ef4444", width=1),
            fillcolor="rgba(239, 68, 68, 0.25)",
        ),
        row=2, col=1,
    )

    fig_eq.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0b0f19",
        plot_bgcolor="#0f172a",
        margin=dict(l=20, r=20, t=30, b=20),
        height=550,
    )
    st.plotly_chart(fig_eq, use_container_width=True)


# -----------------------------------------------------------------------------
# TAB 3: INSTITUTIONAL RISK MATRIX
# -----------------------------------------------------------------------------
with tab3:
    st.markdown("### Institutional Risk & Performance Statistics")
    
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        st.markdown("#### 🎯 Return & Compounding")
        st.dataframe(
            pd.DataFrame([
                {"Metric": "Initial Capital", "Value": f"${result.initial_capital:,.2f}"},
                {"Metric": "Final Equity", "Value": f"${result.final_equity:,.2f}"},
                {"Metric": "Total Return (%)", "Value": f"{metrics['total_return_pct']:+.2f}%"},
                {"Metric": "CAGR (Compound Annual Growth)", "Value": f"{metrics['cagr_pct']:+.2f}%"},
                {"Metric": "Benchmark Return (%)", "Value": f"{metrics.get('benchmark_return_pct', 0.0):+.2f}%"},
                {"Metric": "Annualized Volatility (%)", "Value": f"{metrics['annualized_volatility_pct']:.2f}%"},
            ]),
            hide_index=True,
            use_container_width=True,
        )

    with col_b:
        st.markdown("#### 🛡️ Risk-Adjusted Ratios")
        st.dataframe(
            pd.DataFrame([
                {"Metric": "Sharpe Ratio (Ann.)", "Value": f"{metrics['sharpe_ratio']:.2f}"},
                {"Metric": "Sortino Ratio (Downside Vol)", "Value": f"{metrics['sortino_ratio']:.2f}"},
                {"Metric": "Calmar Ratio (CAGR / MaxDD)", "Value": f"{metrics['calmar_ratio']:.2f}"},
                {"Metric": "Omega Ratio", "Value": f"{metrics['omega_ratio']:.2f}"},
                {"Metric": "Alpha vs Benchmark (Ann. %)", "Value": f"{metrics.get('alpha', 0.0):+.2f}%"},
                {"Metric": "Beta vs Benchmark", "Value": f"{metrics.get('beta', 1.0):.2f}"},
            ]),
            hide_index=True,
            use_container_width=True,
        )

    with col_c:
        st.markdown("#### 🔬 Overfitting & Tail Risk")
        st.dataframe(
            pd.DataFrame([
                {"Metric": "Deflated Sharpe Ratio (DSR)", "Value": f"{metrics.get('deflated_sharpe_ratio', 0.0):.1%}"},
                {"Metric": "Probabilistic Sharpe (PSR)", "Value": f"{metrics['probabilistic_sharpe_ratio']:.1%}"},
                {"Metric": "Value at Risk (VaR 95% Daily)", "Value": f"{metrics['var_95_pct']:.2f}%"},
                {"Metric": "Expected Shortfall (CVaR 95%)", "Value": f"{metrics['cvar_95_pct']:.2f}%"},
                {"Metric": "Max Drawdown (%)", "Value": f"{metrics['max_drawdown_pct']:.2f}%"},
                {"Metric": "Max Drawdown Duration", "Value": f"{int(metrics['max_drawdown_duration_bars'])} bars"},
            ]),
            hide_index=True,
            use_container_width=True,
        )

    st.markdown(
        """
        > 💡 **Why Deflated Sharpe Ratio (DSR) Matters**:
        > Standard Sharpe ratio assumes only 1 strategy was ever tried. When an analyst tests hundreds of parameter
        > combinations, the best Sharpe is often pure luck. **DSR (Bailey & Lopez de Prado, 2014)** applies a statistical
        > haircut based on the number of trials (`num_trials`) and non-normal skewness/kurtosis to yield the true probability of genuine alpha.
        """
    )


# -----------------------------------------------------------------------------
# TAB 4: MONTE CARLO SIMULATION
# -----------------------------------------------------------------------------
with tab4:
    st.markdown("### Monte Carlo Bootstrap Simulation (1,000 Resampled Paths)")
    st.markdown(
        "Tests if strategy performance relies on a lucky trade sequence by reshuffling observed trades over 1,000 iterations."
    )

    mc_summary = run_monte_carlo_simulation(result, iterations=1000, seed=42)

    col_mc1, col_mc2, col_mc3, col_mc4 = st.columns(4)
    col_mc1.metric("Median Final Equity", f"${mc_summary.median_final_equity:,.2f}")
    col_mc2.metric("5th Percentile (Worst 5%)", f"${mc_summary.percentile_5th_final_equity:,.2f}")
    col_mc3.metric("95th Percentile (Best 5%)", f"${mc_summary.percentile_95th_final_equity:,.2f}")
    col_mc4.metric("Probability of Ruin (>50% DD)", f"{mc_summary.probability_of_ruin_pct:.1f}%")

    if mc_summary.confidence_ribbon:
        ribbon_df = pd.DataFrame(mc_summary.confidence_ribbon)
        
        fig_mc = go.Figure()
        
        # 95th / 5th percentile fill
        fig_mc.add_trace(go.Scatter(
            x=ribbon_df["step"], y=ribbon_df["p95"],
            line=dict(color="rgba(56, 189, 248, 0.2)", width=0),
            name="95th Percentile",
        ))
        fig_mc.add_trace(go.Scatter(
            x=ribbon_df["step"], y=ribbon_df["p5"],
            fill="tonexty",
            fillcolor="rgba(56, 189, 248, 0.15)",
            line=dict(color="rgba(56, 189, 248, 0.2)", width=0),
            name="5th - 95th Percentile Cone",
        ))
        
        # 25th / 75th percentile fill
        fig_mc.add_trace(go.Scatter(
            x=ribbon_df["step"], y=ribbon_df["p75"],
            line=dict(color="rgba(56, 189, 248, 0.4)", width=0),
            name="75th Percentile",
        ))
        fig_mc.add_trace(go.Scatter(
            x=ribbon_df["step"], y=ribbon_df["p25"],
            fill="tonexty",
            fillcolor="rgba(56, 189, 248, 0.3)",
            line=dict(color="rgba(56, 189, 248, 0.4)", width=0),
            name="25th - 75th Percentile Core",
        ))

        # Median
        fig_mc.add_trace(go.Scatter(
            x=ribbon_df["step"], y=ribbon_df["p50"],
            line=dict(color="#38bdf8", width=2.5),
            name="Median Simulated Path",
        ))

        fig_mc.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0b0f19",
            plot_bgcolor="#0f172a",
            title="Monte Carlo Equity Envelope Across Trade Steps",
            xaxis_title="Trade Count",
            yaxis_title="Portfolio Equity ($)",
            height=480,
            margin=dict(l=20, r=20, t=40, b=20),
        )
        st.plotly_chart(fig_mc, use_container_width=True)


# -----------------------------------------------------------------------------
# TAB 5: TRADE AUDIT LOG
# -----------------------------------------------------------------------------
with tab5:
    st.markdown("### Execution Trade Log & Return Distribution")
    
    if result.trades:
        trades_data = [
            {
                "Trade #": i + 1,
                "Entry Date": t.entry_date,
                "Entry Price": f"${t.entry_price:,.2f}",
                "Exit Date": t.exit_date,
                "Exit Price": f"${t.exit_price:,.2f}" if t.exit_price else "Open",
                "Quantity": f"{t.quantity:,.4f}",
                "Net PnL ($)": t.pnl,
                "Return (%)": t.return_pct * 100,
                "Commission ($)": t.commission,
                "Duration (Bars)": t.duration_bars,
            }
            for i, t in enumerate(result.trades)
        ]
        trades_df = pd.DataFrame(trades_data)

        col_t1, col_t2 = st.columns([0.65, 0.35])

        with col_t1:
            st.dataframe(
                trades_df.style.format({
                    "Net PnL ($)": "${:,.2f}",
                    "Return (%)": "{:+.2f}%",
                    "Commission ($)": "${:,.2f}",
                }),
                height=400,
                use_container_width=True,
            )

        with col_t2:
            fig_hist = go.Figure()
            fig_hist.add_trace(
                go.Histogram(
                    x=[t.return_pct * 100 for t in result.trades],
                    nbinsx=20,
                    marker_color="#38bdf8",
                )
            )
            fig_hist.update_layout(
                template="plotly_dark",
                paper_bgcolor="#0b0f19",
                plot_bgcolor="#0f172a",
                title="Trade Return Distribution (%)",
                xaxis_title="Return (%)",
                yaxis_title="Frequency",
                height=400,
                margin=dict(l=20, r=20, t=40, b=20),
            )
            st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info("No trades were generated by the strategy on this dataset.")


# -----------------------------------------------------------------------------
# TAB 6: TEAR SHEET EXPORT
# -----------------------------------------------------------------------------
with tab6:
    st.markdown("### Institutional Quant Factsheet / Tear Sheet")
    st.markdown("One-click summary report ready for presentation and institutional investor review.")

    tearsheet_html = f"""
    <div style="background-color:#0f172a; color:#f8fafc; padding:24px; border-radius:12px; font-family:sans-serif; border:1px solid #334155;">
        <h2 style="color:#38bdf8; margin-top:0;">PROJECT QUANT — STRATEGY FACTSHEET</h2>
        <p><strong>Asset:</strong> {asset_label} | <strong>Strategy:</strong> {strategy_name} | <strong>Period:</strong> {bars[0].date} to {bars[-1].date}</p>
        <hr style="border-color:#334155;">
        <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:16px; margin:20px 0;">
            <div style="background:#1e293b; padding:12px 16px; border-radius:8px;">
                <div style="font-size:12px; color:#94a3b8;">TOTAL RETURN</div>
                <div style="font-size:22px; font-weight:bold; color:#10b981;">{metrics['total_return_pct']:+.2f}%</div>
            </div>
            <div style="background:#1e293b; padding:12px 16px; border-radius:8px;">
                <div style="font-size:12px; color:#94a3b8;">ANNUALIZED SHARPE</div>
                <div style="font-size:22px; font-weight:bold; color:#38bdf8;">{metrics['sharpe_ratio']:.2f}</div>
            </div>
            <div style="background:#1e293b; padding:12px 16px; border-radius:8px;">
                <div style="font-size:12px; color:#94a3b8;">DEFLATED SHARPE (DSR)</div>
                <div style="font-size:22px; font-weight:bold; color:#f59e0b;">{metrics.get('deflated_sharpe_ratio', 0.0):.1%}</div>
            </div>
            <div style="background:#1e293b; padding:12px 16px; border-radius:8px;">
                <div style="font-size:12px; color:#94a3b8;">MAX DRAWDOWN</div>
                <div style="font-size:22px; font-weight:bold; color:#ef4444;">{metrics['max_drawdown_pct']:.2f}%</div>
            </div>
            <div style="background:#1e293b; padding:12px 16px; border-radius:8px;">
                <div style="font-size:12px; color:#94a3b8;">WIN RATE / TRADES</div>
                <div style="font-size:22px; font-weight:bold; color:#e2e8f0;">{metrics['win_rate_pct']:.1f}% ({int(metrics['num_trades'])} trades)</div>
            </div>
            <div style="background:#1e293b; padding:12px 16px; border-radius:8px;">
                <div style="font-size:12px; color:#94a3b8;">VALUE AT RISK (VaR 95%)</div>
                <div style="font-size:22px; font-weight:bold; color:#e2e8f0;">{metrics['var_95_pct']:.2f}%</div>
            </div>
        </div>
        <p style="font-size:12px; color:#64748b;">Engine: Clean Architecture (Domain / Service / API / Infra) | Mathematical Overfitting Guard: Marcos López de Prado (2014) DSR</p>
    </div>
    """
    st.markdown(tearsheet_html, unsafe_allow_html=True)
