
╔══════════════════════════════════════════════════════════════════════════════╗
║         X EDUCATION — AI REVENUE INTELLIGENCE PLATFORM v2.0                ║
║                  Complete Windows Setup Manual                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

Read every word. Setup takes 25 minutes first time. Every time after: 3 minutes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 0 — HOW THE SYSTEM WORKS (READ BEFORE ANYTHING ELSE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You have FOUR servers running simultaneously:

  [1] user-backend     → FastAPI  → port 8000  (ML, auth, cart, behaviour)
  [2] user-frontend    → React    → port 5173  (X Education website)
  [3] marketing-backend→ FastAPI  → port 8001  (campaigns, email, AI improve)
  [4] marketing-frontend→ React   → port 5174  (Marketing team dashboard)

The flow:
  User signs up → OTP sent to Gmail → verified → browses site
  → Behaviour tracked silently (visits, time, video, brochure, chat, pricing, testimonials)
  → Adds course to cart → goes inactive for 1 hour
  → Background job detects → ML score computed → GenAI email generated → sent via Gmail
  → Marketing team sees lead on port 5174 → edits email → sends → coupon issued

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 1 — FOLDER STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  xedu_v2/
  ├── user-backend/
  │   ├── ml_models/          ← PUT YOUR 6 .pkl FILES HERE
  │   │   ├── hgb_model_calibrated.pkl
  │   │   ├── preprocessor.pkl
  │   │   ├── kmeans.pkl
  │   │   ├── pca.pkl
  │   │   ├── scaler_cluster.pkl
  │   │   └── model_config.pkl
  │   ├── main.py
  │   ├── auth.py
  │   ├── database.py
  │   ├── predict.py
  │   ├── scheduler.py
  │   ├── genai_mock.py
  │   ├── email_service.py
  │   ├── recommendations.py
  │   ├── requirements.txt
  │   └── .env              ← CREATE THIS (copy from .env.example)
  │
  ├── user-frontend/
  │   ├── src/
  │   ├── package.json
  │   └── vite.config.js
  │
  ├── marketing-backend/
  │   ├── main.py
  │   ├── genai_mock.py
  │   ├── email_service.py
  │   ├── requirements.txt
  │   └── .env              ← CREATE THIS (copy from .env.example)
  │
  └── marketing-frontend/
      ├── src/
      ├── package.json
      └── vite.config.js

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 2 — PREREQUISITES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. Python 3.11 or 3.12
     → https://www.python.org/downloads/
     → TICK "Add Python to PATH" during install
     → Verify: python --version

  2. Node.js 20+ (LTS)
     → https://nodejs.org/
     → Verify: node --version

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 3 — FIRST-TIME SETUP (run once)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1 — Copy your .pkl files
  Copy all 6 .pkl files to: xedu_v2\user-backend\ml_models\
  Exact filenames required:
    hgb_model_calibrated.pkl
    preprocessor.pkl
    kmeans.pkl
    pca.pkl
    scaler_cluster.pkl
    model_config.pkl

STEP 2 — Create user-backend .env
  In xedu_v2\user-backend\, create a file named: .env
  Contents:
    GMAIL_USER=yourname@gmail.com
    GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
    JWT_SECRET=any_long_random_string_here_change_this
    OTP_EXPIRY_MINUTES=10
    CART_CHECK_INTERVAL_MINUTES=5
    CART_ABANDON_THRESHOLD_MINUTES=60

  HOW TO GET GMAIL APP PASSWORD:
    1. Go to myaccount.google.com → Security
    2. Enable 2-Step Verification
    3. Search "App Passwords" → Select Mail → Generate
    4. Copy 16-character code → paste as GMAIL_APP_PASSWORD

STEP 3 — Create marketing-backend .env
  In xedu_v2\marketing-backend\, create a file named: .env
  Contents:
    GMAIL_USER=yourname@gmail.com
    GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
    MARKETING_EMAIL=admin@xeducation.in
    MARKETING_PASSWORD=marketing_admin_2025
    JWT_SECRET=any_different_long_random_string
    USER_DB_PATH=../user-backend/xeducation_user.db

  NOTE: MARKETING_EMAIL and MARKETING_PASSWORD are what the
        marketing team uses to log in to port 5174.
        Change these to anything you want.

STEP 4 — Install user-backend Python packages
  Open Command Prompt:
    cd xedu_v2\user-backend
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt

STEP 5 — Install marketing-backend Python packages
  Open a NEW Command Prompt:
    cd xedu_v2\marketing-backend
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt

STEP 6 — Install user-frontend packages
  Open a NEW Command Prompt:
    cd xedu_v2\user-frontend
    npm install

STEP 7 — Install marketing-frontend packages
  Open a NEW Command Prompt:
    cd xedu_v2\marketing-frontend
    npm install

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 4 — RUNNING THE PROJECT (4 terminals, every time)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  TERMINAL 1 — User Backend
    cd xedu_v2\user-backend
    venv\Scripts\activate
    uvicorn main:app --reload --port 8000

    Expected output:
      [DB] Initialised → ...xeducation_user.db
      [ML] All 6 artefacts loaded.
      [SCHEDULER] Background jobs started
      [API] X Education User Backend running on port 8000

  TERMINAL 2 — Marketing Backend
    cd xedu_v2\marketing-backend
    venv\Scripts\activate
    uvicorn main:app --reload --port 8001

    Expected output:
      [MKT-DB] Initialised → ...xeducation_marketing.db
      [API] Marketing Backend running on port 8001

  TERMINAL 3 — User Frontend
    cd xedu_v2\user-frontend
    npm run dev
    → Open: http://localhost:5173

  TERMINAL 4 — Marketing Frontend
    cd xedu_v2\marketing-frontend
    npm run dev
    → Open: http://localhost:5174

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 5 — VIVA DEMO SCRIPT (rehearse this twice)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [1] Open http://localhost:5173 in Chrome

  [2] Click any course → it shows only the card + price (no login needed)
      → Explain: "Free browsing, like Amazon product pages"

  [3] Click "View Curriculum" → login gate appears
      → Explain: "Gated content forces registration, capturing genuine leads"

  [4] Sign up with your email → OTP arrives → enter OTP
      → Explain: "Gmail OTP verifies email is real — no fake accounts"

  [5] Complete Profile popup → fill Occupation, Specialization, Age, City
      → Explain: "These 4 fields feed directly into our ML model as features"

  [6] Browse the Data Science course page
      → Click "Watch Course Overview" (video tracker fires)
      → Scroll to Pricing section (pricing tracker fires)
      → Click "Download Brochure" (brochure tracker fires)
      → Open chat widget (chat tracker fires)
      → Explain: "All 14 ML features being captured silently — user sees nothing"

  [7] Add course to Cart → Add another to Wishlist
      → Explain: "Cart = purchase intent signal. Wishlist = interest without commitment."

  [8] Submit an Enquiry Form for one course
      → Explain: "Form filler = minimum Marketing Campaign tier — guaranteed interested lead"
      → Show the Thank You page with Lead Score donut

  [9] Open http://localhost:5174 (marketing dashboard)
      → Login with marketing credentials from your .env
      → Show stats cards and charts
      → Find the lead you just created
      → Click "View Detail" → show full profile, ML score, persona
      → Show the auto-generated email + WhatsApp message
      → Click "Improve with AI" → show improved version
      → Send the email → confirm it arrives in inbox
      → Generate a coupon for this user
      → Explain: "Coupon goes via email — user enters it at checkout, not given automatically.
                  This is strategic — we build the business, not give away revenue."

  [10] To demo cart abandonment:
      → In the SQLite DB, manually set added_at to 2 hours ago for a cart item:
        Open DB Browser for SQLite → xeducation_user.db → cart table
        Change added_at to: 2024-01-01 00:00:00
      → Wait for scheduler (or restart backend to trigger immediately)
      → Show the email that arrives + the lead record created

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 6 — COMMON ERRORS AND FIXES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ERROR: "[ML] WARNING: Could not load artefacts"
  FIX:   Copy all 6 .pkl files to user-backend\ml_models\
         Backend still works in mock mode (random scores) without them.

  ERROR: "Gmail authentication failed"
  FIX:   You used your Gmail password, not the App Password.
         Generate an App Password: myaccount.google.com → Security → App Passwords

  ERROR: "Address already in use" on port 8000
  FIX:   netstat -ano | findstr :8000 → taskkill /PID <number> /F

  ERROR: "MODULE NOT FOUND" in frontend
  FIX:   npm install (inside the frontend folder)

  ERROR: Marketing backend "cannot open database"
  FIX:   Start user-backend FIRST (it creates xeducation_user.db)
         Then start marketing-backend

  ERROR: OTP not arriving
  FIX:   Check GMAIL_USER and GMAIL_APP_PASSWORD in .env
         Check spam folder. Gmail mock mode prints OTP to terminal.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 7 — ADDING REAL CLAUDE API LATER (when you get a key)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. pip install anthropic (in both backend venvs)
  2. Add to both .env files: ANTHROPIC_API_KEY=sk-ant-xxxxx
  3. In both genai_mock.py files:
     - Uncomment the generate_content_ai() function at the bottom
     - In generate_content(), change the last return to call generate_content_ai()
  That is the ONLY change needed. Everything else stays identical.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 8 — QUICK REFERENCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  User website:            http://localhost:5173
  Marketing dashboard:     http://localhost:5174
  User API docs:           http://localhost:8000/docs
  Marketing API docs:      http://localhost:8001/docs

  Reset all data:
    Delete xedu_v2\user-backend\xeducation_user.db
    Delete xedu_v2\marketing-backend\xeducation_marketing.db
    Restart both backends (DBs recreated automatically)

  View database visually:
    Install DB Browser for SQLite: https://sqlitebrowser.org/
    Open: xedu_v2\user-backend\xeducation_user.db

  Manually trigger cart abandonment job (for demo):
    In DB Browser → cart table → change added_at to 2 hours ago → restart backend
