# Aarogya Companion

Build Aarogya AI — a premium Indian medical AI web app.

TECH STACK:
React 18 + TypeScript + Vite + Tailwind CSS + Framer Motion + React Router v6
Icons: Lucide React
Fonts: Inter (all text) + JetBrains Mono (numbers, badges, code)
Load fonts from Google Fonts in index.html

DESIGN TOKENS — add to tailwind.config.js:
colors:
  bg: '#0B1117'
  surface: '#161B22'
  surface2: '#1C2230'
  border: '#253044'
  teal: '#00C9A7'
  teal-dim: 'rgba(0,201,167,0.1)'
  text: '#E6EDF3'
  muted: '#8B949E'
  dim: '#6E7681'
  emergency: '#FF7B72'
  urgent: '#F0A500'
  moderate: '#58A6FF'
  low: '#3FB950'
borderRadius:
  sm: '6px', DEFAULT: '8px', lg: '12px', xl: '16px', pill: '9999px'
fontFamily:
  sans: ['Inter', 'sans-serif']
  mono: ['JetBrains Mono', 'monospace']

GLOBAL CSS (index.css):
* html, body background: #0B1117
* Default text color: #E6EDF3
* Scrollbar: thin, #253044 thumb on transparent track
* Selection highlight: teal background, dark text
* Smooth scroll: html { scroll-behavior: smooth }

ROUTING — React Router v6:
Public routes (no auth needed):
  /            → SplashScreen
  /home        → LandingPage
  /login       → LoginPage
  /signup      → SignUpPage

Protected routes (redirect to /login if not authenticated):
  /dashboard   → Dashboard
  /analyze     → AnalyzePage
  /results/:id → ResultsPage
  /doctors     → DoctorFinderPage
  /history     → HistoryPage
  /profile     → ProfilePage
  /settings    → SettingsPage

AUTH — Use Supabase Auth (NOT custom React Context):
* Initialize Supabase client using the project's Supabase URL and anon key
* Use supabase.auth.signInWithPassword() for email login
* Use supabase.auth.signInWithOAuth({ provider: 'google' }) for Google sign-in
* Use supabase.auth.onAuthStateChange() to listen for session changes
* ProtectedRoute component: checks Supabase session, redirects to /login if missing
* After login: redirect to /dashboard
* After logout: supabase.auth.signOut(), redirect to /home
* Store user profile in Supabase 'profiles' table

APP SHELL:
* AppLayout component wraps all protected routes
* Left sidebar (240px, fixed): logo top + nav items + user avatar bottom
* Main content area: flex-1, overflow-y auto
* Sidebar collapses to 60px (icons only) on screens < 1024px
* Mobile (< 768px): sidebar becomes bottom tab bar with 4 items only: Home, Analyze, Doctors, Profile

NAV ITEMS in sidebar (desktop shows all, mobile bottom bar shows 4):
🏠 Home → /dashboard
🔬 Analyze → /analyze
🏥 Doctors → /doctors
📋 History → /history
👤 Profile → /profile
⚙️ Settings → /settings
Sign out (bottom, red hover)

Active nav item: left 2px teal border + teal text + rgba(0,201,167,0.06) background

API SETUP:
Create src/api/mediassist.ts
Base URL from: import.meta.env.VITE_API_BASE_URL || 'https://zilbjmvwx1.execute-api.us-east-1.amazonaws.com/api/v1'
Export these typed functions:
  checkHealth(): Promise
  analyzeSymptoms(data: FormData): Promise<AnalyzeResponse>
  searchDoctors(params: DoctorSearchParams): Promise<DoctorSearchResponse>
  getSession(id: string): Promise<AnalyzeResponse>
  getHistory(): Promise<AnalyzeResponse[]>
  submitFeedback(sessionId: string, rating: 1|-1, comment?: string): Promise<void>

Create src/types/api.types.ts with all TypeScript interfaces:
  interface PatientProfile { name: string; age: number; gender: 'male'|'female'|'other'; blood_group?: string; height_cm?: number; weight_kg?: number; conditions?: string[]; allergies?: string[]; medications?: string[]; smoking?: 'never'|'former'|'current'; pack_years?: number; alcohol_units_per_week?: number; activity_level?: 'sedentary'|'light'|'moderate'|'active'; sleep_hours?: number; }
  interface Diagnosis { condition_name: string; confidence: number; explanation: string; severity_level: string; specialist_needed: string; citations: string[]; }
  interface Urgency { level: 'emergency'|'urgent'|'moderate'|'low'; action_plan: string[]; call_emergency: boolean; }
  interface DoctorResult { name: string; specialty: string; address: string; distance_km: number; rating?: number; phone?: string; is_open_now?: boolean; source: string; }
  interface AnalyzeResponse { session_id: string; context_built: boolean; inputs_processed: string[]; symptoms_extracted: number; risk_flags: string[]; context_confidence: number; primary_concern: string; diagnosis?: Diagnosis; urgency?: Urgency; recommendations?: DoctorResult[]; disclaimer: string; processing_time_ms: number; }
  interface DoctorSearchParams { condition: string; lat?: number; lng?: number; radius_km?: number; }
  interface DoctorSearchResponse { specialty: string; doctors: DoctorResult[]; condition: string; }

Do not build any page content yet — just the foundation, routing, AppLayout, Supabase auth setup, and API layer. All page components should be placeholder divs with just the page name as text.

This project was built with [Lovable](https://lovable.dev).

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/49301e8d-e29f-4f15-99f9-b6ca1c02f085).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
