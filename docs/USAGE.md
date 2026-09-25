# Panduan Penggunaan — btc-dash

Panduan ini menjelaskan cara menjalankan dan menggunakan seluruh bagian dari **btc-dash**, mulai dari Dashboard sampai Django Admin Panel.

> **Screenshot**: Gambar di panduan ini masih placeholder (`docs/images/*.png`). Jalankan aplikasi, ambil screenshot tiap halaman sesuai nama file yang tertulis di bawah setiap gambar, lalu taruh di folder `docs/images/`. Begitu file-nya ada, gambar akan otomatis muncul saat markdown ini dibuka di GitHub/editor manapun.

## Daftar isi

1. [Menjalankan aplikasi](#1-menjalankan-aplikasi)
2. [Dashboard](#2-dashboard)
3. [Backtests](#3-backtests)
4. [Models (Walk-Forward Validation)](#4-models-walk-forward-validation)
5. [AI Agents](#5-ai-agents)
6. [Admin Panel](#6-admin-panel)
7. [Alur kerja end-to-end (via CLI)](#7-alur-kerja-end-to-end-via-cli)
8. [Konfigurasi penting (`.env`)](#8-konfigurasi-penting-env)

---

## 1. Menjalankan aplikasi

Paling gampang pakai script yang sudah disiapkan — otomatis start Postgres check, Redis, Celery worker, Celery beat, dan Django dev server sekaligus:

```bash
cd btc-dash
./scripts/start_dev.sh
```

Tekan `Ctrl+C` untuk mematikan semua service yang script ini start (service yang sudah jalan sebelumnya tidak diganggu).

Kalau mau jalankan manual satu-satu:

```bash
source .venv/bin/activate
python manage.py runserver          # dashboard di http://localhost:8000/
redis-server                        # dibutuhkan Celery
celery -A config worker -l info --pool=solo   # --pool=solo wajib di macOS
celery -A config beat -l info       # penggerak live engine tiap candle close
```

Buka **http://localhost:8000/** di browser setelah server jalan.

![Sidebar navigasi](docs/images/sidebar.png)
*Sidebar kiri ada di semua halaman: Dashboard, Market Data, Strategies, Backtests, Models, AI Agents, Trading, Settings (admin).*

---

## 2. Dashboard

Halaman utama (`/`) berisi semua status sistem dalam satu layar, disusun sebagai kartu-kartu (cards).

![Dashboard penuh](docs/images/dashboard-full.png)
*Tampilan Dashboard secara keseluruhan.*

### 2.1 Infrastructure

![Kartu Infrastructure](docs/images/dashboard-infrastructure.png)

Status koneksi dasar: Database (Postgres), Redis, dan apakah Celery sudah terkonfigurasi. Hijau = OK, merah = bermasalah. Ini pengecekan paling pertama kalau ada yang aneh di halaman lain.

### 2.2 Live Engine

![Kartu Live Engine](docs/images/dashboard-live-engine.png)

Ini kontrol utama sistem trading live (belum ada eksekusi order real — lihat catatan di halaman ini juga).

- **Status ON/OFF** — tombol untuk menyalakan/mematikan live engine. Default-nya **OFF** (safety default).
- **Mode** — `Quant` (strategi + XGBoost saja), `Quant + AI` (tambah 1x review AI per kandidat), `Full Agent` (tambah pipeline 7-agent TradingAgents).
- **Timeframe** — 15m / 1H / 4H.
- **Execution** — `Disabled` atau `Paper` (virtual saja, **tidak pernah** eksekusi order asli — opsi "Live" sengaja tidak pernah ditawarkan di UI ini).
- **Status runtime**: evaluasi terakhir, candle berikutnya yang ditunggu, sinyal terakhir, probabilitas model, jumlah inferensi hari ini.

Setiap kali candle baru close (dicek Celery beat tiap 30 detik), engine otomatis: ambil data → hitung fitur → jalankan strategi baseline → filter XGBoost → (opsional) AI review → simpan sinyal.

### 2.3 AI Reviewer

![Kartu AI Reviewer](docs/images/dashboard-ai-reviewer.png)

Statistik pemakaian AI hari ini: jumlah call vs limit harian, token input/output, cache hits, estimasi biaya, dan keputusan terakhir dari reviewer tunggal maupun dari TradingAgents. AI hanya dipanggil untuk kandidat yang sudah lolos threshold probabilitas XGBoost — **tidak pernah** dipanggil di setiap candle. Tidak ada tombol ON/OFF AI di sini secara sengaja — itu diatur lewat `.env` (`AI_ENABLED`), bukan klik UI, karena menyangkut biaya nyata.

### 2.4 Paper Trading

![Kartu Paper Trading](docs/images/dashboard-paper-trading.png)

Akun trading virtual: balance, equity, realized/unrealized PnL, win rate, profit factor, max drawdown, dan tabel posisi yang sedang terbuka. Ada tombol **Pause/Resume** — saat di-pause, posisi baru tidak akan dibuka, tapi posisi yang sudah terbuka tetap dipantau untuk SL/TP (tidak dibiarkan tanpa manajemen risiko).

### 2.5 Market Data & Features

![Kartu Market Data dan Features](docs/images/dashboard-market-features.png)

Ringkasan data candle BTCUSDT 1H yang tersimpan: rentang tanggal, jumlah candle, candle yang hilang (gap detection), jumlah data funding rate & open interest, serta status feature snapshot (indikator teknikal yang sudah dihitung). Kalau kosong, halaman ini kasih tahu command CLI yang perlu dijalankan.

---

## 3. Backtests

Menu **Backtests** di sidebar (`/backtests/`).

### 3.1 Daftar backtest

![Daftar backtest](docs/images/backtest-list.png)

Semua backtest yang pernah dijalankan: strategi, symbol, timeframe, rentang tanggal, status (queued/running/completed/failed), dan return. Ada tombol **Run new backtest** dan link **Compare strategies**.

### 3.2 Form backtest baru

![Form backtest baru](docs/images/backtest-create.png)

Isi strategi, symbol, timeframe, tanggal mulai/akhir, modal awal, fee, slippage, dan cara sizing posisi. Backtest **tidak** dijalankan langsung saat submit — masuk antrian Celery (status `queued` → `running` → `completed`), supaya request HTTP tidak nge-block.

### 3.3 Detail backtest

![Detail backtest - ringkasan](docs/images/backtest-detail-summary.png)
*Kartu ringkasan: total return, Buy & Hold, profit factor, win rate, max drawdown, Sharpe ratio, total trades.*

![Detail backtest - grafik](docs/images/backtest-detail-charts.png)
*4 grafik: harga BTC dengan penanda entry/exit LONG/SHORT, equity curve, drawdown curve, dan cumulative PnL.*

![Detail backtest - tabel trade](docs/images/backtest-detail-trades.png)
*Riwayat trade lengkap dengan filter (LONG/SHORT, WIN/LOSS, exit reason), plus tabel largest winners & largest losers.*

Halaman ini auto-refresh selama status masih `queued`/`running`, lalu reload otomatis begitu selesai.

### 3.4 Compare strategies

![Compare strategies](docs/images/backtest-compare.png)

Tabel perbandingan semua backtest yang sudah selesai — satu baris per run, kolom Return/PF/Max DD/Sharpe. Untuk perbandingan 4-varian (baseline vs XGBoost vs +AI reviewer vs +TradingAgents) yang lebih detail, pakai command CLI `compare_strategies` (lihat bagian [7](#7-alur-kerja-end-to-end-via-cli)).

---

## 4. Models (Walk-Forward Validation)

Menu **Models** di sidebar (`/walk-forward/`).

### 4.1 Daftar walk-forward run

![Daftar walk-forward](docs/images/walkforward-list.png)

Setiap run walk-forward validation: mode (rolling/expanding), rentang tanggal, jumlah window, dan return agregat out-of-sample.

### 4.2 Detail walk-forward

![Detail walk-forward](docs/images/walkforward-detail.png)

Kartu ringkasan performa **out-of-sample saja** (bukan performa training — jangan sampai tertukar), lalu tabel per-window: periode training, periode testing, jumlah trade, return, profit factor, max drawdown, Sharpe — supaya kelihatan apakah model konsisten kalau di-retrain berkala, bukan cuma cocok di satu periode.

---

## 5. AI Agents

Menu **AI Agents** di sidebar (`/ai-agents/`) — halaman baru untuk melihat detail keputusan dari mode **Full Agent** (TradingAgents).

### 5.1 Daftar run

![Daftar AI Agents run](docs/images/agents-list.png)

Setiap kandidat yang direview lengkap oleh 7-agent pipeline: symbol, timeframe, candle sinyal, sisi baseline, rekomendasi final, token terpakai, estimasi biaya.

### 5.2 Detail trace — di sinilah "kenapa" keputusan trading bisa dilihat

![Detail trace agent - bagian atas](docs/images/agents-detail-top.png)
*Header: sinyal yang direview (symbol, timeframe, waktu candle, sisi baseline, probabilitas XGBoost), rekomendasi final, dan total token/biaya/latency.*

![Detail trace agent - alur pipeline](docs/images/agents-detail-trace.png)
*Alur lengkap 7 agent secara berurutan:*
1. **Technical Analyst** — baca RSI/EMA/ATR/volatility yang sudah dihitung (bukan minta LLM hitung ulang).
2. **Derivatives Analyst** — funding rate, perubahan funding, open interest, perubahan OI.
3. **Sentiment Analyst** — stub lokal (tidak ada sumber berita/sentiment eksternal di project ini, jadi tidak ada API call nyata di sini, gratis).
4. **Bull Researcher** vs **Bear Researcher** — dua argumen berlawanan.
5. **Trader** — sintesis semua di atas jadi satu keputusan LONG/SHORT/WAIT.
6. **Risk Reviewer** — gerbang terakhir; kartu ini diberi **border hijau kalau approve, merah kalau ditolak**. Kalau ditolak, keputusan final otomatis jadi WAIT.

Tiap kartu juga menampilkan token, estimasi biaya, dan latency masing-masing panggilan — jadi kelihatan persis di mana biaya AI-nya terpakai.

---

## 6. Admin Panel

`/admin/` — panel bawaan Django untuk lihat/edit semua data mentah langsung dari database.

### 6.1 Bikin akun admin (sekali saja)

Belum ada akun admin secara default. Buat dulu:

```bash
source .venv/bin/activate
python manage.py createsuperuser
```

Ikuti prompt-nya (username, email, password).

### 6.2 Login

![Halaman login admin](docs/images/admin-login.png)

### 6.3 Halaman utama admin

![Index admin](docs/images/admin-index.png)

Semua model dikelompokkan per app: **Market** (MarketSymbol, Candle, FeatureSnapshot, FundingRate, OpenInterest), **Strategy** (StrategyConfig, SignalCandidate), **Backtest** (BacktestRun, BacktestTrade), **ML** (ModelVersion, WalkForwardRun, WalkForwardWindow), **Trading** (EngineConfig, LiveSignal, PaperAccount, PaperPosition, PaperTrade), **Agents** (AgentDecision, AgentPipelineRun, AgentStepDecision).

Sidebar Dashboard juga langsung link ke bagian **Market Data** (`/admin/market/`), **Strategies** (`/admin/strategy/`), dan **Trading** (`/admin/trading/`) di admin ini.

### 6.4 Contoh: lihat EngineConfig langsung dari admin

![Contoh model admin](docs/images/admin-model-example.png)

Berguna untuk debug cepat — misalnya cek langsung apakah `EngineConfig.enabled` benar-benar `False`, tanpa lewat Dashboard.

---

## 7. Alur kerja end-to-end (via CLI)

Kalau mau isi data dari nol sampai backtest, urutannya:

```bash
source .venv/bin/activate

# 1. Ambil data candle historis dari Binance
python manage.py fetch_historical --symbol BTCUSDT --timeframe 1h --start 2024-01-01 --end 2024-01-05

# 2. Hitung fitur teknikal (RSI, EMA, MACD, ATR, dll — tanpa look-ahead bias)
python manage.py build_features --symbol BTCUSDT --timeframe 1h --start 2024-01-01 --end 2024-01-05

# 3. Jalankan strategi baseline, hasilkan kandidat sinyal LONG/SHORT
python manage.py generate_signals --strategy ema_rsi --symbol BTCUSDT --timeframe 1h --start 2024-01-01 --end 2024-01-05

# 4. Backtest strategi baseline (bisa juga lewat web UI di /backtests/create/)
python manage.py run_backtest --strategy ema_rsi --symbol BTCUSDT --timeframe 1h --start 2024-01-01 --end 2024-01-05 --initial-capital 10000

# 5. Bangun dataset ML dari hasil backtest (WIN/LOSS label, tanpa data leakage)
python manage.py build_ml_dataset --strategy ema_rsi --symbol BTCUSDT --timeframe 1h

# 6. Latih model XGBoost
python manage.py train_quant_model --strategy ema_rsi --symbol BTCUSDT --timeframe 1h

# 7. Evaluasi model (baseline vs filtered by XGBoost probability)
python manage.py evaluate_quant_model --model-version-id <ID>

# 8. Walk-forward validation (retrain berkala, test out-of-sample)
python manage.py run_walk_forward --strategy ema_rsi --symbol BTCUSDT --timeframe 1h --start 2021-01-01 --end 2025-08-31 --mode rolling

# 9. Bandingkan 4 varian: baseline / +XGBoost / +AI reviewer / +TradingAgents
python manage.py compare_strategies --strategy ema_rsi --symbol BTCUSDT --timeframe 1h --start 2024-01-01 --end 2024-01-05
```

Setelah data & model siap, tinggal nyalakan **Live Engine** dari Dashboard untuk mode otomatis (candle-close driven, bukan polling tiap detik).

---

## 8. Konfigurasi penting (`.env`)

File `.env` (bikin dari `.env.example`, jangan pernah commit) berisi:

| Variabel | Fungsi | Default aman |
|---|---|---|
| `DB_*` | Koneksi Postgres | — |
| `REDIS_URL` / `CELERY_*` | Koneksi Redis & Celery | `redis://localhost:6379/0` |
| `ANTHROPIC_API_KEY` | Kunci API Claude (dibutuhkan kalau mau pakai AI reviewer/TradingAgents beneran) | kosong |
| `AI_ENABLED` | Saklar utama semua fitur AI | `False` |
| `AI_MODEL` | Model Claude yang dipakai | `claude-opus-5` |
| `AI_DAILY_CALL_LIMIT` | Batas jumlah call API per hari (shared antara mode Quant+AI dan Full Agent) | `50` |
| `AI_MIN_QUANT_PROBABILITY` | Ambang probabilitas XGBoost minimum sebelum AI direview | `0.65` |
| `AI_MAX_OUTPUT_TOKENS` | Batas token output per call AI | `256` |

**Penting**: `AI_ENABLED=True` + `ANTHROPIC_API_KEY` yang valid berarti sistem akan benar-benar memanggil API Claude (biaya nyata) begitu ada kandidat sinyal yang lolos threshold di mode Quant+AI atau Full Agent — pastikan sadar sebelum menyalakan Live Engine dalam kondisi ini.
