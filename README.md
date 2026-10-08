# VERITAS QUANT — Institutional Backtest & Alpha Verification Platform

**VERITAS QUANT** เป็นแพลตฟอร์มทดสอบกลยุทธ์การลงทุนเชิงปริมาณ (Quantitative Backtesting) และประเมินความเสี่ยงระดับสถาบัน ออกแบบด้วย **Clean Architecture 4 ชั้น** และผสานคณิตศาสตร์การเงินชั้นสูง **Deflated Sharpe Ratio (DSR)** เพื่อแก้ปัญหาสำคัญระดับโลกในวงการ Quant: **"Backtest Overfitting & Selection Bias"** (ภาพลวงตาจากการทดสอบพารามิเตอร์ซ้ำๆ จนได้กำไรปลอม)

---

## สารบัญ
- [จุดเด่นและนวัตกรรมหลัก](#จุดเด่นและนวัตกรรมหลัก)
- [ภาพรวมสถาปัตยกรรม (Clean Architecture)](#ภาพรวมสถาปัตยกรรม-clean-architecture)
- [นวัตกรรมทางคณิตศาสตร์และการประเมินความเสี่ยง](#นวัตกรรมทางคณิตศาสตร์และการประเมินความเสี่ยง)
- [คลังกลยุทธ์การเทรด (Strategy Arsenal)](#คลังกลยุทธ์การเทรด-strategy-arsenal)
- [Interactive Research Terminal (Dashboard)](#interactive-research-terminal-dashboard)
- [Tech Stack](#tech-stack)
- [วิธีติดตั้งและรันระบบ](#วิธีติดตั้งและรันระบบ)
- [API Reference](#api-reference)
- [การทดสอบคุณภาพ (120 Automated Tests)](#การทดสอบคุณภาพ-120-automated-tests)
- [แผน Cloud Deployment (GCP + Terraform)](#แผน-cloud-deployment-gcp--terraform)

---

## จุดเด่นและนวัตกรรมหลัก

1. **Deflated Sharpe Ratio (DSR) & Probabilistic Sharpe Ratio (PSR)**:
   - อ้างอิงงานวิจัยของ *Marcos López de Prado (Journal of Portfolio Management, 2014)*
   - หักลบค่าความฟลุ๊ค (Statistical Haircut) ตามจำนวนครั้งที่ค้นหาพารามิเตอร์ (`num_trials`) และความเบ้/ความโด่งของผลตอบแทน (Skewness & Kurtosis) เพื่อพิสูจน์ว่าผลตอบแทนมาจาก **ฝีมือจริง (True Alpha)**
2. **Realistic Market Microstructure**:
   - จำลอง **Slippage (Basis Points)** และ **Broker Commission** ทั้งขาเข้าและขาออก
   - บันทึกการประเมินมูลค่าพอร์ตแบบ **Mark-to-Market** แท่งต่อแท่ง และคำนวณ **Trade Duration** จริง
3. **Monte Carlo Bootstrap Robustness Engine**:
   - สุ่มจำลองลำดับการเทรด 1,000 เส้นทาง (Resampling with replacement)
   - สร้างกรอบความเชื่อมั่น **Confidence Ribbons (5th, 25th, 50th, 75th, 95th Percentile)** และประเมิน **Probability of Ruin** (โอกาสพอร์ตแตก)
4. **Interactive Research Terminal (Streamlit)**:
   - รองรับโหมด 2 ภาษา (**ไทย / English**)
   - ดึงข้อมูลตลาดจริงสดๆ จาก Yahoo Finance ทั่วโลก (`NVDA`, `AAPL`, `SPY`, `BTC-USD`, `GC=F` ทองคำ, `PTT.BK` หุ้นไทย)
   - โหมด **Crisis Stress Testing** จำลองวิกฤติตลาดหุ้น (2020 COVID Flash Crash, 2022 Bear Market)
   - ระบบสรุปผลสัมฤทธิ์ **Executive Strategy Verdict** และ Export **Strategy Factsheet** ทางการใน 1 คลิก

---

## ภาพรวมสถาปัตยกรรม (Clean Architecture)

ระบบออกแบบตามหลักการ **Clean Architecture** แยกหน้าที่ออกเป็น 4 เลเยอร์อย่างเด็ดขาด โดยที่ Dependency ชี้เข้าสู่ Domain Layer ทางเดียว:

```
┌─────────────────────────────────────────────────────────────┐
│  API Layer        (FastAPI routes / Pydantic schemas)       │  ← HTTP Contract & Validation
├─────────────────────────────────────────────────────────────┤
│  Services Layer   (Use-case orchestration & Strategy build) │  ← เชื่อมโยง Domain กับภายนอก
├─────────────────────────────────────────────────────────────┤
│  Domain Layer      (Pure Python Engine, Math Metrics, Core)  │  ← Business Logic บริสุทธิ์
│                                                             │     ไม่มี Dependency ใดๆ
├─────────────────────────────────────────────────────────────┤
│  Infrastructure   (SQLAlchemy ORM, PostgreSQL / SQLite)     │  ← ฐานข้อมูล & รายละเอียดทางเทคนิค
└─────────────────────────────────────────────────────────────┘
```

---

## นวัตกรรมทางคณิตศาสตร์และการประเมินความเสี่ยง

| หมวดหมู่ | Metrics ที่ระบบคำนวณ | รายละเอียดและความสำคัญ |
|---|---|---|
| **Overfitting Guard** | **Deflated Sharpe Ratio (DSR)** | คำนวณความน่าจะเป็น (0-100%) ที่กลยุทธ์ไม่ใช่ผลลวงตาจากการ Overfit |
| **Statistical Alpha** | **Probabilistic Sharpe (PSR)** | โอกาสทางสถิติที่ Sharpe Ratio ของพอร์ตจะชนะ Benchmark |
| **Risk-Adjusted** | **Sortino Ratio** | วัดผลตอบแทนเทียบกับ Downside Semi-Deviation (ความเสี่ยงเฉพาะขาลง) |
| **Drawdown Risk** | **Calmar Ratio & Omega Ratio** | วัดอัตราส่วนการเติบโตเทียบกับ Max Drawdown และสัดส่วนกำไร/ขาดทุน |
| **Tail Risk** | **Value at Risk (VaR 95%)** | ความเสียหายสูงสุดต่อวันในระดับความเชื่อมั่น 95% |
| **Tail Risk** | **Expected Shortfall (CVaR 95%)** | ความเสียหายเฉลี่ยในกรณีเลวร้ายที่สุด 5% (Tail Risk) |
| **Capital Recovery** | **Max Drawdown Duration** | ระยะเวลาที่พอร์ตติดดอยยาวนานที่สุดก่อนทำ All-Time High ใหม่ (Bars) |
| **Optimal Sizing** | **Kelly Criterion %** | สัดส่วนการจัดสรรเงินทุนที่เหมาะสมที่สุดตามทฤษฎีความน่าจะเป็น |
| **Benchmark Comp** | **Alpha & Beta** | ผลตอบแทนส่วนเพิ่มและความอ่อนไหวเทียบกับ Buy & Hold ของสินทรัพย์อ้างอิง |

---

## คลังกลยุทธ์การเทรด (Strategy Arsenal)

1. `dual_momentum`: ผสาน RSI Pullback เข้ากับ EMA Trend Filter (เทรดเฉพาะเมื่อราคาอยู่เหนือแนวโน้มใหญ่)
2. `macd_crossover`: โมเมนตัมตัดกันของเส้น MACD Line และ Signal Line
3. `bollinger_mean_reversion`: กลยุทธ์ดักซื้อเมื่อราคาหลุดขอบล่าง Bollinger Band แล้วดีดกลับขึ้นมา
4. `fibonacci_retracement`: ดักซื้อที่แนวรับ Fibonacci 61.8% และขายทำกำไรที่ 23.6% หรือ Stop Loss ที่ Swing Low
5. `rsi_mean_reversion`: กลยุทธ์ย่อซื้อเมื่อ RSI ฟื้นตัวจากโซน Oversold (< 30) และขายเมื่อ Overbought (> 70)
6. `sma_crossover`: กลยุทธ์พื้นฐานเส้นค่าเฉลี่ยเคลื่อนที่ Fast/Slow SMA ตัดกัน

---

## วิธีติดตั้งและรันระบบ

### 1. การเปิดใช้งาน Terminal Dashboard (Streamlit Web UI)
```powershell
cd backend
.\venv\Scripts\Activate.ps1
streamlit run dashboard.py
```
> เปิดเบราว์เซอร์ไปที่: **`http://localhost:8501`**

### 2. การเปิดใช้งาน Backend REST API (FastAPI + Swagger Docs)
```powershell
cd backend
.\venv\Scripts\uvicorn.exe app.main:app --reload
```
> - Interactive API Docs: **`http://localhost:8000/docs`**
> - ReDoc: **`http://localhost:8000/redoc`**
> - Health Check: **`http://localhost:8000/health`**

### 3. รันทั้งระบบด้วย Docker Compose
```bash
cd backend
docker compose up --build
```

---

## API Reference

| Method | Path | คำอธิบาย |
|---|---|---|
| `GET` | `/` | ข้อมูลระบบและลิงก์เอกสาร API ทั้งหมด |
| `GET` | `/health` | ตรวจสอบสถานะการทำงานของเซิร์ฟเวอร์ |
| `GET` | `/backtests/strategies` | รายชื่อกลยุทธ์ทั้งหมดที่มีให้เลือกใช้งาน |
| `POST` | `/backtests` | ส่งชุดข้อมูล OHLCV + พารามิเตอร์กลยุทธ์ + ค่า Slippage/Fee เพื่อรัน Backtest |
| `GET` | `/backtests/{id}` | ดึงผลการทดสอบย้อนหลังตาม Job ID |
| `GET` | `/backtests` | ดูรายการและประวัติ Backtest ทั้งหมด |

---

## การทดสอบคุณภาพ (120 Automated Tests)

ระบบมีชุดทดสอบครอบคลุม **120 Automated Tests** (ผ่าน 100%):

```powershell
cd backend
.\venv\Scripts\pytest.exe -v
```

| กลุ่มการทดสอบ | จำนวนข้อ | ขอบเขตที่ตรวจสอบ |
|---|---|---|
| `test_institutional_metrics` | 7 | Sortino, Omega, VaR, CVaR 95%, Alpha/Beta, PSR, Drawdown Duration |
| `test_institutional_strategies` | 5 | MACD Crossover, Bollinger Mean Reversion, Dual Momentum |
| `test_engine_friction` | 3 | Slippage Basis Points, Broker Commission, Monte Carlo Bootstrap |
| `test_deflated_sharpe_ratio` | 9 | Lopez de Prado DSR Formula, Skewness, Kurtosis, Haircut math |
| `test_indicators` & `test_new_indicators` | 32 | Fibonacci Levels, Pivot Points, SMA, EMA, RSI, MACD, Bollinger |
| `test_engine` & `test_models` | 17 | Trade Execution, Force-close, Mark-to-Market, Bar validation |
| `test_strategy` & `test_rsi_strategy` | 17 | Moving Average & RSI edge cases, Zero-volatility handling |
| `test_api` & `test_repository` | 30 | Endpoints HTTP Status Codes, Pydantic validation, SQLite/Postgres persistence |

---

## แผน Cloud Deployment (GCP + Terraform)

โครงสร้างพื้นฐานบน Google Cloud Platform ถูกเขียนเป็นโค้ดไว้สมบูรณ์ในโฟลเดอร์ `infra/`:
- **Cloud Run (FastAPI)**: Serverless Container ประมวลผลคำนวณกลยุทธ์ รองรับการ Scale-to-Zero ($0 เมื่อไม่ได้ใช้งาน)
- **Cloud SQL (PostgreSQL 16)**: เก็บประวัติผลการทดสอบเชิงปริมาณทั้งหมด
- **Artifact Registry**: จัดเก็บ Docker Images
- **Terraform (`infra/main.tf`)**: Infrastructure-as-Code สำหรับสั่งสร้างและทำลาย Resource บน Cloud ได้ด้วยคำสั่งเดียว

---

## โครงสร้างโปรเจกต์

```
Quant Backtest engine/
├── backend/
│   ├── app/
│   │   ├── api/             # FastAPI routers & Pydantic schemas
│   │   ├── domain/          # Core Backtest Engine, Strategies, Math Metrics, Monte Carlo
│   │   ├── infrastructure/  # SQLAlchemy models, Database Session, Repository
│   │   ├── services/        # Backtest Use-case Orchestration
│   │   └── main.py          # FastAPI Application Entrypoint
│   ├── tests/               # 120 Automated Tests (Pytest)
│   ├── scripts/             # สคริปต์ตัวอย่างดึงข้อมูลจริง (yfinance)
│   ├── dashboard.py         # Institutional Streamlit Research Terminal (Bilingual TH/EN)
│   ├── run_dashboard.bat    # ตัวเปิด Dashboard ด่วนบน Windows
│   ├── Dockerfile           # Docker Production Image Definition
│   └── docker-compose.yml   # Multi-Container Setup (API + PostgreSQL)
├── infra/                   # Terraform GCP Cloud Run + Cloud SQL Configs
├── DEPLOY.md                # คู่มือขั้นตอนการ Deploy บน Google Cloud Platform
└── README.md                # เอกสารประกอบโปรเจกต์ฉบับสมบูรณ์
```
