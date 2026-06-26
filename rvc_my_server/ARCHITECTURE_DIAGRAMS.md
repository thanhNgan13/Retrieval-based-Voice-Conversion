# Sơ Đồ Kiến Trúc Hệ Thống RVC Server

## Mục Lục

1. [Tổng Quan Hệ Thống](#1-tổng-quan-hệ-thống)
2. [Use Case Diagram](#2-use-case-diagram)
   - [Use Case: Training Flow](#21-use-case-training-flow)
   - [Use Case: Inference Flow](#22-use-case-inference-flow)
3. [Sequence Diagram](#3-sequence-diagram)
   - [Training: Upload Audio](#31-sequence-upload-audio-training)
   - [Training: Tạo & Thực Thi Job](#32-sequence-tạo--thực-thi-training-job)
   - [Training: Theo Dõi Tiến Trình (WebSocket)](#33-sequence-theo-dõi-tiến-trình-websocket)
   - [Inference: Direct Voice Conversion](#34-sequence-direct-voice-conversion)
   - [Song Inference: Full Pipeline](#35-sequence-song-inference-full-pipeline)
   - [Inference: Audio Mixing](#36-sequence-audio-mixing)

---

## 1. Tổng Quan Hệ Thống

```
┌─────────────────────────────────────────────────────────────────────┐
│                        RVC My Server                                │
│                                                                     │
│  ┌─────────────┐   ┌──────────────┐   ┌────────────────────────┐   │
│  │  Train API  │   │  Infer API   │   │   Song Infer API       │   │
│  │  (FastAPI)  │   │  (FastAPI)   │   │   (FastAPI)            │   │
│  └──────┬──────┘   └──────┬───────┘   └──────────┬─────────────┘   │
│         │                 │                       │                 │
│  ┌──────▼──────────────────▼───────────────────────▼─────────────┐  │
│  │                  Job Scheduler (Async Loop)                    │  │
│  │         [VRAM Budget Management + Redis Allocation]            │  │
│  └──────────────────────────┬────────────────────────────────────┘  │
│                             │                                       │
│  ┌──────────────────────────▼────────────────────────────────────┐  │
│  │                   Celery Workers (Redis)                       │  │
│  │  ┌──────────────────┐    ┌──────────────────────────────────┐ │  │
│  │  │ train_rvc_model  │    │     infer_song_cover             │ │  │
│  │  │     _task        │    │         _task                    │ │  │
│  │  └──────────────────┘    └──────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  External: Firebase Storage | Firestore | Redis Pub/Sub            │
└─────────────────────────────────────────────────────────────────────┘
```

**Deployment Roles:**
| Role | Mục đích | GPU | Nền tảng |
|------|----------|-----|----------|
| `all` | Toàn bộ hệ thống | Có | VM với GPU |
| `light` | API only, không infer | Không | Cloud Run (CPU) |
| `infer` | Chỉ infer/separation | Có | Cloud Run (GPU) |

---

## 2. Use Case Diagram

### 2.1 Use Case: Training Flow

```mermaid
graph TD
    User(["👤 User"])
    Admin(["🔑 Admin"])
    System(["⚙️ Celery Worker"])

    subgraph UC_Training ["🎓 Training System"]
        UC1["Đăng ký / Đăng nhập"]
        UC2["Upload file âm thanh training"]
        UC3["Xem danh sách file đã upload"]
        UC4["Xoá file đã upload"]
        UC5["Tạo Training Job"]
        UC6["Xem danh sách Training Job"]
        UC7["Xem chi tiết Training Job"]
        UC8["Theo dõi tiến trình (WebSocket)"]
        UC9["Retry Training Job thất bại"]
        UC10["Xem danh sách model đã train"]
        UC11["Xem chi tiết / Download model"]

        subgraph Background ["⚙️ Background Processing"]
            UC12["Lên lịch & phân bổ VRAM"]
            UC13["Tiền xử lý âm thanh"]
            UC14["Trích xuất F0 (Pitch)"]
            UC15["Trích xuất Hubert Features"]
            UC16["Train GAN Model"]
            UC17["Build FAISS Index"]
            UC18["Lưu model lên Storage"]
        end
    end

    User --> UC1
    User --> UC2
    User --> UC3
    User --> UC4
    User --> UC5
    User --> UC6
    User --> UC7
    User --> UC8
    User --> UC9
    User --> UC10
    User --> UC11

    UC5 -.->|"triggers"| UC12
    System --> UC12
    UC12 -.->|"dispatches"| UC13
    UC13 -.->|"next"| UC14
    UC14 -.->|"next"| UC15
    UC15 -.->|"next"| UC16
    UC16 -.->|"next"| UC17
    UC17 -.->|"next"| UC18
    UC18 -.->|"creates"| UC10

    Admin --> UC1
    Admin -.->|"manage"| UC12

    style UC_Training fill:#f0f8ff,stroke:#4a90d9
    style Background fill:#fff3e0,stroke:#ff9800
```

### 2.2 Use Case: Inference Flow

```mermaid
graph TD
    User(["👤 User"])
    System(["⚙️ Celery Worker"])

    subgraph UC_Infer ["🎵 Inference System"]
        UC1["Đăng nhập"]
        UC2["Kiểm tra trạng thái GPU (torch-status)"]

        subgraph DirectInfer ["🎤 Direct Voice Conversion"]
            UC3["Chọn model RVC (public/private)"]
            UC4["Upload file âm thanh đầu vào"]
            UC5["Cấu hình tham số conversion"]
            UC6["Thực hiện chuyển giọng trực tiếp"]
            UC7["Tải file kết quả"]
        end

        subgraph MixInfer ["🎛️ Audio Mixing"]
            UC8["Upload vocal chính đã convert"]
            UC9["Upload vocal phụ (tuỳ chọn)"]
            UC10["Upload nhạc nền (tuỳ chọn)"]
            UC11["Cấu hình hiệu ứng âm thanh"]
            UC12["Mix âm thanh"]
            UC13["Tải bản mix kết quả"]
        end

        subgraph SongInfer ["🎼 Song Inference (Full Pipeline)"]
            UC14["Upload bài hát / Chọn bài có sẵn"]
            UC15["Chọn model RVC"]
            UC16["Cấu hình tham số"]
            UC17["Tạo Song Infer Job"]
            UC18["Theo dõi tiến trình (WebSocket)"]
            UC19["Xem danh sách Job"]
            UC20["Xem danh sách Cover đã tạo"]
            UC21["Tải các file output"]

            subgraph BgSong ["⚙️ Background Pipeline"]
                UC22["Tách vocal/nhạc nền (MDX-Net)"]
                UC23["Tách vocal chính/phụ"]
                UC24["Loại bỏ reverb (De-reverb)"]
                UC25["Chuyển giọng (RVC Engine)"]
                UC26["Mix âm thanh cuối"]
                UC27["Upload kết quả lên Storage"]
            end
        end
    end

    User --> UC1
    User --> UC2
    User --> UC3
    User --> UC4
    User --> UC5
    UC5 -.->|"extends"| UC6
    UC6 -.->|"produces"| UC7

    User --> UC8
    User --> UC9
    User --> UC10
    User --> UC11
    UC11 -.->|"extends"| UC12
    UC12 -.->|"produces"| UC13

    User --> UC14
    User --> UC15
    User --> UC16
    UC16 -.->|"triggers"| UC17
    User --> UC18
    User --> UC19
    User --> UC20
    User --> UC21

    System --> UC22
    UC17 -.->|"dispatches"| UC22
    UC22 -.->|"next"| UC23
    UC23 -.->|"next"| UC24
    UC24 -.->|"next"| UC25
    UC25 -.->|"next"| UC26
    UC26 -.->|"next"| UC27
    UC27 -.->|"updates"| UC20

    style UC_Infer fill:#f0fff4,stroke:#38a169
    style DirectInfer fill:#e6fffa,stroke:#319795
    style MixInfer fill:#faf5ff,stroke:#805ad5
    style SongInfer fill:#fff5f5,stroke:#e53e3e
    style BgSong fill:#fff3e0,stroke:#ff9800
```

---

## 3. Sequence Diagram

### 3.1 Sequence: Upload Audio (Training)

```mermaid
sequenceDiagram
    actor Client
    participant API as FastAPI<br/>(Train Routes)
    participant Auth as Auth Middleware
    participant Service as Train Service
    participant FS as Firestore
    participant Storage as Firebase Storage

    Client->>+API: POST /train-services/upload-urls<br/>{fileNames, fileTypes}
    API->>+Auth: Verify JWT Token
    Auth-->>-API: userId
    API->>+Service: generate_upload_urls(userId, fileNames)
    
    loop Mỗi file
        Service->>+Storage: Generate Signed PUT URL<br/>(train_uploads/{userId}/...)
        Storage-->>-Service: signedPutUrl
        Service->>+FS: Create AudioUpload document<br/>{audioUploadId, objectPath, userId}
        FS-->>-Service: audioUploadId
    end
    
    Service-->>-API: [{audioUploadId, uploadUrl, objectPath}]
    API-->>-Client: 200 OK - Upload URLs

    Note over Client,Storage: Client tự upload file trực tiếp lên Storage
    
    Client->>+Storage: PUT signedPutUrl (audio file binary)
    Storage-->>-Client: 200 OK

    Client->>+API: GET /train-services/uploads
    API->>+Auth: Verify JWT Token
    Auth-->>-API: userId
    API->>+Service: list_audio_uploads(userId)
    Service->>+FS: Query audioUploads where user_id == userId
    FS-->>-Service: [AudioUploadModel]
    
    loop Mỗi upload
        Service->>+Storage: Generate Signed Download URL
        Storage-->>-Service: signedDownloadUrl
    end
    
    Service-->>-API: [AudioUploadPublicView]
    API-->>-Client: 200 OK - Danh sách uploads
```

---

### 3.2 Sequence: Tạo & Thực Thi Training Job

```mermaid
sequenceDiagram
    actor Client
    participant API as FastAPI<br/>(Train Routes)
    participant Service as Train Service
    participant FS as Firestore
    participant Scheduler as Job Scheduler<br/>(Async Loop)
    participant Redis as Redis<br/>(Broker + PubSub)
    participant Celery as Celery Worker
    participant Pipeline as RVC Train Pipeline
    participant Storage as Firebase Storage

    Client->>+API: POST /train-services/jobs<br/>{audioUploadIds, params...}
    API->>+Service: create_train_job(userId, request)

    Service->>+FS: Validate audioUploadIds (ownership check)
    FS-->>-Service: [objectPaths]

    Service->>+FS: Create TrainJob document<br/>{status="queued", stage=null, progress=0}
    FS-->>-Service: trainJobId

    Service-->>-API: TrainJobPublicView
    API-->>-Client: 201 Created {trainJobId}

    Note over Scheduler: Chạy vòng lặp mỗi 3s hoặc nhận trigger từ Redis

    loop Scheduler tick
        Scheduler->>+FS: Fetch jobs where status="queued"<br/>(train + infer, sort by created_at)
        FS-->>-Scheduler: [queued jobs]

        loop Mỗi job (FIFO)
            Scheduler->>+Redis: WATCH/MULTI/EXEC<br/>try_allocate(jobId, TRAIN_JOB_VRAM_MB)
            Redis-->>-Scheduler: allocated / not enough VRAM
            
            alt VRAM đủ
                Scheduler->>+Celery: send_task("train_rvc_model_task", [trainJobId])
                Celery-->>-Scheduler: task dispatched
            else Không đủ VRAM
                Scheduler->>Scheduler: Skip, thử lại tick tiếp theo
            end
        end
    end

    Celery->>+Pipeline: execute_train_job(trainJobId)
    Pipeline->>+FS: Update status="running"
    FS-->>-Pipeline: OK

    Note over Pipeline,Storage: 8 Stages thực thi tuần tự

    Pipeline->>+Storage: Download audio files từ train_uploads/
    Storage-->>-Pipeline: audio files

    Pipeline->>Pipeline: Stage 1 - Preprocess (10%)<br/>Resample + Slice → 0_gt_wavs/
    Pipeline->>+FS: Update progress=10, stage="preprocess"
    FS-->>-Pipeline: OK
    Pipeline->>+Redis: Publish progress to rvc_train_job:{id}
    Redis-->>-Pipeline: OK

    Pipeline->>Pipeline: Stage 2 - Extract F0 (25%)<br/>Pitch curve → 2a_f0/ & 2b-f0nsf/
    Pipeline->>+Redis: Publish progress=25
    Redis-->>-Pipeline: OK

    Pipeline->>Pipeline: Stage 3 - Extract Hubert Features (40%)<br/>768D vectors → 3_feature768/
    Pipeline->>+Redis: Publish progress=40
    Redis-->>-Pipeline: OK

    Pipeline->>Pipeline: Stage 4 - Write Filelist (45%)<br/>Match samples → filelist.txt
    Pipeline->>+Redis: Publish progress=45
    Redis-->>-Pipeline: OK

    Pipeline->>Pipeline: Stage 5 - Train GAN (55-80%)<br/>Generator + Discriminator epochs
    
    loop Mỗi epoch
        Pipeline->>+Redis: Publish epoch progress
        Redis-->>-Pipeline: OK
    end

    Pipeline->>Pipeline: Stage 6 - Extract Small Model (80%)<br/>Quantize/Prune → model.pth
    Pipeline->>+Storage: Upload model.pth<br/>user_rvc_model/{userId}/{modelId}/model.pth
    Storage-->>-Pipeline: OK
    Pipeline->>+Redis: Publish progress=80
    Redis-->>-Pipeline: OK

    Pipeline->>Pipeline: Stage 7 - Build FAISS Index (90%)<br/>Concat features + KMeans + IVF index
    Pipeline->>+Storage: Upload model.index<br/>user_rvc_model/{userId}/{modelId}/model.index
    Storage-->>-Pipeline: OK
    Pipeline->>+Redis: Publish progress=90
    Redis-->>-Pipeline: OK

    Pipeline->>Pipeline: Stage 8 - Finalize (95-100%)
    Pipeline->>+FS: Create UserRVCModel document<br/>{rvcModelId, model_path, index_path, visibility="private"}
    FS-->>-Pipeline: rvcModelId

    Pipeline->>+FS: Update TrainJob {status="succeeded", rvc_model_id, progress=100}
    FS-->>-Pipeline: OK

    Pipeline->>+Redis: Publish terminal message
    Redis-->>-Pipeline: OK

    Pipeline->>+Redis: release(trainJobId) + trigger_scheduler
    Redis-->>-Pipeline: OK
    Pipeline-->>-Celery: Task completed
```

---

### 3.3 Sequence: Theo Dõi Tiến Trình (WebSocket)

```mermaid
sequenceDiagram
    actor Client
    participant WS as WebSocket Handler<br/>(FastAPI)
    participant Redis as Redis PubSub<br/>rvc_train_job:{id}
    participant FS as Firestore<br/>(Fallback)

    Client->>+WS: WS /train-services/jobs/{trainJobId}/ws<br/>(JWT in header/query)
    WS->>WS: Verify JWT, get userId
    WS->>WS: Verify job ownership

    WS->>+FS: Get current job snapshot
    FS-->>-WS: TrainJobModel
    WS-->>Client: {"type": "snapshot", "data": {...}}

    WS->>+Redis: SUBSCRIBE rvc_train_job:{trainJobId}
    
    par Redis Updates
        loop Khi Celery publish progress
            Redis-->>WS: progress message
            WS-->>Client: {"type": "progress", "progress": 45, "stage": "train", "message": "..."}
        end
    and Firestore Fallback (30s interval)
        loop Mỗi 30 giây (safety net)
            WS->>+FS: Get job document
            FS-->>-WS: TrainJobModel
            WS-->>Client: {"type": "snapshot", "data": {...}}
        end
    and Heartbeat
        loop Mỗi 20 giây
            WS-->>Client: {"type": "heartbeat"}
        end
    end

    alt Training hoàn thành
        Redis-->>WS: terminal message (succeeded/failed)
        WS-->>Client: {"type": "terminal", "status": "succeeded", "rvc_model_id": "..."}
        WS->>-Client: Đóng kết nối WebSocket
    else Client ngắt kết nối
        Client->>WS: Close WebSocket
        WS->>Redis: UNSUBSCRIBE
    end
```

---

### 3.4 Sequence: Direct Voice Conversion

```mermaid
sequenceDiagram
    actor Client
    participant API as FastAPI<br/>(Infer Routes)
    participant Service as Infer Service
    participant FS as Firestore
    participant Cache as Local Cache<br/>(cache/weights, cache/indices)
    participant Storage as Firebase Storage
    participant Engine as Infer Engine<br/>(RVC + PyTorch)
    participant Lock as Engine Lock<br/>(RLock)

    Client->>+API: POST /infer-services/convert<br/>{audio file, rvcModelId, f0UpKey, f0Method,<br/>indexRate, filterRadius, rmsMixRate, protect...}
    API->>+Service: convert_voice(userId, file, params)

    Service->>+FS: get_accessible_rvc_model(userId, rvcModelId)<br/>(private model hoặc public collection)
    FS-->>-Service: RVCModelModel {model_path, index_path}

    Service->>+Cache: Check cache/weights/{cacheKey}.pth
    
    alt Chưa có trong cache
        Cache-->>Service: Not found
        Service->>+Storage: Download model.pth
        Storage-->>-Service: pth binary
        Service->>Cache: Save to cache/weights/{cacheKey}.pth
    else Đã có trong cache
        Cache-->>-Service: local pth path
    end

    Service->>+Cache: Check cache/indices/{cacheKey}.index
    
    alt Chưa có trong cache
        Cache-->>Service: Not found
        Service->>+Storage: Download model.index
        Storage-->>-Service: index binary
        Service->>Cache: Save to cache/indices/{cacheKey}.index
    else Đã có trong cache
        Cache-->>-Service: local index path
    end

    Service->>+Lock: Acquire infer_engine_lock() (RLock)
    
    Note over Engine: Lazy-load torch, fairseq, librosa<br/>(chỉ lần đầu, mất 30-60s)
    
    Service->>+Engine: Load Config (CUDA query, fp16 settings)
    Engine-->>-Service: Config

    alt Model chưa được load hoặc khác model
        Service->>+Engine: vc.get_vc(pth_filename)<br/>Load .pth vào GPU/CPU
        Engine-->>-Service: VC ready
    end

    Service->>+Engine: vc.vc_single(audio, params)
    
    Note over Engine: RVC Algorithm:
    Engine->>Engine: 1. HuBERT: audio → 768D feature vectors
    Engine->>Engine: 2. F0 Extraction: audio → pitch curve<br/>(pm/harvest/crepe/rmvpe)
    Engine->>Engine: 3. FAISS Retrieval: find similar vectors<br/>in index (indexRate mixing)
    Engine->>Engine: 4. Generator: features + pitch + speakerId<br/>→ mel-spectrogram
    Engine->>Engine: 5. Vocoder: mel-spectrogram → waveform
    
    Engine-->>-Service: output_audio (numpy array)
    Lock-->>-Service: Release lock

    Service->>+Cache: Save output WAV locally
    Cache-->>-Service: local path

    Service->>+Storage: Upload to infer_outputs/{userId}/{conversionId}.wav
    Storage-->>-Service: objectPath

    Service->>+Storage: Generate Signed Download URL
    Storage-->>-Service: signedUrl

    Service-->>-API: {url: signedUrl, duration, ...}
    API-->>-Client: 200 OK {downloadUrl}
```

---

### 3.5 Sequence: Song Inference (Full Pipeline)

```mermaid
sequenceDiagram
    actor Client
    participant API as FastAPI<br/>(Song Infer Routes)
    participant Service as Song Infer Service
    participant FS as Firestore
    participant Storage as Firebase Storage
    participant Scheduler as Job Scheduler
    participant Redis as Redis
    participant Celery as Celery Worker
    participant Executor as Song Infer Executor
    participant Separation as Separation Service<br/>(MDX-Net ONNX)
    participant Engine as Infer Engine<br/>(RVC)
    participant Mixing as Mixing Service<br/>(Pedalboard + pydub)

    Client->>+API: POST /song-infer-services/jobs<br/>{songFile, rvcModelId, f0UpKey, f0Method,<br/>indexRate, reverbRoomSize, mainGain...}
    API->>+Service: create_song_infer_job(userId, file, params)

    Service->>+Storage: Upload song to<br/>song_infer_inputs/{userId}/{jobId}_{filename}
    Storage-->>-Service: objectPath

    Service->>+FS: Create SongInferJob document<br/>{status="queued", progress=0, rvc_model_id}
    FS-->>-Service: songInferJobId

    Service-->>-API: SongInferJobPublicView
    API-->>-Client: 201 Created {songInferJobId}

    Note over Scheduler: Scheduler phát hiện job queued

    Scheduler->>+Redis: Allocate VRAM cho job<br/>(INFER_JOB_VRAM_MB = 3072 MB)
    Redis-->>-Scheduler: allocated

    Scheduler->>+Celery: send_task("infer_song_cover_task", [songInferJobId])
    Celery-->>-Scheduler: dispatched

    Celery->>+Executor: execute_song_infer_job(songInferJobId)
    Executor->>+FS: Get job + Update status="running"
    FS-->>-Executor: SongInferJobModel

    Executor->>+Storage: Download input song
    Storage-->>-Executor: song file

    Note over Executor,Separation: STAGE 1: SEPARATION (0% → 34%)

    Executor->>+Separation: Stage 1a - Vocal/Instrumental Split (12%)
    Note over Separation: Model: UVR-MDX-NET-Voc_FT.onnx
    Separation-->>-Executor: vocals.wav, instrumental.wav

    Executor->>+Redis: Publish progress=12, stage="separation"
    Redis-->>-Executor: OK

    Executor->>+Separation: Stage 1b - Main/Backup Vocal Split (24%)
    Note over Separation: Model: UVR_MDXNET_KARA_2.onnx<br/>Input: vocals.wav
    Separation-->>-Executor: backup_vocals.wav, main_vocals.wav

    Executor->>+Redis: Publish progress=24
    Redis-->>-Executor: OK

    Executor->>+Separation: Stage 1c - De-reverberation (34%)
    Note over Separation: Model: Reverb_HQ_By_FoxJoy.onnx<br/>Input: main_vocals.wav
    Separation-->>-Executor: main_vocals_dereverb.wav

    Executor->>+Redis: Publish progress=34
    Redis-->>-Executor: OK

    Note over Executor,Engine: STAGE 2: VOICE CONVERSION (34% → 55%)

    Executor->>+Engine: Convert main_vocals_dereverb.wav<br/>(Load model → HuBERT → F0 → FAISS → Generator → Vocoder)
    Engine-->>-Executor: converted_main_vocal.wav

    Executor->>+Redis: Publish progress=55, stage="voice_conversion"
    Redis-->>-Executor: OK

    Note over Executor,Mixing: STAGE 3: MIXING (55% → 85%)

    Executor->>+Mixing: Mix audio tracks
    
    Note over Mixing: Pedalboard Effects (main vocal):
    Mixing->>Mixing: HighpassFilter()
    Mixing->>Mixing: Compressor(ratio=4, threshold=-15dB)
    Mixing->>Mixing: Reverb(roomSize, wetLevel, dryLevel, damping)
    
    Note over Mixing: pydub Overlay:
    Mixing->>Mixing: main_vocal: -4dB + mainGain
    Mixing->>Mixing: backup_vocal: -6dB + backupGain
    Mixing->>Mixing: instrumental: -7dB + instGain
    Mixing->>Mixing: Overlay all tracks → final_mix
    
    Mixing-->>-Executor: ai_vocals_wet.wav, final_mix.wav

    Executor->>+Redis: Publish progress=85, stage="mixing"
    Redis-->>-Executor: OK

    Note over Executor,Storage: STAGE 4: UPLOAD & FINALIZE (85% → 100%)

    par Upload tất cả output files
        Executor->>Storage: Upload ai_vocals_wet.wav<br/>song_infer_outputs/{userId}/{jobId}/
        Executor->>Storage: Upload ai_vocals_dry.wav
        Executor->>Storage: Upload backup_vocals.wav
        Executor->>Storage: Upload instrumental.wav
        Executor->>Storage: Upload final_mix.wav (or .mp3)
        Executor->>Storage: Upload cover.json (metadata)
    end

    Storage-->>Executor: Signed URLs cho tất cả files

    Executor->>+FS: Update SongInferJob<br/>{status="succeeded", progress=100, outputs={...urls}}
    FS-->>-Executor: OK

    Executor->>+FS: Save to ListCoverCollection (public discovery)
    FS-->>-Executor: OK

    Executor->>+Redis: Publish terminal + progress=100
    Redis-->>-Executor: OK

    Executor->>+Redis: release(jobId) + trigger_scheduler
    Redis-->>-Executor: OK
    Executor-->>-Celery: Task completed

    Note over Client,Redis: Client lắng nghe WebSocket
    Redis-->>Client: {"type": "terminal", "status": "succeeded",<br/>"outputs": {finalMix: {url, size}, ...}}
```

---

### 3.6 Sequence: Audio Mixing

```mermaid
sequenceDiagram
    actor Client
    participant API as FastAPI<br/>(Infer Routes)
    participant Service as Mixing Service<br/>(Pedalboard + pydub)
    participant Storage as Firebase Storage

    Client->>+API: POST /infer-services/mix<br/>{mainVocalFile, backupVocalFile?, instrumentalFile?,<br/>reverbRoomSize, reverbWetLevel, reverbDryLevel,<br/>reverbDamping, mainGain, backupGain, instGain,<br/>outputFormat (wav/mp3)}
    API->>+Service: mix_audio(userId, files, params)

    Service->>Service: Load audio files locally

    Note over Service: Áp dụng effects cho main vocal (Pedalboard):
    Service->>Service: HighpassFilter() — loại bỏ tần số thấp
    Service->>Service: Compressor(ratio=4, threshold_db=-15)<br/>— nén dynamic range
    Service->>Service: Reverb(roomSize, wetLevel, dryLevel, damping)<br/>— thêm không gian âm thanh

    Note over Service: Mix tracks (pydub AudioSegment):
    Service->>Service: main_vocal: normalize -4dB + mainGain dB
    
    alt Có backup vocal
        Service->>Service: backup_vocal: normalize -6dB + backupGain dB
    else Không có
        Service->>Service: backup_vocal: silent track
    end
    
    alt Có instrumental
        Service->>Service: instrumental: normalize -7dB + instGain dB
    else Không có
        Service->>Service: instrumental: silent track
    end
    
    Service->>Service: Overlay: main + backup + instrumental → final_mix

    Service->>Service: Export output (wav hoặc mp3)

    par Upload to Storage
        Service->>+Storage: Upload ai_vocals_wet.{format}<br/>mixing_outputs/{userId}/{mixingId}/
        Storage-->>-Service: url_wet
        Service->>+Storage: Upload final_mix.{format}
        Storage-->>-Service: url_final
    end

    Service->>+Storage: Generate Signed Download URLs
    Storage-->>-Service: signedUrls

    Service-->>-API: {aiVocalsWetUrl, finalMixUrl}
    API-->>-Client: 200 OK {aiVocalsWetUrl, finalMixUrl}
```

---

## Tóm Tắt Kiến Trúc

### Training Flow
```
Client → Upload URLs API → Firebase Storage (trực tiếp)
      → Create Job API → Firestore (status=queued)
      ← WebSocket ←─────────────────────────────┐
                                                 │
Scheduler (3s poll + Redis trigger)              │
      → Allocate VRAM (Redis atomic)             │
      → Celery Worker                            │
           ↓ 8 Stages:                           │
           Preprocess → Extract F0 → Hubert → Train GAN
           → Extract Model → Build FAISS Index   │
           → Upload to Storage → Update Firestore │
           → Publish to Redis PubSub ────────────┘
```

### Inference Flow
```
[Direct]  Client → Infer API → Lookup Model (Firestore)
                             → Download .pth/.index (cache)
                             → RVC Engine (HuBERT + F0 + FAISS + GAN)
                             → Upload result → Return signed URL

[Song]    Client → Song Infer API → Upload song (Storage) → Firestore (queued)
                ← WebSocket ←──────────────────────────────────────┐
          Scheduler → Celery Worker                                 │
               → MDX-Net: Vocal/Inst split → Main/Backup split     │
               → De-reverb → RVC Engine → Mixing (Pedalboard+pydub)│
               → Upload all outputs → Firestore (succeeded) ───────┘
```

```mermaid
graph TD
    %% Định nghĩa các Swimlanes
    subgraph Người_dùng ["Người dùng"]
        start1(( ))
        login["Đăng nhập"]
        upload["Chọn chức năng<br>thu âm / tải lên<br>dữ liệu giọng nói"]
        request_train["Người dùng yêu cầu<br>huấn luyện<br>mẫu giọng"]
        view_model["Xem mô hình giọng<br>đã tạo"]
        end1(( ))
        end2(( ))
    end

    subgraph Ứng_dụng_Flutter ["Ứng dụng Flutter"]
        send_audio["Gửi file<br>âm thanh"]
    end

    subgraph FastAPI_Backend ["FastAPI Backend"]
        check_data["Kiểm tra định dạng,<br>kích thước, thời lượng"]
        is_valid{"Dữ liệu<br>hợp lệ?"}
        err_msg["Trả thông báo lỗi /<br>yêu cầu thu âm lại"]
        save_metadata["Lưu file vào Storage,<br>lưu metadata<br>vào Firestore"]
        create_job["Tạo training job<br>(trạng thái: pending)"]
        push_queue["Đẩy job vào<br>Task Queue"]
    end

    subgraph Task_Queue ["Task Queue / Redis-Celery"]
        receive_queue["Nhận job<br>(trạng thái: pending<br>-> processing)"]
    end

    subgraph AI_Engine ["AI Engine"]
        receive_job["Nhận job (training)<br>(processing)"]
        preprocess["Tiền xử lý dữ liệu<br>(chuẩn hóa sample rate,<br>cắt im lặng,<br>chuẩn hóa âm lượng)"]
        extract_feat["Trích xuất đặc trưng<br>nội dung<br>(HuBERT / ContentVec)"]
        extract_f0["Trích xuất F0<br>(RMVPE / FCPE)"]
        train_rvc["Huấn luyện<br>mô hình RVC"]
        build_faiss["Xây dựng file chỉ mục<br>FAISS"]
        save_artifact["Lưu artifact mô hình<br>(.pth) và chỉ mục<br>(.index) vào Storage,<br>cập nhật trạng thái<br>vào Firestore"]
        
        is_success{"Huấn luyện<br>thành công?"}
        update_fail["Cập nhật trạng thái<br>failed, ghi log lỗi,<br>gửi thông báo thất bại"]
        update_success["Cập nhật trạng thái<br>completed, gửi<br>thông báo hoàn tất"]
    end

    subgraph Firestore_Storage ["Firestore / Storage"]
        db_save_audio["Lưu file âm thanh<br>(Storage) và<br>metadata<br>(Firestore)"]
        db_save_model["Lưu .pth, .index<br>(Storage) và<br>cập nhật trạng thái<br>(Firestore)"]
    end

    %% Luồng 1: Tải lên dữ liệu âm thanh
    start1 --> login
    login --> upload
    upload --> send_audio
    send_audio --> check_data
    check_data --> is_valid
    
    is_valid -- "Không" --> err_msg
    err_msg --> end1
    
    is_valid -- "Có" --> save_metadata
    save_metadata --> db_save_audio

    %% Luồng 2: Huấn luyện mô hình giọng
    request_train --> create_job
    create_job --> push_queue
    push_queue --> receive_queue
    receive_queue --> receive_job
    
    receive_job --> preprocess
    preprocess --> extract_feat
    extract_feat --> extract_f0
    extract_f0 --> train_rvc
    train_rvc --> build_faiss
    build_faiss --> save_artifact
    
    save_artifact --> db_save_model
    save_artifact --> is_success
    
    is_success -- "Không" --> update_fail
    is_success -- "Có" --> update_success
    
    update_fail --> view_model
    update_success --> view_model
    view_model --> end2
```