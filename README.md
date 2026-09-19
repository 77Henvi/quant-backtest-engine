# Project Quant — Backtest Platform

ระบบทดสอบกลยุทธ์ Quant ย้อนหลัง (Backtesting) ออกแบบด้วย Clean Architecture
พร้อม deploy บน Google Cloud Platform (Infrastructure-as-Code เขียนไว้สมบูรณ์
ในโฟลเดอร์ `infra/`)

## สารบัญ
- [ภาพรวมสถาปัตยกรรม](#ภาพรวมสถาปัตยกรรม)
- [Tech Stack](#tech-stack)
- [วิธีรันบนเครื่องตัวเอง](#วิธีรันบนเครื่องตัวเอง)
- [API Reference](#api-reference)
- [การทดสอบ (Testing)](#การทดสอบ-testing)
- [โครงสร้างโปรเจกต์](#โครงสร้างโปรเจกต์)
- [แผน Cloud Deployment](#แผน-cloud-deployment)

---

## ภาพรวมสถาปัตยกรรม

ระบบแบ่งเป็น 4 ชั้นตามหลัก **Clean Architecture** โดยแต่ละชั้นมีข้อมูล
รูปแบบเป็นของตัวเอง (ไม่ใช้ class เดียวกันข้ามชั้น) เพื่อให้แก้ไขชั้นหนึ่ง
ไม่กระทบชั้นอื่น:

```
┌─────────────────────────────────────────────┐
│  API layer        (FastAPI routes/schemas)   │  ← HTTP contract
├─────────────────────────────────────────────┤
│  Services layer   (use-case orchestration)   │  ← ผูก domain กับภายนอก
├─────────────────────────────────────────────┤
│  Domain layer      (backtest engine, core)   │  ← business logic ล้วนๆ
│                                               │     ไม่พึ่ง framework ใดๆ
├─────────────────────────────────────────────┤
│  Infrastructure    (database, ORM models)    │  ← รายละเอียดทางเทคนิค
└─────────────────────────────────────────────┘
```

**หลักการสำคัญ**: ลูกศร dependency ชี้ทางเดียว — domain layer ไม่รู้จัก
API หรือ database เลย ทำให้สลับฐานข้อมูล (SQLite → Postgres) หรือสลับ
เฟรมเวิร์ก API ในอนาคตได้โดยไม่ต้องแตะโค้ดคำนวณกลยุทธ์แม้แต่บรรทัดเดียว

## Tech Stack

| ส่วน | เทคโนโลยี | เหตุผลที่เลือก |
|---|---|---|
| Backend Framework | FastAPI | Type-safe, auto-generate API docs, async support |
| Database | PostgreSQL (SQLAlchemy ORM) | มาตรฐานอุตสาหกรรม, SQLite ใช้แทนได้ตอน dev |
| Testing | pytest | มาตรฐานวงการ Python |
| Containerization | Docker + Docker Compose | รันได้เหมือนกันทุกเครื่อง ไม่มีปัญหา "งานที่เครื่องฉัน" |
| Infrastructure-as-Code | Terraform | Provision GCP resources แบบ reproducible |
| Target Cloud | Google Cloud Platform (Cloud Run + Cloud SQL) | Serverless, scale-to-zero, ต้นทุนต่ำ |

## วิธีรันบนเครื่องตัวเอง

### แบบเร็วที่สุด: Docker Compose (แนะนำ)

รันทั้งระบบ (API + PostgreSQL) ด้วยคำสั่งเดียว ไม่ต้องติดตั้ง Python หรือ
Postgres เองเลย:

```bash
cd backend
docker compose up --build
```

รอจนเห็น `Application startup complete` แล้วเปิดเบราว์เซอร์ไปที่:
- `http://localhost:8000/docs` — หน้าทดสอบ API แบบมี UI (Swagger)
- `http://localhost:8000/health` — เช็คว่า server ทำงานอยู่

กด `Ctrl+C` เพื่อหยุด และ `docker compose down` เพื่อลบ container ทิ้ง

### แบบรันตรงด้วย Python (สำหรับ dev/debug)

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest -v             # รันเทสทั้งหมดก่อน
uvicorn app.main:app --reload   # ใช้ SQLite อัตโนมัติ ไม่ต้องตั้งค่าอะไรเพิ่ม
```

## API Reference

| Method | Path | หน้าที่ |
|---|---|---|
| GET | `/health` | เช็คสถานะ server |
| GET | `/backtests/strategies` | รายชื่อกลยุทธ์ที่มีให้เลือก |
| POST | `/backtests` | รัน backtest ใหม่ (ส่ง price data + strategy params) |
| GET | `/backtests/{id}` | ดึงผลการทดสอบย้อนหลังตาม id |
| GET | `/backtests` | ดูรายการ backtest ทั้งหมด |

**กลยุทธ์ที่มีให้ใช้งาน:**
1. `sma_crossover` — ค่าเฉลี่ยเคลื่อนที่ตัดกัน (fast/slow SMA crossover)
2. `fibonacci_retracement` — ซื้อที่แนวรับ Fibonacci 61.8%, ขายทำกำไรที่ 23.6%

**Metrics ที่คำนวณให้ทุกครั้ง**: Total Return %, Sharpe Ratio, Max Drawdown %,
Win Rate %, Profit Factor, จำนวน Trade

ตัวอย่าง request/response แบบเต็มดูได้ที่ `http://localhost:8000/docs`
(FastAPI สร้างเอกสารแบบ interactive ให้อัตโนมัติ)

## การทดสอบ (Testing)

**รวม 60 automated tests ผ่านทั้งหมด**, รันด้วย `python -m pytest -v`

| กลุ่มเทส | จำนวน | ครอบคลุมอะไร |
|---|---|---|
| Domain models | 6 | Bar validation, Trade pnl/return calculation |
| Strategy (SMA) | 6 | Crossover detection, warm-up period, edge cases |
| Strategy (Fibonacci) | 6 | Entry/exit levels, zero-volatility edge case |
| Indicators | 12 | Fibonacci levels, pivot points, support/resistance |
| Backtest engine | 10 | Trade execution, force-close, position sizing |
| Metrics | 9 | Sharpe ratio, drawdown, profit factor, edge cases |
| API layer | 12 | HTTP status codes, validation errors, CRUD flow |

**บั๊กที่เจอและแก้ระหว่างพัฒนา** (ตัวอย่างกระบวนการ QA จริง):
1. Fibonacci strategy เคยยิง BUY signal ผิดเมื่อราคานิ่งสนิท (zero volatility)
   ทำให้ retracement level คำนวณผิดพลาด — แก้โดยข้ามช่วงที่ไม่มีความผันผวน
2. API เคยตอบ `500 Internal Server Error` แทนที่จะเป็น `422 Bad Request`
   เมื่อได้รับข้อมูลราคาที่ผิดพลาด (open อยู่นอกช่วง high/low) — แก้แล้ว
   พร้อม regression test ป้องกันไม่ให้เกิดซ้ำ

## โครงสร้างโปรเจกต์

```
project-quant/
├── backend/
│   ├── app/
│   │   ├── domain/           # Business logic (engine, strategies, metrics)
│   │   ├── services/          # Use-case orchestration
│   │   ├── infrastructure/    # Database, ORM models
│   │   ├── api/               # FastAPI routes + schemas
│   │   └── main.py
│   ├── tests/                 # 60 automated tests
│   ├── scripts/                # ตัวอย่างดึงข้อมูลหุ้นจริง (yfinance)
│   ├── Dockerfile
│   └── docker-compose.yml     # รันทั้งระบบด้วยคำสั่งเดียว
├── infra/                      # Terraform: Cloud Run + Cloud SQL
├── DEPLOY.md                   # คู่มือ deploy ขึ้น GCP แบบ step-by-step
└── README.md                    # ไฟล์นี้
```

## แผน Cloud Deployment

ระบบออกแบบให้พร้อม deploy บน GCP ตั้งแต่แรก:
- **Cloud Run** รัน FastAPI แบบ serverless (scale-to-zero เมื่อไม่มีคนใช้)
- **Cloud SQL** (Postgres) เก็บผลการทดสอบแบบถาวร
- **Terraform** เขียน infrastructure ทั้งหมดเป็นโค้ด (`infra/*.tf`)
  รันซ้ำได้ ลบทิ้งสร้างใหม่ได้ด้วยคำสั่งเดียว

> **หมายเหตุสถานะปัจจุบัน**: Infrastructure-as-Code (Terraform + Dockerfile)
> เขียนและตรวจสอบ syntax เสร็จสมบูรณ์แล้ว การ deploy จริงขึ้น GCP รอเพียง
> การผูกบัตรชำระเงินที่ GCP รองรับ (อยู่ระหว่างดำเนินการ) ระบบทดสอบและ
> สาธิตได้ครบทุกฟังก์ชันผ่าน Docker Compose บนเครื่อง local ซึ่งจำลอง
> สภาพแวดล้อม production (FastAPI + PostgreSQL) ได้เหมือนจริง 100%
> รายละเอียดขั้นตอน deploy แบบเต็มอยู่ใน `DEPLOY.md`
