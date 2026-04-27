# Audio Recording Feature Implementation Plan

**Project:** SonicFlow Studio v5 - Live Audio Recording Feature  
**Date:** 2026-04-27  
**Architect:** System Architect Agent  
**Status:** Planning Phase  

---

## Executive Summary

This document outlines the implementation plan for adding a live audio recording feature to SonicFlow Studio, along with validation of local testing setup, code quality checks, and browser automation testing against the production EC2 instance.

**Current Production Environment:**
- **Frontend:** Next.js 14 (port 3001) at http://3.239.91.199:3001
- **Backend:** FastAPI (port 8000) at http://3.239.91.199:8000
- **Deployment:** AWS EC2 Ubuntu with systemd services
- **Auth:** admin@studio.com / admins
- **Storage:** File-based JSON (data/projects.json)

---

## 1. Work Breakdown Structure

### Workstream 1: Local Testing Setup Validation
**Owner:** DevOps/Testing Agent  
**Duration:** Low complexity  
**Dependencies:** None

#### Tasks:
1. **Environment Verification**
   - Verify Python 3.11+ with venv activation
   - Verify Node.js 18+ and npm installation
   - Check all required system dependencies (ffmpeg, etc.)
   - Validate .env file structure and required API keys

2. **Service Health Checks**
   - Test FastAPI backend startup on port 8000
   - Test Next.js frontend startup on port 3001
   - Verify CORS configuration between services
   - Test authentication flow (login endpoint)

3. **API Endpoint Validation**
   - POST /login - authentication
   - POST /generate - full pipeline test
   - GET /artists/search - Genius API integration
   - POST /stems/extract - stem extraction flow
   - GET /projects - project listing

4. **Local vs EC2 Parity Check**
   - Compare API response structures
   - Verify data persistence patterns
   - Check audio file serving (CORS headers)
   - Validate systemd service configurations

**Deliverables:**
- Local environment validation report
- Service health dashboard
- API endpoint test results
- Parity analysis document

---

### Workstream 2: Audio Recording Feature (Frontend + Backend)
**Owner:** Full-Stack Feature Agent  
**Duration:** Medium complexity  
**Dependencies:** Local testing setup validated

#### 2.1 Frontend Implementation (Next.js)

**Files to Create:**
- `frontend-nextjs/components/AudioRecorder.tsx` - Main recording component
- `frontend-nextjs/components/RecordingControls.tsx` - Start/stop/pause controls
- `frontend-nextjs/components/AudioWaveform.tsx` - Real-time waveform visualization
- `frontend-nextjs/lib/audioRecorder.ts` - Browser MediaRecorder API wrapper
- `frontend-nextjs/hooks/useAudioRecorder.ts` - React hook for recording state

**Files to Modify:**
- `frontend-nextjs/app/page.tsx` - Add recording UI to Multimodal Tools section
- `frontend-nextjs/lib/types.ts` - Add recording-related types
- `frontend-nextjs/lib/api.ts` - Add upload endpoint for recorded audio

**Implementation Details:**

```typescript
// New Types (frontend-nextjs/lib/types.ts)
export interface RecordingState {
  status: 'idle' | 'recording' | 'paused' | 'stopped'
  duration: number
  audioBlob: Blob | null
  error: string | null
}

export interface AudioRecorderConfig {
  sampleRate: number
  channelCount: number
  mimeType: string
  maxDuration: number // seconds
  maxSize: number // bytes (e.g., 60MB)
}
```

**Recording Flow:**
1. Request microphone permission via `navigator.mediaDevices.getUserMedia()`
2. Initialize MediaRecorder with optimal audio settings (WebM/MP3)
3. Capture audio chunks in real-time
4. Display live duration timer and waveform
5. On stop, combine chunks into single Blob
6. Validate file size (max 60MB to match backend limit)
7. Offer preview playback before upload
8. Upload to backend as instrumental or reference audio

**UI Integration:**
- Add "Record Audio" button in Multimodal Tools section (sidebar)
- Modal dialog for recording interface
- Visual feedback: recording indicator (pulsing red dot), timer, waveform
- Preview player with re-record option
- Direct integration with instrumental upload flow

#### 2.2 Backend Implementation (FastAPI)

**Files to Create:**
- `api/routes/recordings.py` - New recording endpoints (optional refactor)
- `services/audio_validator.py` - Audio file validation and format conversion

**Files to Modify:**
- `api/main.py` - Add recording upload endpoint (or reuse existing upload flow)
- `services/audio_mixer.py` - Extend to handle recorded audio formats

**New Endpoints:**

```python
POST /recordings/upload
- Accept recorded audio (WebM, MP3, WAV)
- Validate format, size (<60MB), duration
- Convert to standard format (MP3 16-bit 44.1kHz) if needed
- Save to UPLOADS_DIR or AUDIO_DIR
- Return file URL or reference ID
- Same auth as other endpoints (Bearer token)

GET /recordings/{recording_id}
- Serve recorded audio file
- Same CORS headers as /audio/{filename}
```

**Implementation Details:**

```python
# Audio Validation
- Max size: 60MB (consistent with stem extraction)
- Supported formats: audio/webm, audio/mp3, audio/wav, audio/ogg
- Sample rate: normalize to 44.1kHz or 48kHz
- Bit depth: 16-bit minimum
- Duration: 15 seconds minimum, 10 minutes maximum

# Storage
- Save to: data/recordings/{user_session_id}/{timestamp}.mp3
- Filename format: recording_{timestamp}_{uuid}.mp3
- Auto-cleanup: recordings older than 7 days (background task)

# Integration with existing flows:
- Recorded audio can be used as "instrumental" in /generate endpoint
- Recorded audio can be sent to /stems/extract
- Recorded audio can be saved to project library
```

---

### Workstream 3: Browser Automation Testing
**Owner:** QA/Automation Agent  
**Duration:** Medium complexity  
**Dependencies:** Local setup validated, audio recording feature implemented

#### 3.1 Test Setup

**Framework:** Playwright (already available via MCP server)  
**Target:** Production EC2 at http://3.239.91.199:3001  
**Authentication:** admin@studio.com / admins

**Files to Create:**
- `tests/e2e/test_main_flows.spec.ts` - Core user flows
- `tests/e2e/test_recording_feature.spec.ts` - Audio recording tests
- `tests/e2e/test_stem_extraction.spec.ts` - Stem extraction flow
- `tests/e2e/fixtures/audio-samples/` - Test audio files
- `tests/e2e/helpers/auth.ts` - Login helper
- `tests/e2e/playwright.config.ts` - Playwright configuration

#### 3.2 Critical User Flows to Test

**Flow 1: Full Song Generation (Draft Mode)**
1. Navigate to http://3.239.91.199:3001
2. Login with credentials
3. Fill artist field: "Drake"
4. Fill theme: "late night drive"
5. Select Draft Mode output
6. Click "IGNITE PRODUCTION"
7. Wait for pipeline completion (max 60s)
8. Verify lyrics generated
9. Verify voice audio player present
10. Download and validate MP3 file
11. Check auto-save to project library

**Flow 2: Audio Recording Feature**
1. Login and navigate to Studio
2. Click "Record Audio" button in sidebar
3. Grant microphone permissions
4. Click "Start Recording"
5. Record for 5 seconds
6. Click "Stop"
7. Preview recorded audio
8. Use as instrumental upload
9. Generate lyrics with recorded track
10. Verify lyrics styled to recording

**Flow 3: Stem Extraction**
1. Login and navigate to Studio
2. Upload test MP3 to Stem Extraction section
3. Wait for upload completion
4. Monitor processing status (polling every 6s)
5. Wait for completion (max 8 minutes)
6. Verify 4 stems available (vocals, drums, bass, other)
7. Play each stem individually
8. Download all stems as ZIP
9. Verify ZIP contains 4 WAV files

**Flow 4: Producer Mode Workflow**
1. Login and select Producer Remix output mode
2. Select "AI Singing (Suno)" vocal source
3. Generate full song
4. Verify both audio tracks generated
5. Verify automatic stem extraction triggered
6. Check Stems tab for extracted components
7. Download all producer exports
8. Verify file formats and naming

**Flow 5: Project Library**
1. Navigate to /library
2. Verify saved projects display
3. Click project card
4. Verify project opens in Studio with all params restored
5. Delete project
6. Verify deletion reflected in library

#### 3.3 Recording Feature-Specific Tests

```typescript
test('Audio recording captures and uploads successfully', async ({ page }) => {
  // Setup: Mock microphone input with test audio
  await page.context().grantPermissions(['microphone'])
  
  // Start recording
  await page.click('[data-testid="record-audio-button"]')
  await page.click('[data-testid="start-recording"]')
  
  // Verify recording UI
  expect(await page.locator('[data-testid="recording-indicator"]').isVisible()).toBe(true)
  expect(await page.locator('[data-testid="recording-timer"]').textContent()).toContain('00:')
  
  // Wait 5 seconds
  await page.waitForTimeout(5000)
  
  // Stop recording
  await page.click('[data-testid="stop-recording"]')
  
  // Preview
  expect(await page.locator('[data-testid="recording-preview"]').isVisible()).toBe(true)
  
  // Upload as instrumental
  await page.click('[data-testid="use-as-instrumental"]')
  
  // Verify file uploaded
  expect(await page.locator('[data-testid="uploaded-instrumental"]').textContent())
    .toContain('recording_')
})

test('Recording respects size limits', async ({ page }) => {
  // Attempt 10-minute recording (should enforce max limit)
  // Verify error message for oversized recordings
})

test('Recording handles permission denial gracefully', async ({ page }) => {
  // Deny microphone permissions
  // Verify error message displayed
  // Verify fallback to file upload remains available
})
```

#### 3.4 Error Scenario Tests

1. **Network Failures**
   - Simulate API timeout during generation
   - Verify user-friendly error messages
   - Verify retry mechanism

2. **Invalid Inputs**
   - Empty artist + empty theme
   - Oversized file uploads
   - Unsupported audio formats

3. **Service Degradation**
   - ElevenLabs API failure (voice_error handling)
   - Suno API failure (music_error handling)
   - Stem extraction timeout

4. **Concurrent Operations**
   - Start generation, immediately start another
   - Upload stem while generation running
   - Multiple browser tabs

---

### Workstream 4: Security Review
**Owner:** Security Agent  
**Duration:** Low complexity  
**Dependencies:** Feature implementation complete

#### 4.1 Security Checklist

**Authentication & Authorization:**
- ✓ All endpoints require Bearer token (except /health)
- ✓ Session token validation in `verify_token()`
- ⚠️ Hardcoded credentials (admin@studio.com) - acceptable for MVP
- ⚠️ No password hashing - acceptable for single-user system
- ⚠️ No HTTPS - recommend for production

**Input Validation:**
- ✓ File size limits enforced (60MB)
- ✓ File extension validation (.mp3, .wav, .m4a, .flac)
- ✓ Path traversal protection in `/audio/{filename}` (uses Path.name)
- ⚠️ Missing MIME type validation on uploads
- ⚠️ No virus scanning on uploaded files

**Data Exposure:**
- ✓ Stem extraction uses random job_id (12-char hex)
- ✓ No SQL injection risk (no SQL database)
- ⚠️ API keys in .env (secure, but ensure .gitignore)
- ⚠️ CORS allows all origins (*) - restrict in production

**Rate Limiting:**
- ⚠️ No rate limiting implemented
- ⚠️ No request size limits beyond file uploads
- ⚠️ No concurrent request throttling

**Audio Recording Security:**
- ⚠️ Need to validate audio format from browser
- ⚠️ Need to sanitize recording metadata
- ⚠️ Need to implement per-user storage quotas
- ⚠️ Need to auto-delete old recordings (privacy)

#### 4.2 Recommendations

**Critical (Implement before production):**
1. Add MIME type validation for all uploads
2. Restrict CORS origins to known domains
3. Implement recording storage quotas per session
4. Add auto-cleanup for recordings >7 days old

**High Priority (Implement within 1 month):**
1. Enable HTTPS on EC2 (Let's Encrypt)
2. Add rate limiting (10 requests/minute per IP)
3. Implement basic virus scanning (ClamAV)
4. Add request logging for security auditing

**Medium Priority:**
1. Replace hardcoded credentials with env vars
2. Add password hashing (argon2)
3. Implement session expiry
4. Add CSRF protection

**Low Priority (Future):**
1. Multi-user authentication system
2. Role-based access control
3. API key rotation mechanism
4. Encrypted storage for sensitive data

---

## 2. File Ownership Map

### Frontend Files

| File | Owner | Operations | Conflicts |
|------|-------|------------|-----------|
| `frontend-nextjs/components/AudioRecorder.tsx` | Feature Agent | Create | None |
| `frontend-nextjs/components/RecordingControls.tsx` | Feature Agent | Create | None |
| `frontend-nextjs/components/AudioWaveform.tsx` | Feature Agent | Create | None |
| `frontend-nextjs/lib/audioRecorder.ts` | Feature Agent | Create | None |
| `frontend-nextjs/hooks/useAudioRecorder.ts` | Feature Agent | Create | None |
| `frontend-nextjs/app/page.tsx` | Feature Agent | Modify (lines 939-1021) | ⚠️ Multimodal Tools section |
| `frontend-nextjs/lib/types.ts` | Feature Agent | Modify (add types) | ⚠️ Shared types file |
| `frontend-nextjs/lib/api.ts` | Feature Agent | Modify (add endpoint) | ⚠️ Shared API client |
| `frontend-nextjs/components/GenerationStatus.tsx` | Testing Agent | Read only | None |
| `frontend-nextjs/components/StemPlayer.tsx` | Testing Agent | Read only | None |

### Backend Files

| File | Owner | Operations | Conflicts |
|------|-------|------------|-----------|
| `api/main.py` | Feature Agent | Modify (add endpoint) | ⚠️ Main API file |
| `services/audio_validator.py` | Feature Agent | Create | None |
| `services/audio_mixer.py` | Feature Agent | Modify (extend) | ⚠️ Shared service |
| `services/stem_extractor.py` | Testing Agent | Read only | None |

### Testing Files

| File | Owner | Operations | Conflicts |
|------|-------|------------|-----------|
| `tests/e2e/test_main_flows.spec.ts` | QA Agent | Create | None |
| `tests/e2e/test_recording_feature.spec.ts` | QA Agent | Create | None |
| `tests/e2e/test_stem_extraction.spec.ts` | QA Agent | Create | None |
| `tests/e2e/helpers/auth.ts` | QA Agent | Create | None |
| `tests/e2e/playwright.config.ts` | QA Agent | Create | None |
| `tests/e2e/fixtures/audio-samples/` | QA Agent | Create (directory) | None |

### Documentation Files

| File | Owner | Operations | Conflicts |
|------|-------|------------|-----------|
| `docs/plans/audio-recording-feature.md` | Architect | This file | None |
| `docs/testing-report.md` | QA Agent | Create | None |
| `docs/security-audit.md` | Security Agent | Create | None |
| `README.md` | All | Update | ⚠️ Shared documentation |

### Conflict Resolution Strategy

**High-Conflict Files:**
1. `frontend-nextjs/app/page.tsx` - Feature Agent modifies lines 939-1021 (Multimodal Tools section)
2. `frontend-nextjs/lib/types.ts` - Feature Agent adds types at end of file
3. `frontend-nextjs/lib/api.ts` - Feature Agent adds functions at end of file
4. `api/main.py` - Feature Agent adds endpoint before final routes

**Resolution:**
- All modifications use append strategy (add to end)
- Clear section markers in comments: `# ── Audio Recording Feature ──`
- Sequential development: Testing waits for Feature completion
- Code reviews before merge to main branch

---

## 3. Risk Assessment

### Risk Matrix

| Risk Area | Severity | Probability | Impact | Mitigation |
|-----------|----------|-------------|--------|------------|
| **Local Setup Changes** | Low | Low | Low | No infrastructure changes needed |
| **Audio Recording - Browser Permissions** | Medium | High | Medium | Clear permission prompts, fallback to upload |
| **Audio Recording - File Size** | Medium | Medium | Medium | Client-side validation before upload |
| **Audio Recording - Format Compatibility** | Medium | Medium | High | Server-side format conversion with ffmpeg |
| **Audio Recording - Storage Growth** | Medium | High | High | Auto-cleanup policy, user quotas |
| **Browser Automation - Production Testing** | High | Low | High | Read-only tests, separate test account |
| **EC2 Resource Exhaustion** | Critical | Low | Critical | Recording size limits, concurrent limits |
| **Cross-Browser Compatibility** | Medium | Medium | Medium | Test on Chrome, Firefox, Safari |
| **Mobile Recording** | High | High | High | Disable on mobile, show desktop-only notice |

### Detailed Risk Analysis

#### 1. Local Setup Changes
**Risk Level:** Low  
**Description:** Validating local development environment against production

**Potential Issues:**
- Environment variable mismatches
- Port conflicts (3001, 8000)
- Missing dependencies (ffmpeg, Python packages)

**Mitigation:**
- Document exact dependency versions in requirements.txt
- Create setup validation script
- Use Docker for consistent environments (future)

**Rollback:** No rollback needed (read-only validation)

---

#### 2. Audio Recording Feature - Browser Permissions
**Risk Level:** Medium  
**Description:** Users may deny microphone permissions

**Potential Issues:**
- Permission denied → feature unusable
- Permission prompt confusion
- Privacy concerns

**Mitigation:**
- Clear explanatory text before permission request
- Show visual example of recording interface
- Fallback to file upload always available
- "Why do we need this?" help tooltip

**Rollback:** Feature can be hidden via feature flag

---

#### 3. Audio Recording Feature - File Size
**Risk Level:** Medium  
**Description:** Long recordings may exceed 60MB limit

**Potential Issues:**
- User records 10-minute session → 150MB file
- Upload fails after long recording
- User frustration, data loss

**Mitigation:**
- Display max duration timer (e.g., "5:00 remaining")
- Auto-stop recording at 8 minutes
- Client-side size estimation during recording
- Show size warning at 50MB threshold
- Use compressed format (MP3 128kbps, not WAV)

**Rollback:** Remove recording feature, keep upload

---

#### 4. Audio Recording Feature - Format Compatibility
**Risk Level:** Medium  
**Description:** Browser-generated audio may not be compatible with backend

**Potential Issues:**
- WebM format not playable in Safari
- Ogg format not supported by ElevenLabs/Suno
- Sample rate mismatches
- Codec incompatibilities

**Mitigation:**
- Server-side format normalization with ffmpeg
- Convert all recordings to MP3 16-bit 44.1kHz
- Test across browsers: Chrome (WebM), Firefox (Ogg), Safari (MP4)
- Client-side format selection based on browser

**Rollback:** Disable recording, use upload only

---

#### 5. Audio Recording Feature - Storage Growth
**Risk Level:** High  
**Description:** Recorded files accumulate, filling EC2 disk

**Potential Issues:**
- 100 users × 10 recordings × 30MB = 30GB
- EC2 disk full → service crashes
- Old recordings never deleted

**Mitigation:**
- **Immediate:** Max 5 recordings per session
- **Short-term:** Auto-delete recordings after 7 days
- **Long-term:** Per-user storage quotas (500MB)
- Background cleanup task runs daily
- Disk usage monitoring alerts (>80% capacity)

**Rollback:** Delete all recordings directory, disable feature

---

#### 6. Browser Automation - Production Testing
**Risk Level:** High  
**Description:** Automated tests run against live EC2 production instance

**Potential Issues:**
- Test data pollutes production database
- High load from test suite crashes server
- Accidental data deletion
- Cost spikes from API usage (OpenAI, ElevenLabs, Suno)

**Mitigation:**
- **Critical:** Read-only tests (no POST/DELETE) for first run
- Create separate test account: test@studio.com
- Tag all test projects with "E2E_TEST_" prefix
- Auto-cleanup test data after suite runs
- Rate limiting: 1 test every 30 seconds
- Run tests during low-traffic hours (2-5 AM UTC)
- Mock external API calls where possible

**Rollback:** Disable automation, manual testing only

---

#### 7. EC2 Resource Exhaustion
**Risk Level:** Critical  
**Description:** Multiple concurrent recordings + stem extractions overwhelm EC2

**Potential Issues:**
- 10 users record simultaneously → 10 × 30MB uploads
- Concurrent Demucs stem extractions (GPU/CPU intensive)
- Memory exhaustion → OOM killer terminates services
- Swap thrashing → system unresponsive

**Mitigation:**
- **Immediate:** Limit concurrent recordings to 3
- **Immediate:** Limit concurrent stem extractions to 2
- Queue system for stem extraction (not parallel)
- Monitor EC2 metrics: CPU, memory, disk I/O
- Auto-scaling (future): add EC2 instance if load >80%
- Resource limits: Max 1GB memory per recording process

**Rollback:** Disable recording feature, reduce stem extraction workers

---

#### 8. Cross-Browser Compatibility
**Risk Level:** Medium  
**Description:** MediaRecorder API behaves differently across browsers

**Browser Support:**
- ✅ Chrome 47+ (WebM with VP8/VP9)
- ✅ Firefox 25+ (Ogg with Opus)
- ✅ Safari 14.1+ (MP4 with AAC)
- ❌ IE 11 (no support)
- ❌ Safari <14.1 (no support)

**Potential Issues:**
- Different audio codecs per browser
- Safari uses MP4, not WebM
- Format incompatibilities with backend processing

**Mitigation:**
- Detect browser and use appropriate MIME type
- Server normalizes all formats to MP3
- Display browser compatibility warning on old browsers
- Graceful degradation: show upload button only on unsupported browsers

**Rollback:** Feature flag per browser

---

#### 9. Mobile Recording
**Risk Level:** High  
**Description:** Recording on mobile devices has unique challenges

**Potential Issues:**
- High latency on mobile networks (large uploads)
- Background tab auto-pauses recording (iOS)
- Battery drain during long recordings
- Touch UI interactions differ from desktop
- Mobile browsers have stricter permissions

**Mitigation:**
- **Phase 1:** Desktop only (display "Desktop required" message on mobile)
- **Phase 2:** Mobile optimization after desktop stable
- Detect screen size: hide recording if width <768px
- Show clear mobile incompatibility message

**Rollback:** Keep mobile disabled indefinitely

---

## 4. Testing Strategy

### 4.1 Testing Levels

#### Unit Tests (Python - Backend)
**Framework:** pytest  
**Coverage Target:** 80% for new code  
**Files:**
- `tests/unit/test_audio_validator.py`
- `tests/unit/test_recordings_endpoint.py`

**Test Cases:**
```python
# Audio Validation
test_audio_validator_accepts_valid_formats()
test_audio_validator_rejects_oversized_files()
test_audio_validator_rejects_invalid_formats()
test_audio_validator_normalizes_sample_rate()
test_audio_validator_converts_webm_to_mp3()

# Recording Endpoint
test_upload_recording_success()
test_upload_recording_without_auth_fails()
test_upload_recording_exceeding_size_limit_fails()
test_upload_recording_saves_to_correct_directory()
test_upload_recording_returns_valid_url()
```

#### Integration Tests (Python - Backend)
**Framework:** pytest with TestClient  
**Coverage Target:** 70% for API flows  

**Test Cases:**
```python
# End-to-End Recording Flow
test_upload_recording_and_use_as_instrumental()
test_upload_recording_and_extract_stems()
test_upload_recording_and_generate_lyrics()
test_concurrent_uploads_with_rate_limiting()
test_recording_cleanup_job_deletes_old_files()
```

#### Component Tests (Frontend - React)
**Framework:** Jest + React Testing Library  
**Coverage Target:** 75% for new components  

**Test Cases:**
```typescript
// AudioRecorder Component
test('renders recording button', () => {})
test('requests microphone permission on start', () => {})
test('displays recording timer during capture', () => {})
test('stops recording and creates blob', () => {})
test('validates file size before upload', () => {})
test('shows error message on permission denial', () => {})
test('displays waveform during recording', () => {})

// RecordingControls Component
test('start button initiates recording', () => {})
test('stop button ends recording', () => {})
test('pause button pauses recording', () => {})
test('disables controls during upload', () => {})
```

#### E2E Tests (Browser Automation)
**Framework:** Playwright  
**Coverage Target:** 100% of critical user flows  

**Critical Flows (see Workstream 3.2):**
1. Full Song Generation (Draft Mode)
2. Audio Recording Feature
3. Stem Extraction
4. Producer Mode Workflow
5. Project Library

**Test Execution:**
- **Local:** Run against http://localhost:3001 (fast iteration)
- **Staging:** Run against EC2 after deployment (pre-release validation)
- **Production:** Read-only smoke tests only (health checks)

**Schedule:**
- Local: On every PR (CI/CD pipeline)
- EC2: Daily at 3:00 AM UTC (scheduled job)
- Production: Weekly (Sunday midnight)

---

### 4.2 Browser Automation Details

#### Test Environment Setup

```typescript
// tests/e2e/playwright.config.ts
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 120000, // 2 minutes per test
  retries: 2, // Retry flaky tests
  workers: 1, // Sequential execution (avoid overloading EC2)
  
  use: {
    baseURL: 'http://3.239.91.199:3001',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    
    // Emulate real user
    viewport: { width: 1920, height: 1080 },
    userAgent: 'Mozilla/5.0 (Playwright E2E Tests)',
    
    // Authentication
    storageState: 'tests/e2e/.auth/user.json',
  },
  
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
  ],
})
```

#### Authentication Helper

```typescript
// tests/e2e/helpers/auth.ts
export async function login(page: Page) {
  await page.goto('/login')
  await page.fill('[data-testid="email-input"]', 'admin@studio.com')
  await page.fill('[data-testid="password-input"]', 'admins')
  await page.click('[data-testid="login-button"]')
  await page.waitForURL('/')
  await expect(page.locator('text=SonicFlow')).toBeVisible()
}
```

#### Recording Feature Test

```typescript
// tests/e2e/test_recording_feature.spec.ts
test.describe('Audio Recording Feature', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('user can record audio and use as instrumental', async ({ page, context }) => {
    // Grant microphone permission
    await context.grantPermissions(['microphone'])
    
    // Open recording modal
    await page.click('[data-testid="record-audio-button"]')
    await expect(page.locator('[data-testid="recording-modal"]')).toBeVisible()
    
    // Start recording
    await page.click('[data-testid="start-recording"]')
    
    // Verify recording UI
    const indicator = page.locator('[data-testid="recording-indicator"]')
    await expect(indicator).toBeVisible()
    await expect(indicator).toHaveCSS('background-color', 'rgb(255, 71, 87)') // Red
    
    // Verify timer running
    const timer = page.locator('[data-testid="recording-timer"]')
    await expect(timer).toContainText('00:0')
    
    // Wait 5 seconds
    await page.waitForTimeout(5000)
    await expect(timer).toContainText('00:0[5-9]') // 5-9 seconds
    
    // Stop recording
    await page.click('[data-testid="stop-recording"]')
    
    // Verify preview available
    const preview = page.locator('[data-testid="recording-preview"]')
    await expect(preview).toBeVisible()
    
    // Play preview
    await page.click('[data-testid="preview-play"]')
    await page.waitForTimeout(2000)
    
    // Use as instrumental
    await page.click('[data-testid="use-as-instrumental"]')
    
    // Verify uploaded
    const uploadedFile = page.locator('[data-testid="uploaded-instrumental"]')
    await expect(uploadedFile).toContainText('recording_')
    
    // Generate with recorded instrumental
    await page.fill('[data-testid="artist-input"]', 'Drake')
    await page.fill('[data-testid="theme-input"]', 'test recording')
    await page.click('[data-testid="generate-button"]')
    
    // Wait for generation
    await page.waitForSelector('[data-testid="lyrics-output"]', { timeout: 60000 })
    
    // Verify lyrics generated
    const lyrics = page.locator('[data-testid="lyrics-output"]')
    await expect(lyrics).not.toBeEmpty()
  })

  test('shows error when microphone permission denied', async ({ page, context }) => {
    // Deny microphone
    await context.grantPermissions([])
    
    await page.click('[data-testid="record-audio-button"]')
    await page.click('[data-testid="start-recording"]')
    
    // Verify error message
    const error = page.locator('[data-testid="recording-error"]')
    await expect(error).toBeVisible()
    await expect(error).toContainText('Microphone permission denied')
    
    // Verify fallback to upload shown
    await expect(page.locator('[data-testid="upload-fallback"]')).toBeVisible()
  })

  test('enforces maximum recording duration', async ({ page, context }) => {
    await context.grantPermissions(['microphone'])
    
    await page.click('[data-testid="record-audio-button"]')
    await page.click('[data-testid="start-recording"]')
    
    // Fast-forward to 8 minutes (480 seconds)
    // In real test, we'd mock the timer or use a shorter limit for testing
    await page.waitForTimeout(1000) // Simulate
    
    // Verify duration warning appears
    const warning = page.locator('[data-testid="duration-warning"]')
    // (Implementation detail: show warning at 7 minutes)
    
    // Verify auto-stop at max duration
    // (Implementation detail: auto-stop at 8 minutes)
  })

  test('validates file size before upload', async ({ page, context }) => {
    // This test would need to mock a large file or use a pre-recorded large file
    // Skip for now, or use a fixture that exceeds 60MB
  })
})
```

#### Stem Extraction Flow Test

```typescript
// tests/e2e/test_stem_extraction.spec.ts
test('full stem extraction workflow', async ({ page }) => {
  await login(page)
  
  // Upload test audio file
  const filePath = path.join(__dirname, 'fixtures/audio-samples/test-song.mp3')
  await page.setInputFiles('[data-testid="stem-file-input"]', filePath)
  
  // Verify upload started
  const status = page.locator('[data-testid="stem-status"]')
  await expect(status).toContainText('Uploading')
  
  // Wait for processing
  await expect(status).toContainText('Extracting', { timeout: 10000 })
  
  // Wait for completion (max 8 minutes)
  await expect(status).toContainText('ready', { timeout: 480000 })
  
  // Switch to Stems tab
  await page.click('[data-testid="tab-stems"]')
  
  // Verify 4 stems present
  const stemPlayers = page.locator('[data-testid^="stem-player-"]')
  await expect(stemPlayers).toHaveCount(4)
  
  // Test playing each stem
  await page.click('[data-testid="stem-player-vocals"] [data-testid="play-button"]')
  await page.waitForTimeout(2000)
  await page.click('[data-testid="stem-player-vocals"] [data-testid="pause-button"]')
  
  // Download ZIP
  const downloadPromise = page.waitForEvent('download')
  await page.click('[data-testid="download-stems-zip"]')
  const download = await downloadPromise
  
  // Verify ZIP filename
  expect(download.suggestedFilename()).toMatch(/stems_.*\.zip/)
})
```

---

### 4.3 Coverage Targets Summary

| Test Level | Target | Critical Features | Non-Critical |
|------------|--------|-------------------|--------------|
| Unit Tests (Backend) | 80% | Recording validation, format conversion | Utility functions |
| Unit Tests (Frontend) | 75% | Recording hooks, audio processing | UI components |
| Integration Tests | 70% | Upload → Generate flow, Upload → Stems flow | Individual endpoints |
| E2E Tests | 100% | All 5 critical user flows | Edge cases, error states |

**Coverage Enforcement:**
- CI/CD pipeline fails if coverage drops below targets
- Weekly coverage reports emailed to team
- Untested code highlighted in PR reviews

---

## 5. Rollback Plan

### Scenario 1: Audio Recording Feature Causes Critical Issues

**Symptoms:**
- Server crashes due to memory exhaustion
- Recordings corrupt audio generation pipeline
- Browser crashes during recording
- User data loss

**Rollback Steps:**

1. **Immediate (T+0 minutes):**
   ```bash
   # SSH to EC2
   ssh ubuntu@3.239.91.199
   
   # Set feature flag to disable recording
   cd ~/AI-Songwriting-System
   echo "FEATURE_AUDIO_RECORDING=false" >> .env
   
   # Restart services
   sudo systemctl restart sonicflow-api
   sudo systemctl restart sonicflow-nextjs
   
   # Verify services running
   sudo systemctl status sonicflow-api
   sudo systemctl status sonicflow-nextjs
   ```

2. **Short-term (T+15 minutes):**
   ```bash
   # Revert to previous commit (before recording feature)
   git log --oneline  # Find last good commit
   git revert <commit-hash>  # Or use git reset --hard <commit-hash>
   
   # Rebuild frontend
   cd frontend-nextjs
   npm run build
   
   # Restart services
   sudo systemctl restart sonicflow-nextjs
   ```

3. **Cleanup (T+30 minutes):**
   ```bash
   # Delete all recorded files to free disk space
   rm -rf data/recordings/*
   
   # Optional: keep last 24 hours for debugging
   find data/recordings -type f -mtime +0 -delete
   ```

4. **Monitoring (T+1 hour):**
   - Check error logs: `journalctl -u sonicflow-api -f`
   - Monitor disk usage: `df -h`
   - Verify API health: `curl http://3.239.91.199:8000/health`
   - Test manual generation on frontend

**Rollback Verification Checklist:**
- [ ] Frontend accessible at http://3.239.91.199:3001
- [ ] Login works
- [ ] Song generation works (Draft Mode)
- [ ] Stem extraction works
- [ ] No recording button visible
- [ ] No errors in browser console
- [ ] API health endpoint returns OK

**Post-Rollback:**
- Incident report: document root cause
- Fix issue in development
- Add regression test
- Re-deploy with fix after validation

---

### Scenario 2: Browser Automation Tests Overload Production

**Symptoms:**
- EC2 CPU at 100%
- API response times >10 seconds
- Real users unable to use service
- Suno/ElevenLabs API rate limits hit

**Rollback Steps:**

1. **Immediate (T+0 minutes):**
   ```bash
   # Kill Playwright process
   pkill -f playwright
   
   # If tests running as CI/CD job
   # Cancel GitHub Actions workflow or Jenkins job
   ```

2. **Service Recovery (T+5 minutes):**
   ```bash
   # SSH to EC2
   ssh ubuntu@3.239.91.199
   
   # Check service status
   sudo systemctl status sonicflow-api
   
   # If services crashed, restart
   sudo systemctl restart sonicflow-api
   sudo systemctl restart sonicflow-nextjs
   
   # Monitor recovery
   journalctl -u sonicflow-api -f
   ```

3. **Cleanup Test Data (T+15 minutes):**
   ```sql
   # Open projects.json
   cd ~/AI-Songwriting-System/data
   
   # Backup
   cp projects.json projects.json.backup
   
   # Remove test projects (manually edit JSON, or use Python script)
   python3 << EOF
   import json
   with open('projects.json') as f:
       projects = json.load(f)
   
   # Remove projects with test markers
   clean = [p for p in projects if not p.get('theme', '').startswith('E2E_TEST_')]
   
   with open('projects.json', 'w') as f:
       json.dump(clean, f, indent=2)
   EOF
   ```

4. **Prevention (T+30 minutes):**
   - Add rate limiting to tests (1 test per 30 seconds)
   - Run tests in read-only mode only
   - Use dedicated test environment (separate EC2)

---

### Scenario 3: Storage Exhaustion from Recordings

**Symptoms:**
- Disk usage >95%
- Service unable to save new projects
- Stem extraction fails with "No space left on device"
- API returns 500 errors

**Rollback Steps:**

1. **Immediate (T+0 minutes):**
   ```bash
   # SSH to EC2
   ssh ubuntu@3.239.91.199
   
   # Check disk usage
   df -h
   du -sh ~/AI-Songwriting-System/data/*
   
   # Emergency cleanup: delete all recordings
   rm -rf ~/AI-Songwriting-System/data/recordings/*
   
   # Delete old stem extraction jobs (keep last 7 days)
   find ~/AI-Songwriting-System/data/stems -type f -mtime +7 -delete
   
   # Delete old uploads
   find ~/AI-Songwriting-System/data/uploads -type f -mtime +3 -delete
   
   # Verify space freed
   df -h
   ```

2. **Service Restart (T+5 minutes):**
   ```bash
   sudo systemctl restart sonicflow-api
   sudo systemctl restart sonicflow-nextjs
   ```

3. **Monitoring (T+15 minutes):**
   - Set up disk usage alerts: `cron` job to email if >80%
   - Add automated cleanup script to run daily

4. **Long-term Fix:**
   - Implement recording quotas
   - Auto-cleanup recordings after 7 days
   - Move to S3 for audio storage (future)

---

### Rollback Decision Matrix

| Issue Severity | Response Time | Rollback Strategy | Notification |
|----------------|---------------|-------------------|--------------|
| **Critical** (service down) | <5 minutes | Full rollback, disable feature | Email, Slack, SMS |
| **High** (degraded performance) | <30 minutes | Feature flag disable | Email, Slack |
| **Medium** (some users affected) | <2 hours | Hotfix or rollback | Email |
| **Low** (edge cases) | <24 hours | Fix in next deployment | Ticket |

---

## 6. Implementation Phases

### Phase 1: Foundation (Week 1)
**Goal:** Validate environment and set up testing infrastructure

**Tasks:**
1. Local testing setup validation (Workstream 1)
2. Create E2E test structure (Workstream 3.1)
3. Security audit of existing system (Workstream 4)

**Deliverables:**
- [ ] Local environment validated
- [ ] E2E test framework configured
- [ ] Security baseline report

**Success Criteria:**
- All existing endpoints tested and documented
- Zero critical security vulnerabilities
- E2E tests run successfully against EC2

---

### Phase 2: Backend Recording (Week 2)
**Goal:** Implement recording upload and validation on backend

**Tasks:**
1. Create audio validation service
2. Add recording upload endpoint
3. Implement format conversion with ffmpeg
4. Add storage cleanup background task
5. Write unit tests for validation

**Deliverables:**
- [ ] `/recordings/upload` endpoint working
- [ ] Format conversion tested (WebM → MP3)
- [ ] Storage cleanup scheduled
- [ ] 80% unit test coverage

**Success Criteria:**
- Upload 60MB MP3 succeeds
- Upload 70MB file fails with error
- WebM file converted to MP3
- Old recordings deleted after 7 days

---

### Phase 3: Frontend Recording (Week 3)
**Goal:** Implement recording UI and browser integration

**Tasks:**
1. Create AudioRecorder component
2. Implement MediaRecorder API wrapper
3. Add waveform visualization
4. Integrate with sidebar UI
5. Write component tests

**Deliverables:**
- [ ] Recording button in sidebar
- [ ] Modal recording interface
- [ ] Waveform visualization
- [ ] Preview playback
- [ ] 75% component test coverage

**Success Criteria:**
- User can record 30-second audio
- Recording displays waveform
- Preview playback works
- Recording uploaded to backend

---

### Phase 4: Integration & E2E Testing (Week 4)
**Goal:** End-to-end validation and browser automation

**Tasks:**
1. Write E2E tests for all 5 critical flows
2. Test recording feature end-to-end
3. Validate across Chrome, Firefox, Safari
4. Load testing with 10 concurrent users
5. Performance profiling

**Deliverables:**
- [ ] 5 critical flows tested
- [ ] Recording E2E test passing
- [ ] Cross-browser validation report
- [ ] Performance test results

**Success Criteria:**
- All E2E tests pass on 3 browsers
- Recording → Generation flow <2 minutes
- No memory leaks after 100 recordings
- EC2 CPU <60% under load

---

### Phase 5: Production Deployment (Week 5)
**Goal:** Deploy to EC2 and monitor

**Tasks:**
1. Create deployment checklist
2. Deploy to EC2 with feature flag (off)
3. Enable feature flag for testing
4. Monitor metrics for 48 hours
5. Enable for all users

**Deliverables:**
- [ ] Feature deployed to EC2
- [ ] Monitoring dashboard set up
- [ ] Rollback plan tested
- [ ] User documentation updated

**Success Criteria:**
- Zero production incidents
- <5% error rate on recording uploads
- Disk usage <50%
- User feedback positive (>4/5 stars)

---

## 7. Success Metrics

### Technical Metrics

| Metric | Target | Measurement | Frequency |
|--------|--------|-------------|-----------|
| Recording success rate | >95% | (successful uploads / total attempts) | Daily |
| Format conversion success | 100% | (conversions succeeded / total conversions) | Daily |
| Storage usage | <50GB | `du -sh data/recordings` | Daily |
| E2E test pass rate | 100% | Test suite results | On every commit |
| API response time | <2s | `/recordings/upload` endpoint | Real-time |
| Browser compatibility | 3 browsers | Chrome, Firefox, Safari | Weekly |
| Security vulnerabilities | 0 critical | OWASP scan | Weekly |

### User Experience Metrics

| Metric | Target | Measurement | Frequency |
|--------|--------|-------------|-----------|
| Recording UI load time | <1s | Time to interactive | Real-time |
| Recording start latency | <500ms | Permission → start | Real-time |
| Recording stop latency | <200ms | Stop click → blob ready | Real-time |
| Error message clarity | >4/5 | User survey | Monthly |
| Feature adoption rate | >30% | % users who use recording | Weekly |

### Business Metrics

| Metric | Target | Measurement | Frequency |
|--------|--------|-------------|-----------|
| User retention | +10% | Users returning after recording | Monthly |
| Session duration | +15% | Average time on platform | Weekly |
| Feature usage | >500/week | Total recordings created | Weekly |
| Support tickets | <10/week | Recording-related issues | Weekly |

---

## 8. Dependencies & Prerequisites

### System Requirements

**EC2 Instance:**
- Ubuntu 20.04 or 22.04
- Minimum 4GB RAM (8GB recommended with recording)
- 100GB disk (for recordings + stems)
- ffmpeg installed (`apt-get install ffmpeg`)

**Local Development:**
- Python 3.11+
- Node.js 18+
- npm 9+
- ffmpeg

**Browser Support:**
- Chrome 47+ (recommended)
- Firefox 25+
- Safari 14.1+

### External Dependencies

**API Keys Required:**
- OpenAI API key (GPT-4o)
- ElevenLabs API key (voice synthesis)
- Suno API key (music generation)
- Genius API token (artist search)

**Python Packages:**
- See requirements.txt (all already installed)
- New: `pydub>=0.25.1` (already present)

**Node Packages:**
- See frontend-nextjs/package.json
- No new dependencies required (MediaRecorder is native)

---

## 9. Open Questions & Decisions Needed

### Technical Decisions

1. **Recording Format Preference:**
   - **Question:** WebM (Chrome), Ogg (Firefox), or MP4 (Safari)?
   - **Recommendation:** Server normalizes all → MP3 128kbps
   - **Decision:** ✅ Approved

2. **Storage Location:**
   - **Question:** Local disk vs S3 for recordings?
   - **Recommendation:** Local disk for MVP, S3 for scale
   - **Decision:** ⏳ Pending cost analysis

3. **Maximum Recording Duration:**
   - **Question:** 5 minutes or 10 minutes?
   - **Recommendation:** 8 minutes (360MB at 128kbps)
   - **Decision:** ⏳ Needs user research

4. **Real-time Compression:**
   - **Question:** Compress during recording or after?
   - **Recommendation:** After (simpler, browser-agnostic)
   - **Decision:** ✅ Approved

### Product Decisions

1. **Mobile Support:**
   - **Question:** Support mobile recording in Phase 1?
   - **Recommendation:** No, desktop-only for Phase 1
   - **Decision:** ⏳ Needs product review

2. **Recording Library:**
   - **Question:** Should users see past recordings in Library?
   - **Recommendation:** Yes, separate "Recordings" section
   - **Decision:** ⏳ Needs design mockups

3. **Collaboration Features:**
   - **Question:** Allow sharing recordings between users?
   - **Recommendation:** No, single-user system for now
   - **Decision:** ✅ Approved

---

## 10. Timeline & Milestones

```
Week 1 (Foundation)
├─ Day 1-2: Local testing validation
├─ Day 3-4: E2E test setup
└─ Day 5: Security audit

Week 2 (Backend)
├─ Day 1-2: Audio validation service
├─ Day 3-4: Recording endpoint
└─ Day 5: Unit tests

Week 3 (Frontend)
├─ Day 1-2: Recording component
├─ Day 3-4: UI integration
└─ Day 5: Component tests

Week 4 (Testing)
├─ Day 1-2: E2E test suite
├─ Day 3-4: Cross-browser testing
└─ Day 5: Load testing

Week 5 (Deployment)
├─ Day 1-2: EC2 deployment
├─ Day 3-4: Feature flag rollout
└─ Day 5: Monitoring & optimization
```

**Critical Path:** Week 2 → Week 3 → Week 4 (sequential dependencies)  
**Parallelizable:** Security audit can run parallel to development  
**Slack Time:** 3 days buffer for unexpected issues

---

## 11. Contact & Escalation

### Team Structure

| Role | Responsibility | Contact |
|------|----------------|---------|
| **Architect** | Overall design, risk assessment | This agent |
| **Feature Agent** | Frontend + backend implementation | TBD |
| **QA Agent** | E2E testing, browser automation | TBD |
| **Security Agent** | Security review, vulnerability scanning | TBD |
| **DevOps Agent** | Deployment, monitoring, rollbacks | TBD |

### Escalation Path

**Level 1 (Minor):** Agent self-resolves  
**Level 2 (Moderate):** Architect review required  
**Level 3 (Major):** All-hands sync meeting  
**Level 4 (Critical):** Production incident → immediate rollback

---

## 12. Appendix

### A. Reference Links

- [MediaRecorder API Docs](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder)
- [Playwright Testing Guide](https://playwright.dev/docs/intro)
- [FastAPI File Uploads](https://fastapi.tiangolo.com/tutorial/request-files/)
- [ffmpeg Audio Conversion](https://ffmpeg.org/ffmpeg.html#Audio-Options)

### B. Code Snippets

**Browser Permission Check:**
```typescript
async function checkMicrophonePermission(): Promise<boolean> {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    stream.getTracks().forEach(track => track.stop())
    return true
  } catch (error) {
    if (error.name === 'NotAllowedError') {
      return false
    }
    throw error
  }
}
```

**Server-side Format Conversion:**
```python
import subprocess
from pathlib import Path

def convert_to_mp3(input_path: Path, output_path: Path) -> bool:
    """Convert audio file to MP3 128kbps 44.1kHz using ffmpeg."""
    try:
        subprocess.run([
            'ffmpeg', '-i', str(input_path),
            '-acodec', 'libmp3lame', '-ab', '128k', '-ar', '44100',
            '-y', str(output_path)
        ], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False
```

### C. Test Data

**Audio Samples for Testing:**
- `tests/e2e/fixtures/audio-samples/test-song-30s.mp3` (30 seconds, 500KB)
- `tests/e2e/fixtures/audio-samples/test-song-5min.mp3` (5 minutes, 5MB)
- `tests/e2e/fixtures/audio-samples/test-oversized.mp3` (65MB, should fail)
- `tests/e2e/fixtures/audio-samples/test-invalid.txt` (invalid format, should fail)

---

## Change Log

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2026-04-27 | 1.0 | Initial implementation plan | Architect Agent |

---

**Document Status:** ✅ Ready for Review  
**Next Steps:** Team review → approve → assign agents → begin Phase 1  
**Estimated Total Effort:** 5 weeks (1 architect + 4 implementation agents)
