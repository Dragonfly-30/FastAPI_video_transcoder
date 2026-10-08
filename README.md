# Video Transcoder Service (v1: Async Pipeline Foundation)

A decoupled, asynchronous video transcoding backend built with **FastAPI**, **MinIO (S3-compatible object storage)**, **PostgreSQL (SQLAlchemy)**, **Celery & Redis**, and **FFmpeg**.

> [!NOTE]
> **Project Scope Statement:**
> This repository represents **v1** of an asynchronous video processing backend. It establishes a clean, decoupled architecture (direct-to-storage presigned uploads, isolated worker queues, multi-container orchestration, and automated media validation), while serving as the architectural foundation for a future enterprise-grade Adaptive Bitrate Streaming (HLS/DASH) platform.

---

## Architecture Overview

```
                      ┌───────────────────────────────────────┐
                      │             API Client                │
                      └───────┬───────────────────────┬───────┘
                              │ 1. Request PUT URL    │ 4. Poll status
                              │ 3. Submit Job         │
                              ▼                       ▼
                      ┌───────────────────────────────────────┐
                      │         FastAPI Web Service           │
                      │        (app/api & app/services)       │
                      └───┬───────────────────────────────┬───┘
                          │                               │
       2. Direct PUT      │ Generates Presigned URLs      │ Enqueues Task
       (Zero API load)    │                               │
              ▼           ▼                               ▼
    ┌───────────────────────────┐               ┌──────────────────┐
    │       MinIO Storage       │               │   Redis Broker   │
    │  raw/ & transcoded/ keys  │               └────────┬─────────┘
    └─────────────▲─────────────┘                        │ Consumes Task
                  │                                      ▼
                  │ Upload result /             ┌──────────────────┐
                  │ Download input              │  Celery Worker   │
                  │                             │ (FFmpeg/FFprobe) │
                  └─────────────────────────────┤                  │
                                                │ Isolated Scratch │
                                                │      Space       │
                                                └────────┬─────────┘
                                                         │ Updates State
                                                         ▼
                                                ┌──────────────────┐
                                                │    PostgreSQL    │
                                                │ transcoding_jobs │
                                                └──────────────────┘
```

---

## Key Engineering Decisions in v1

### 1. Direct-to-Storage Ingestion (Presigned URLs)
- **Problem:** Streaming gigabyte video files through an API server exhausts memory, blocks worker threads, and degrades latency for all users.
- **Solution:** Clients request a short-lived cryptographic Presigned `PUT` URL from `/api/v1/uploads/presigned-url` and upload raw video directly to MinIO. The FastAPI server never handles raw video payloads.

### 2. Decoupled CPU-Intensive Worker (Celery + Redis)
- **Problem:** Video transcoding with FFmpeg is CPU-heavy and long-running. Using in-process background tasks (`FastAPI.BackgroundTasks`) starves the event loop, drops jobs on server restart, and prevents horizontal scaling.
- **Solution:** The API dispatches jobs to a persistent Redis message broker in `< 2ms`. Dedicated Celery workers execute the transcoding in separate, independently scalable process containers.

### 3. Media Integrity Validation (FFprobe)
- **Pre-validation:** Before attempting a transcode, the worker inspects the input file using `ffprobe`. Corrupted uploads, empty files, or non-video formats are rejected in milliseconds without wasting CPU cycles.
- **Post-validation:** After transcoding, the output file is validated with `ffprobe` to ensure valid playable audio/video streams exist and size > 0 before uploading to MinIO.

### 4. Web Progressive Streaming (`-movflags +faststart` & MOOV Atom)

#### Understanding MP4 Container Anatomy:
An MP4 container is composed of discrete data blocks called **atoms** (or boxes):
- **`mdat` (Media Data):** Contains the raw audio and video payload bytes (usually 99% of the file size).
- **`moov` (Movie Metadata):** Contains the index table of sample timestamps, keyframe offsets, audio sync, and codec parameters. A player **must** read the `moov` atom to decode and begin playback.

```
Standard FFmpeg Output (Problematic for Web):
┌─────────────────────────────────────────────────────────────┬───────────┐
│              mdat (Media Payload - 500 MB)                  │ moov (1MB)│
└─────────────────────────────────────────────────────────────┴───────────┘
▲                                                                         ▲
Browser downloads byte 0... must download all 500MB before finding index ─┘
(Player hangs buffering until the ENTIRE file is downloaded)

Faststart Relocated Output (-movflags +faststart):
┌───────────┬─────────────────────────────────────────────────────────────┐
│ moov (1MB)│              mdat (Media Payload - 500 MB)                  │
└───────────┴─────────────────────────────────────────────────────────────┘
▲
Browser reads first 1MB index -> starts rendering video immediately while downloading rest.
```

By applying `-movflags +faststart`, FFmpeg executes a second pass relocating the `moov` atom to the very beginning of the file, enabling instant progressive playback in HTML5 video players.

### 5. Safe Scratch Space Isolation
- Each Celery transcoding task runs inside a dedicated `tempfile.TemporaryDirectory()`. Input and intermediate outputs are completely isolated.
- A `finally` block guarantees that the scratch directory is wiped from disk on completion or failure, preventing disk saturation.

### 6. Clean Layered Architecture
- **API Layer (`app/api/`):** Thin controllers validating input and returning standardized DTOs.
- **Service Layer (`app/services/`):** Business logic, transaction boundaries, and Celery dispatch.
- **Repository Layer (`app/repositories/`):** Encapsulates SQLAlchemy database queries.
- **Domain Models (`app/models/`):** `TranscodingJob` table with GUID primary keys, enums, and timestamps.
- **Worker (`app/worker/`):** FFmpeg subprocess wrapper and Celery task definitions.

---

## Current Scope (v1) vs. Production-Grade Reality

A critical aspect of professional software engineering is recognizing the boundary between a functional foundation and a large-scale production system. Here is an honest comparison of where v1 stands and what is required for true enterprise scale:

| Dimension | v1 Implementation | Enterprise Production Requirement |
| :--- | :--- | :--- |
| **Packaging & Format** | Single monolithic `.mp4` file | **HLS / MPEG-DASH:** Master playlist (`.m3u8`) with fragmented media segments (`.ts` / `.m4s`). |
| **Streaming Delivery** | Progressive HTTP download | **Adaptive Bitrate Streaming (ABR):** Player dynamically switches qualities (360p $\leftrightarrow$ 1080p) based on real-time network bandwidth. |
| **Transcoding Granularity** | Whole file per worker process | **Distributed Keyframe Chunking:** Slicing long videos into 5s segments across a fleet of workers and stitching manifests. |
| **Quality Profiles** | Single target resolution requested | **Full Encoding Ladder:** Generates 360p, 480p, 720p, and 1080p simultaneously from a single master upload. |
| **Client Notifications** | Polling endpoint (`GET /jobs/{id}`) | **Webhooks & Event Bus:** HMAC-signed HTTP push notifications to subscriber endpoints, with Kafka/SNS event streams. |
| **Hardware Compute** | Software CPU encoding (`libx264`) | **Hardware Acceleration:** GPU-assisted encoding (`h264_nvenc` on NVIDIA, QuickSync on Intel). |
| **Worker Scaling** | Fixed Celery worker container | **Autoscaling Fleet (KEDA):** Automatically scales worker pods from 1 to 50 based on Redis queue depth. |
| **Security & Auth** | Unauthenticated public endpoints | **OAuth2 / JWT Auth:** Tenant isolation, upload quota enforcement, and rate limiting. |

---

## Production Roadmap (v2 & Future Milestones)

To evolve this project into an enterprise-grade video pipeline (similar to Mux or AWS MediaConvert), the following milestones are planned:

- [ ] **Milestone 1: HLS Adaptive Bitrate (ABR) Pipeline**
  - Update FFmpeg to generate multi-variant HLS playlists (`master.m3u8`) and segmented chunks (`360p.m3u8`, `720p.m3u8`, `segment_001.ts`).
  - Store segmented output folders in MinIO and generate manifest URLs for modern video players (e.g., Video.js, HLS.js).
- [ ] **Milestone 2: Webhook Event Dispatcher**
  - Add optional `webhook_url` and `webhook_secret` to `JobCreateRequest`.
  - Dispatch signed HTTP POST callbacks (`transcode.completed`, `transcode.failed`) upon job termination with exponential backoff retries.
- [ ] **Milestone 3: Distributed Segment Chunking**
  - For files exceeding 10 minutes, segment video at keyframes, dispatch chunks across Celery worker pools in parallel, and assemble master playlist.
- [ ] **Milestone 4: GPU Acceleration & Autoscaling**
  - Add NVIDIA container toolkit support (`h264_nvenc`).
  - Add Kubernetes deployment with KEDA to scale Celery workers dynamically based on Redis task queue length.
- [ ] **Milestone 5: Auth & Rate Limiting**
  - Implement API Key authentication and per-tenant concurrency limits.

---

## API Specification

### 1. Request Upload Presigned URL
`POST /api/v1/uploads/presigned-url`

**Request:**
```json
{
  "filename": "demo_video.mp4"
}
```

**Response (`200 OK`):**
```json
{
  "upload_url": "http://localhost:9000/transcoder-videos/raw/7d3a8b.../demo_video.mp4?...",
  "object_key": "raw/7d3a8b.../demo_video.mp4"
}
```

---

### 2. Upload Video to MinIO (Direct HTTP PUT)
Upload the raw video file directly using `curl`:
```bash
curl -X PUT -T "demo_video.mp4" "<upload_url>"
```

---

### 3. Create Transcoding Job
`POST /api/v1/jobs`

**Request:**
```json
{
  "original_filename": "demo_video.mp4",
  "input_key": "raw/7d3a8b.../demo_video.mp4",
  "target_quality": "720p"
}
```

**Response (`201 Created`):**
```json
{
  "id": "e4b2d358-1a2f-4889-a292-6dcfb9409b8d",
  "original_filename": "demo_video.mp4",
  "target_quality": "720p",
  "status": "pending",
  "input_key": "raw/7d3a8b.../demo_video.mp4",
  "output_key": null,
  "download_url": null,
  "error_message": null,
  "created_at": "2026-10-08T18:30:00Z",
  "updated_at": "2026-10-08T18:30:00Z"
}
```

---

### 4. Poll Job Status
`GET /api/v1/jobs/{job_id}`

**Response while Processing (`200 OK`):**
```json
{
  "id": "e4b2d358-1a2f-4889-a292-6dcfb9409b8d",
  "status": "processing",
  ...
}
```

**Response when Completed (`200 OK`):**
```json
{
  "id": "e4b2d358-1a2f-4889-a292-6dcfb9409b8d",
  "original_filename": "demo_video.mp4",
  "target_quality": "720p",
  "status": "completed",
  "input_key": "raw/7d3a8b.../demo_video.mp4",
  "output_key": "transcoded/e4b2d358-1a2f-4889-a292-6dcfb9409b8d/720p_demo_video.mp4",
  "download_url": "http://localhost:9000/transcoder-videos/transcoded/.../720p_demo_video.mp4?...",
  "error_message": null,
  "created_at": "2026-10-08T18:30:00Z",
  "updated_at": "2026-10-08T18:30:15Z"
}
```

---

## Quick Start with Docker Compose

### Prerequisites
- Docker & Docker Compose installed.

### 1. Start All Services
```bash
docker compose up --build
```
This spins up:
- **FastAPI API:** [http://localhost:8000/docs](http://localhost:8000/docs) (Interactive Swagger UI)
- **MinIO Console:** [http://localhost:9001](http://localhost:9001) (`user: minioadmin`, `pass: minioadmin`)
- **Celery Worker:** Running in its own container with FFmpeg installed.
- **PostgreSQL:** Running on port `5432`.
- **Redis:** Running on port `6379`.

### 2. Verify Health
```bash
curl http://localhost:8000/health
# {"status":"healthy","service":"Video Transcoder API"}
```

---

## Running Locally (Without Docker)

### 1. Install Dependencies
```bash
uv pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
```

### 3. Run Test Suite
```bash
uv run pytest
```
All unit and integration tests run against thread-safe, in-memory SQLite and mocked S3/FFmpeg calls:
```text
======================== 26 passed, 1 warning in 1.15s =========================
```

### 4. Run API Server
```bash
uvicorn main:app --reload --port 8000
```

### 5. Run Celery Worker
```bash
celery -A app.core.celery_app worker --loglevel=info
```
