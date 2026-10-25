# Integrations not implemented (interfaces + stubs only)

None of these is connected or pretended. Each needs an account, cost approval and terms review.

| Integration | Interface in code | Current behaviour | To go live |
|---|---|---|---|
| SMS OTP | `core/security.py: OtpSender` | `DevStubSender` shows the code on screen ("DEV AUTH" banner) | Choose an Indian SMS provider (DLT registration for templates is commonly required: verify), set `auth.mode: provider`, implement the sender, set `PHL_JWT_SECRET` |
| SMS / WhatsApp notifications | `notifications` table + in-app list | In-app notifications only | Provider adapter + opt-in consent + template approval |
| Web push | Browser Notification permission is requested (skippable) | No push server | VAPID keys + push subscription storage + sender |
| Weather forecast | `services/shelf_life.temperatures` (replay) | Historical replay inside the window; monthly means outside (ASSUMPTION) | Forecast API under licensable terms (Open-Meteo paid plan if commercial) |
| Traffic / disruptions | `simulation/scenario.weights` | Modelled multipliers (ASSUMPTION A9) | A licensable traffic source; add as a separate adapter labelled observed |
| Map tiles | `config.yaml: map.tile_url` | OSM public tiles (dev/demo only) | Own tile server or a paid provider; keep attribution |
| data.gov.in mandi prices | `pipelines/fetch_datagov.py` | RESTRICTED without a key | Owner registers a key; set `DATAGOV_API_KEY`; verify the resource id |
| Agmarknet arrivals | `pipelines/fetch_agmarknet.ingest_manual_exports` | Manual CSV exports | Any official API or data-sharing agreement |
