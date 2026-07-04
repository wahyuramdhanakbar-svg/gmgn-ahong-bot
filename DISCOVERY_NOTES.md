# DISCOVERY NOTES — GMGN CLI

> Hasil discovery 4 Juli 2026 untuk work order perbaikan `gmgn-ahong-bot`.

---

## 1a. Token Price — Perintah & Format

**Command:** `gmgn-cli token info --chain <chain> --address <addr> --raw`

**Output key fields:**
| Field | Format | Contoh |
|---|---|---|
| `price.price` | SOL (float string) | `"0.0000023139581"` |
| `liquidity` | USD (float string) | `"4964.79"` |
| `creation_timestamp` | Unix seconds | `1783134238` |
| `open_timestamp` | Unix seconds (0 jika tidak ada) | `0` |
| `decimals` | Integer | `6` |

**Kesimpulan:** Harga dari `token info` dalam **SOL**. Tidak ada `price_usd` langsung — perlu konversi jika ingin USD. Untuk watchdog SL, cukup bandingkan SOL price langsung.

**Alternative dari trending/trenches payload:**
| Field | Format | Keterangan |
|---|---|---|
| `price` | SOL (float) | Harga saat ini |
| `market_cap` | USD | Market cap — sudah ada di `multi_scan()` |
| `liquidity` | USD | Likuiditas — sudah ada di `multi_scan()` |
| `open_timestamp` | Unix seconds | Token dibuat |
| `creation_timestamp` | Unix seconds | Token dibuat |

---

## 1b. Activities Wallet dengan PnL per-tx

**Command:** `gmgn-cli portfolio activity --chain <chain> --wallet <addr> --limit <n> [--cursor <c>] [--type buy/sell] --raw`

**Field untuk PnL per-trade:**
| Field | Keterangan |
|---|---|
| `event_type` | `"buy"` atau `"sell"` |
| `token.address` | Contract address token |
| `token.symbol` | Symbol |
| `buy_cost_usd` | Cost basis USD (hanya ada di sell) |
| `cost_usd` | Sold value USD (hanya ada di sell) |
| `gas_usd` | Gas fee USD |
| `dex_usd` | DEX fee USD |
| `priority_fee` | Priority fee SOL |
| `tip_fee` | Tip fee SOL |
| `tx_hash` | Transaction hash |
| `quote_amount` | Amount SOL |
| `token_amount` | Amount token |

**Cara hitung PnL per-sell:** `pnl_usd = cost_usd - buy_cost_usd` (kedua field ada di event sell)

**Pagination:** Ada `next` cursor — dapet 310 tx dari 16 halaman dengan `--limit 100`.

---

## 1c. Sell dengan Percentage

**Ditemukan flag:** `--percent <pct>` pada `swap` command!

**Dokumentasi:** "Input amount as a percentage, e.g. 50 = 50%, 1 = 1%; only valid when input_token is NOT a currency"

**Kesimpulan:** Untuk sell token (input_token = token address, bukan SOL/WSOL), bisa pake `--percent 100` untuk menjual **seluruh balance**. Tidak perlu ribet dengan decimals atau raw amount.

**Format command:**
```bash
gmgn-cli swap --chain sol --from <WALLET> \
  --input-token <TOKEN_ADDR> --output-token So11111111111111111111111111111111111111112 \
  --percent 100 \
  --slippage 8 \
  --priority-fee <fee> --tip-fee <fee> \
  --raw
```

---

## 1d. Priority Fee — Audit

**Swap options untuk Solana:**
| Flag | Min | Keterangan |
|---|---|---|
| `--priority-fee <sol>` | 0.00001 SOL | Priority fee |
| `--tip-fee <amount>` | 0.00001 SOL | Jito tip |

**Tidak ada auto/max override untuk Solana** — `--auto-fee` dan `--max-priority-fee-per-gas` hanya untuk ETH/BSC/BASE.

**Observasi data real:**
- Buy (bot langsung): priority_fee ~0.0001 SOL (2x config 0.00005 — mungkin ada minimum rounding atau CLi enforce)
- Sell (GMGN TP/SL otomatis): priority_fee 0.001–0.010 SOL (10-100× config!) — ini karena **GMGN sistem** yang eksekusi, bukan bot config

**Kesimpulan:**
1. Priority fee config di `buy_token()` mungkin diabaikan/minimum enforced oleh GMGN
2. Sell fees tinggi karena GMGN auto-execute TP/SL — tidak ada kontrol dari bot
3. Round-trip fee ~$0.57/trade (gas+dex) yang membunuh profit adalah dari sistem TP/SL, bukan dari buy
4. Satu-satunya yang bisa dikontrol: priority fee dan tip fee di `buy_token()` dan watchdog `sell_token()`

**Rekomendasi:** 
- Priority fee untuk buy: pertahankan 0.00005–0.0001 SOL (cukup untuk pump.fun)
- Untuk watchdog sell (force-sell): pakai priority fee yang sama
- TP/SL fee tinggi adalah biaya yang TIDAK BISA DIHINDARI — harus diimbangi dengan win rate lebih tinggi

---

## 1e. Catatan Tambahan

**Trending payload price:** Dalam SOL (float). Contoh: `"price": 5.66167e-05` = 0.0000566167 SOL.

**Token info price:** Dalam SOL (string). Contoh: `"price": "0.0000023139581"`.

**Mapping field harga untuk entry & watchdog:**
- Saat buy (dari trending/trenches): `price` dari payload adalah harga SOL
- Saat watchdog (dari token info): `price.price` dari response adalah harga SOL
- SL check: `current_price / entry_price <= 0.78` (scale 78)