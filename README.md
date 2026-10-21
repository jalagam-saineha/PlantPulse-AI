# PlantPulse AI

**Visual Plant Health & Growth Intelligence System**
*"See the change. Understand the plant."*

A complete, runnable Flask application for plant health monitoring using real
computer vision (OpenCV), Gemini Vision assessment, an optional AI Care
Assistant, growth-video analysis, PDF reporting, and a modern UI.

---

## 1. Project overview

PlantPulse AI lets a user register, add plants, upload leaf photos for
computer-vision and Gemini Vision assessment, submit symptoms to the Care
Assistant, upload growth time-lapse videos for frame-by-frame tracking, compare
analyses over time, generate PDF reports, and manage everything from a
dashboard with real (never fabricated) statistics.

The OpenCV score is a **leaf-based visual score**, calculated from measured
leaf coverage, yellowing, damage, and dark spots. It does not assess stems,
roots, pests, or complete plant health. Gemini image observations are shown
separately from this score; the legacy fixed-class disease classifier is not
run or displayed.

## 2. Features

| Area | What's implemented |
|---|---|
| Authentication | Register, login, logout, forgot/reset password (dev-mode link display + optional SMTP), CSRF protection, hashed passwords |
| Dashboard | Real DB-driven stats (plants, analyses, avg. health, growth scans, alerts), recent plants/analyses, empty states |
| Plant Management | Create/edit/archive/delete, photo upload, search, plant profile page |
| Leaf Analysis | Drag-and-drop upload, real OpenCV HSV segmentation, leaf/yellow/damage/spot measurement, leaf-based visual score with component breakdown, segmented + color-coded health-map images |
| Gemini Vision Assessment | Bounded, resized uploaded image analyzed when Gemini is configured; reports visible evidence, possible causes, uncertainty, and next steps |
| AI Disease Screening | Legacy fixed-class classifier is retained in source/model files but is not run or displayed |
| AI Care Assistant | Symptom-aware, structured recommendations saved to the related analysis; uses an optional configured AI provider or a labelled basic-care fallback |
| Growth Studio | Video upload, background-thread frame extraction + per-frame CV analysis, live status polling, Chart.js growth charts, frame timeline |
| Health Timeline | Unified feed of analyses + growth frames, filterable by plant/type/health |
| Analysis History | Search, filter, sort, pagination |
| Compare | Real before/after diff (absolute + % change) between two analyses |
| Health Insights | Trend sentences generated only when real historical data supports them |
| Disease Library | Dynamic from `labels.json`; shows "no verified information" when `disease_info.json` has no entry — never invents agricultural claims |
| Reports | Real PDF generation (ReportLab) with images, metrics, AI result, historical comparison, disclaimer; view/download/delete |
| Notifications | Created only on real events (analysis/scan completed or failed) |
| Settings | Profile, password change, system information |
| System Status | Live runtime checks (DB, OpenCV, TensorFlow runtime, video processor, ReportLab, storage) |
| Search | Global search across plants, analyses, reports, timeline |
| Dark mode | CSS-variable based, persisted per account |
| Responsive UI | Desktop sidebar, tablet collapse, mobile drawer |
| Errors | Custom 404 / 403 / 413 / 500 pages |

No sidebar link is disabled or a dead end — every feature listed in the
sidebar is implemented and functional.

## 3. Tech stack

- **Backend:** Python 3.11, Flask 3, SQLAlchemy 2, Flask-Login, Flask-WTF (CSRF)
- **Computer vision:** OpenCV, NumPy, Pillow
- **AI (optional):** TensorFlow/Keras — never required for the app to run
- **Reports:** ReportLab
- **Frontend:** Hand-built design system (no Bootstrap), vanilla JS, Chart.js (CDN) for growth charts
- **Database:** SQLite (auto-created, no migrations needed)

### AI Care Assistant setup

No extra Python package is required. To use Gemini, add these settings to the project `.env` file (replace the key placeholder locally; do not commit it):

```dotenv
PLANTPULSE_AI_PROVIDER=gemini
PLANTPULSE_GEMINI_API_KEY=your-Google-AI-Studio-key
PLANTPULSE_GEMINI_MODEL=gemini-3.5-flash-lite
PLANTPULSE_AI_TIMEOUT=20
```

The Gemini key is sent only in the server-side `x-goog-api-key` header. Text care and inline image assessment use Google's REST `models.generateContent` endpoint with structured JSON output. `gemini-3.5-flash-lite` is currently listed by Google as a stable model with image input and structured-output support; access and quota remain subject to your account and rate limits. Uploaded images are validated, resized, and JPEG-compressed before sending; the original remains available to OpenCV. Results separate recorded plant identity from visual evidence and uncertainty. Care Assistant failures retain basic-care guidance and show a safe provider diagnostic. Never commit `.env` or paste its key into logs/issues.

Vision data is stored in an additive `plant_vision_assessments` table linked one-to-one with an analysis; existing analysis columns and rows are unchanged. Flask `db.create_all()` creates this table on startup. The legacy fixed-class classifier is no longer run or shown in user-facing analysis results; stored historical fields and trained model files are retained.

For the OpenAI-compatible provider, set `PLANTPULSE_AI_PROVIDER=openai`, `PLANTPULSE_AI_API_KEY`, and optionally `PLANTPULSE_AI_API_URL` / `PLANTPULSE_AI_MODEL`. Restart Flask after editing `.env`. The `care_recommendations` table is created automatically; existing analysis records remain valid.

### Test Gemini vision in the browser

1. In the project-root `.env`, set `PLANTPULSE_AI_PROVIDER=gemini`, `PLANTPULSE_GEMINI_API_KEY`, `PLANTPULSE_GEMINI_MODEL=gemini-3.5-flash-lite`, and `PLANTPULSE_AI_TIMEOUT=20`.
2. Stop the previous Flask process and restart from the project directory with `..\venv\Scripts\python.exe app.py`. The startup log shows provider/model and whether a key is present, never the key.
3. Sign in, open **Leaf Analysis**, select a plant (record its species if known), upload a clear JPG/PNG/WebP photo, and run analysis.
4. A successful image assessment shows **GEMINI VISION SCREENING**, including recorded plant, observed symptoms, visual evidence, possible causes, care guidance, and uncertainty. Failures show **VISION ASSESSMENT UNAVAILABLE** while preserving available OpenCV measurements.
5. Submit symptoms, watering, and sunlight in the Care Assistant form. Its request receives the saved Gemini assessment. A successful provider response is labeled **AI-GENERATED**; a failed request stays **BASIC-CARE FALLBACK** and displays its safe reason.

Do not commit `.env`. Uploaded image bytes are sent to Google only when Gemini is configured. Results may misidentify plants or symptoms and are screening guidance, not confirmed diagnoses.

## 4. Project structure

```
PlantPulse_AI/
├── app.py                      # Entry point — run this
├── config.py                   # Environment-based configuration
├── seed_demo.py                 # Optional demo data (run manually)
├── requirements.txt             # Core deps (no TensorFlow)
├── requirements-ai.txt          # Optional TensorFlow for AI screening
├── requirements-dev.txt         # pytest
├── .env.example
│
├── app/
│   ├── __init__.py              # App factory, stale-job recovery
│   ├── extensions.py            # db, login_manager, csrf
│   ├── models/                  # User, Plant, Analysis, VideoAnalysis, VideoFrame,
│   │                             # TimelineEvent, Report, Notification, PasswordResetToken
│   ├── routes/                  # One blueprint per feature area
│   ├── services/                # image_processor, video_processor, health_score,
│   │                             # disease_predictor, report_generator, system_status
│   └── utils/                   # icons.py (inline SVGs), uploads.py (validation)
│
├── templates/                   # One folder per feature, base.html = sidebar+header shell
├── static/css/design-system.css # Full design system (light/dark via CSS variables)
├── static/js/app.js
│
├── data/disease_info.json       # Verified disease info only (empty by default)
├── models/                      # Place plant_disease_model.keras + labels.json here
├── instance/                    # plantpulse.db + plantpulse.log (auto-created)
├── uploads/ results/ reports/   # Auto-created on first run
└── tests/                       # automated pytest suite
```

## 5. Installation (Windows 10/11, PowerShell)

```powershell
cd PlantPulse_AI
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
copy .env.example .env
python app.py
```

Open **http://127.0.0.1:5000**.

The SQLite database, upload folders, and log file are all created
automatically on first run — no manual setup needed.

### Legacy fixed-class model tools (inactive in analysis)

The previous fixed-class disease classifier is not invoked by new analyses and
its predictions are not displayed in results, history, timelines, search, or
PDF reports. Existing model/training utilities remain for reference; installing
a model does not enable the current Gemini workflow.

```powershell
python -m pip install -r requirements-ai.txt
```

Then place a compatible model at:

```
models/plant_disease_model.keras   # Keras model, RGB input, softmax output
models/labels.json                 # JSON array of class names, e.g. ["Healthy", "Tomato Early Blight", ...]
```

For reference, the legacy predictor expects input images resized to
224×224 and normalized to [0, 1] before prediction; if your model expects
different preprocessing, adjust `app/services/disease_predictor.py`.
**No trained model is bundled**; use the optional pipeline below to train
one from your locally obtained dataset. Model performance is not claimed
until it has been measured on the held-out test split.

### Train and evaluate the Tomato model

The optional training pipeline uses the Tomato classes from an extracted
PlantVillage dataset. Install the application and AI dependencies, then
install the plotting and evaluation dependencies:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-ai.txt
python -m pip install -r requirements-training.txt
```

The dataset directory must contain one directory per PlantVillage class;
the training scripts select immediate child directories beginning with
`Tomato___` and ignore other crops. For example:

```
data/PlantVillage/
├── Tomato___Bacterial_spot/
│   ├── image1.jpg
│   └── ...
├── Tomato___Early_blight/
├── Tomato___healthy/
└── ...
```

The dataset is not included in Git. Keep it outside the repository or in
`data/PlantVillage/` (which is ignored). To train from another location,
pass `--dataset-dir` or set `PLANTVILLAGE_DIR`.

```powershell
python train_model.py --dataset-dir "data/PlantVillage"
python evaluate_model.py --dataset-dir "data/PlantVillage"
```

Both scripts use the same sorted class order and seed-42, per-class
70%/15%/15% train/validation/test split. Training applies augmentation
only during training, uses ImageNet-pretrained MobileNetV2 and
early-stopping/checkpointing against validation loss. The model accepts
224×224 RGB float32 images in `[0, 1]`, matching the existing predictor;
it rescales internally to `[-1, 1]` for MobileNetV2. Training writes
`models/plant_disease_model.keras`, the ordered `models/labels.json`,
accuracy/loss plots and a best-validation checkpoint under
`training_results/`. Evaluation runs only on the held-out test split and
writes actual test metrics, per-class precision/recall/F1 and a confusion
matrix under `training_results/`. No model training is performed as part
of installing or running the application.

### Optional: Demo data

```powershell
python seed_demo.py
```

Creates one account (`demo@plantpulse.local` / `demo12345`) with two
plants and one real Leaf Analysis (computed on a generated sample image,
not fabricated numbers). Everything is labeled "(Demo)". Safe to re-run —
it won't duplicate the account. Never runs automatically.

## 6. Testing

Run the automated test suite:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

**Automated suite:** run `python -m pytest -q` (the current suite contains 63 tests; rerun after local changes). Provider tests use mocked responses and do not require or expose an API key. Coverage includes:
- Full auth flow: register, login, logout, forgot/reset password (including token reuse rejection), CSRF enforcement, duplicate-email rejection
- Plant CRUD, photo upload, ownership enforcement (403 for other users)
- Leaf Analysis: real OpenCV pipeline verified against a synthetic image with known green/yellow/brown/spot regions — measured percentages matched expectations; corrupt-image and wrong-extension rejection; cross-user access blocked
- Gemini Vision and Care Assistant structured-output success/failure, recorded identity, visible concern, fallback, and safe diagnostic behavior
- Growth Studio: background video processing verified end-to-end on a synthetic growth video — leaf area genuinely increased across frames, matching the simulated growth; status transitions QUEUED→PROCESSING→COMPLETED
- Health Timeline, History, Compare: verified with real, distinct analyses (a genuine before/after health-score diff)
- Disease Library: dynamic labels, verified/unverified distinction, search
- Health Insights: only generates insights when real historical data supports them
- Notifications: created on real events, mark-read flow
- Reports: real PDF bytes generated and verified, view/download/delete, ownership enforcement
- Settings: profile update, password change (old password required, new password works)
- System Status: real runtime checks (not hardcoded)
- Global search across plants/analyses/reports
- `seed_demo.py`: runs, is idempotent, produces real (non-fabricated) demo data
- Clean install from `requirements.txt` alone (no TensorFlow) → automated suite passes
- `python app.py` boots and serves local HTTP responses

**NOT TESTED:**
- Dark mode toggle and sidebar collapse/mobile drawer in an actual browser (verified in code, not click-tested — no browser in the build environment)
- SMTP email delivery (no mail server configured; code path exists but unexercised)
- Behavior under concurrent multi-user load (this is a single-user local demo app, per project scope)
- 403/413 error pages beyond the specific cases covered by tests

**KNOWN LIMITATIONS:**
- Uses `db.create_all()` rather than migrations. If you change a model's
  columns during development, delete `instance/plantpulse.db` and restart.
- Growth video processing uses a background thread (no Celery/Redis), per
  project scope — appropriate for a single-user local/demo deployment,
  not a multi-tenant production server. Only one growth scan processes at
  a time per design; a second upload is rejected with a clear message
  until the first finishes.
- Legacy TensorFlow training and predictor files remain for reference, but
  the fixed-class predictor is inactive in the user-facing analysis flow.
- The Leaf-Based Visual Score is an explicit **screening** heuristic based
  on measured foliage. It does not assess stems, roots, pests, or the whole
  plant and is not a validated agricultural or scientific diagnostic.

## 7. Feature checklist (matches the full spec)

- [x] Authentication (register/login/logout/forgot/reset, hashed passwords, CSRF)
- [x] Dashboard with real metrics
- [x] Plant management (CRUD, photo, archive)
- [x] Plant profile page
- [x] Leaf Analysis upload workspace (drag-and-drop, preview)
- [x] Real OpenCV computer vision pipeline
- [x] Leaf-Based Visual Score with component breakdown and scope explanation
- [x] Visual Health Map (color-coded overlay + legend)
- [x] Gemini Vision image assessment; legacy fixed-class classifier is not run or displayed
- [x] Growth Studio (video upload)
- [x] Background video processing (QUEUED/PROCESSING/COMPLETED/FAILED)
- [x] Growth charts (leaf area, health score, green coverage, damage vs. time)
- [x] Health Timeline (unified, filterable)
- [x] Analysis History (search/filter/sort/paginate)
- [x] Before/After Compare (real diffs)
- [x] Health Insights (real, data-gated)
- [x] Disease Library (dynamic, verified-only info)
- [x] PDF Reports (generate/view/download/delete)
- [x] Notifications (real events only)
- [x] Settings (profile/password/system info)
- [x] System Status (live runtime checks)
- [x] Global Search
- [x] Dark mode (persisted)
- [x] Responsive (desktop/tablet/mobile)
- [x] Error handling (404/403/413/500, friendly pages, no stack traces to user)
- [x] Loading/empty states throughout
- [x] Database persistence (SQLite, auto-created)
- [x] Demo data system (`seed_demo.py`, opt-in only)
- [x] Security (hashing, CSRF, secure filenames, upload validation, ownership checks, env-based secrets)
- [x] Documentation (this file)
- [x] Automated test suite

## 8. Submission checklist

- Run `python -m pytest -q` in the project environment and record the result.
- Start Flask from the project directory, sign in, and demonstrate plant creation, an image analysis, the leaf-only score, Gemini visual evidence or its unavailable state, and the Care Assistant success/fallback label.
- Demonstrate History, Timeline, Growth Studio, PDF report generation, Disease Library, Insights, Search, and mobile-width layout.
- Keep the project `.env`, SQLite database under `instance/`, private uploads, generated reports, runtime logs, virtual environment, caches, and training datasets out of the submission ZIP. Include source, templates, static assets, tests, requirements files, README, and `data/disease_info.json`. Include only non-secret model label/config files if the submission needs them; model weights and generated training artifacts are not required for Gemini analysis.
- `.gitignore` already excludes `.env`, the local database/logs, uploaded media, generated reports/results, model weights, training outputs, and the virtual environment. Check the ZIP contents before submission and do not include screenshots containing account details or API configuration.

## 9. Troubleshooting

- **"No module named cv2" / similar** — run `python -m pip install -r requirements.txt` inside the activated venv.
- **Port already in use** — set `PORT=5001` in `.env` (or stop the other process).
- **"No foliage could be detected"** — use a clearer, closer photo of the leaf against a plainer background.
- **Legacy classifier status is not used by current analyses.** Gemini settings are loaded from the project-root `.env`; restart Flask after editing them. On a Care Assistant fallback, read the safe provider diagnostic on the result page or in `instance/plantpulse.log`. Never share the `.env` file or API key.
- **Forgot-password link isn't emailed** — this is expected in development mode (`MAIL_ENABLED=false`); the link is shown on screen and printed to the terminal/log instead.
