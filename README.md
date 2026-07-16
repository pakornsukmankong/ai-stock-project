# AI Stock Alert Platform

AI-assisted stock alert platform that sends LINE notifications when potential buy opportunities are detected.

## Architecture

```
Next.js Frontend → FastAPI Backend → Scheduler (5 min)
                                        ↓
                                   Market Data Fetch
                                        ↓
                                   Indicator Engine (RSI, MACD, EMA, Volume)
                                        ↓
                                   Signal Engine (Rule-based)
                                        ↓
                                   If BUY signal:
                                     → AI Analysis (OpenAI)
                                     → LINE Push Notification
                                     → Save Alert History
```

## Tech Stack

- **Frontend**: Next.js 15, TypeScript, TailwindCSS, shadcn/ui
- **Backend**: FastAPI, Pydantic, pandas, pandas-ta
- **Database**: Supabase PostgreSQL + Auth
- **AI**: OpenAI GPT-4o-mini
- **Notifications**: LINE Messaging API
- **Deployment**: Vercel (frontend) + Railway/Render (backend)

## Getting Started

### Prerequisites

- Node.js 20+
- Python 3.12+
- Supabase project
- OpenAI API key
- LINE Official Account

### Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
uvicorn app.main:app --reload
```

### Frontend Setup

```bash
cd frontend
npm install
cp .env.example .env.local
# Edit .env.local with your credentials
npm run dev
```

### Database Setup

Run the SQL migration in your Supabase SQL editor:
```
supabase/migrations/001_initial_schema.sql
```

## Environment Variables Guide

### Backend (`backend/.env`)

| Variable | วิธีได้มา |
|----------|-----------|
| `SUPABASE_URL` | ไปที่ [Supabase Dashboard](https://supabase.com/dashboard) → เลือก Project → Settings → API → Project URL |
| `SUPABASE_KEY` | Supabase Dashboard → Settings → API → `anon` `public` key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase Dashboard → Settings → API → `service_role` key (ใช้ฝั่ง backend เท่านั้น ห้ามเปิดเผย) |
| `OPENAI_API_KEY` | ไปที่ [OpenAI Platform](https://platform.openai.com/api-keys) → Create new secret key |
| `LINE_CHANNEL_ACCESS_TOKEN` | ไปที่ [LINE Developers Console](https://developers.line.biz/console/) → สร้าง Provider → สร้าง Messaging API Channel → Tab "Messaging API" → Issue Channel access token |
| `LINE_CHANNEL_SECRET` | LINE Developers Console → Channel ที่สร้าง → Tab "Basic settings" → Channel secret |
| `MARKET_DATA_API_KEY` | (Optional) ระบบใช้ Yahoo Finance API ฟรีเป็น default ถ้าต้องการ premium data ใช้ [Alpha Vantage](https://www.alphavantage.co/support/#api-key) หรือ [Polygon.io](https://polygon.io/) |
| `APP_ENV` | ตั้งเป็น `development` หรือ `production` |
| `ANALYSIS_INTERVAL_MINUTES` | ความถี่ในการรัน analysis (default: `5`) |
| `CACHE_TTL_MINUTES` | ระยะเวลา cache AI analysis (default: `30`) |

### Frontend (`frontend/.env.local`)

| Variable | วิธีได้มา |
|----------|-----------|
| `NEXT_PUBLIC_SUPABASE_URL` | เหมือน `SUPABASE_URL` ด้านบน |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | เหมือน `SUPABASE_KEY` ด้านบน (ใช้ anon key เท่านั้น) |
| `NEXT_PUBLIC_API_URL` | URL ของ backend เช่น `http://localhost:8000` (dev) หรือ URL จาก Railway/Render (production) |

---

### ขั้นตอนละเอียด

#### 1. Supabase

1. ไปที่ https://supabase.com → Sign up / Login
2. กด **New Project** → ตั้งชื่อ + password + เลือก region
3. รอ project สร้างเสร็จ
4. ไปที่ **Settings** → **API**:
   - **Project URL** = `SUPABASE_URL`
   - **anon public** key = `SUPABASE_KEY` / `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - **service_role** key = `SUPABASE_SERVICE_ROLE_KEY`
5. ไปที่ **SQL Editor** → รัน `supabase/migrations/001_initial_schema.sql`

#### 2. OpenAI

1. ไปที่ https://platform.openai.com → Sign up / Login
2. ไปที่ **API Keys** → **Create new secret key**
3. Copy key → ใส่ใน `OPENAI_API_KEY`
4. ตรวจสอบว่ามี credit / billing ตั้งค่าแล้ว (ค่าเริ่มต้นคือ `gpt-5.6-luna` ปรับได้ด้วย `OPENAI_MODEL`)

#### 3. LINE Messaging API

1. ไปที่ https://developers.line.biz/console/
2. กด **Create** → สร้าง **Provider** ใหม่
3. ภายใน Provider → กด **Create a Messaging API channel**
4. กรอกข้อมูล channel (ชื่อ, description, category)
5. หลังสร้างเสร็จ:
   - Tab **Basic settings** → **Channel secret** = `LINE_CHANNEL_SECRET`
   - Tab **Messaging API** → กด **Issue** ที่ Channel access token = `LINE_CHANNEL_ACCESS_TOKEN`
6. ผู้ใช้ต้อง Add friend กับ Official Account นี้ เพื่อให้ระบบส่ง push message ได้
7. เมื่อผู้ใช้ Add friend → ระบบจะได้ `line_user_id` ผ่าน Webhook (หรือให้ user กรอกเองในหน้า Settings)

#### 4. วิธีหา LINE User ID ของผู้ใช้

- ตั้ง Webhook URL ใน LINE Developers Console ชี้ไปที่ backend
- เมื่อ user ส่งข้อความหา bot → Webhook จะส่ง `userId` มาให้
- หรือใช้ [LINE Bot Tester](https://developers.line.biz/console/) ดู userId ได้

---

## Key Features

- **Smart Filtering**: Rule-based signal engine prevents unnecessary AI calls
- **Analysis Cache**: Same stock analysis reused for multiple users (TTL: 30 min)
- **Token Efficient**: Compact structured data sent to AI, not raw OHLCV
- **Real-time Alerts**: LINE push notifications with confidence levels
