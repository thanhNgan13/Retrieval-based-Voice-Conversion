from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TrainUploadUrlFile(BaseModel):
    file_name: str = Field(
        ...,
        alias="fileName",
        min_length=1,
        max_length=255,
        description=(
            "Tên file audio gốc của user. Chỉ dùng để tạo objectPath dễ đọc; "
            "file thật sẽ được upload trực tiếp lên signed URL."
        ),
        examples=["voice_01.wav"],
    )
    content_type: str = Field(
        default="audio/wav",
        alias="contentType",
        description=(
            "MIME type của audio khi PUT lên signed URL. Phải là audio/* "
            "ví dụ audio/wav, audio/mpeg, audio/flac."
        ),
        examples=["audio/wav", "audio/mpeg", "audio/flac"],
    )

    model_config = ConfigDict(populate_by_name=True)


class CreateTrainUploadUrlsRequest(BaseModel):
    files: list[TrainUploadUrlFile] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Danh sách 1-20 audio files cần xin signed PUT URL để upload.",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "files": [
                    {"fileName": "voice_01.wav", "contentType": "audio/wav"},
                    {"fileName": "voice_02.mp3", "contentType": "audio/mpeg"},
                ]
            }
        },
    )


class CreateTrainJobRequest(BaseModel):
    title: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Tên model private sau khi train xong. Hiển thị trong danh sách model của user.",
        examples=["Giọng nữ đọc truyện"],
    )
    description: str = Field(
        default="",
        max_length=2000,
        description="Mô tả ngắn cho model private. Không ảnh hưởng chất lượng training.",
        examples=["Dataset giọng nữ, thu trong phòng yên tĩnh."],
    )
    audio_upload_ids: Optional[list[str]] = Field(
        default=None,
        alias="audioUploadIds",
        min_length=1,
        max_length=20,
        description=(
            "Danh sách 1-20 audioUploadId trả về từ POST /train-services/upload-urls. "
            "Khuyến nghị dùng field này thay vì audioObjectPaths cho request gọn hơn."
        ),
        examples=[["audio_upload_1779267563260_ac4083e7-cc7b-4c0e-9b56-e284dfc751f1"]],
    )
    audio_object_paths: Optional[list[str]] = Field(
        default=None,
        alias="audioObjectPaths",
        min_length=1,
        max_length=20,
        description=(
            "Danh sách 1-20 Storage object paths đã upload bằng signed URL từ "
            "POST /train-services/upload-urls. Path phải thuộc user hiện tại. "
            "Giữ để tương thích; nên dùng audioUploadIds."
        ),
        examples=[["train_uploads/user_123/upload_456_001_voice.wav"]],
    )
    sample_rate: Literal["32k", "40k", "48k"] = Field(
        default="40k",
        alias="sampleRate",
        description=(
            "Sample rate của model RVC output. 40k thường cân bằng tốt; "
            "32k nhẹ hơn; 48k chất lượng cao hơn nhưng nặng hơn."
        ),
        examples=["40k"],
    )
    version: Literal["v1", "v2"] = Field(
        default="v2",
        description="Phiên bản kiến trúc RVC. Nên dùng v2 cho model mới.",
        examples=["v2"],
    )
    if_f0: bool = Field(
        default=True,
        alias="ifF0",
        description=(
            "Bật nhánh pitch/F0. Nên true cho voice conversion hát/nói tự nhiên; "
            "false nhẹ hơn nhưng kiểm soát cao độ kém hơn."
        ),
    )
    f0_method: Literal["pm", "harvest", "dio", "rmvpe", "rmvpe_gpu"] = Field(
        default="rmvpe",
        alias="f0Method",
        description=(
            "Thuật toán extract pitch: pm nhanh nhưng kém chính xác; harvest/dio CPU ổn; "
            "rmvpe chất lượng tốt, phổ biến; rmvpe_gpu dùng GPU cho F0."
        ),
        examples=["rmvpe"],
    )
    total_epochs: int = Field(
        default=50,
        alias="totalEpochs",
        ge=1,
        le=1000,
        description=(
            "Tổng số epoch training. Test nhanh dùng 5-20; training thật thường 50-300 "
            "tuỳ dataset."
        ),
        examples=[50],
    )
    save_every_epoch: int = Field(
        default=5,
        alias="saveEveryEpoch",
        ge=1,
        le=1000,
        description="Chu kỳ lưu checkpoint G_/D_. Ví dụ 5 nghĩa là mỗi 5 epoch lưu một lần.",
        examples=[5],
    )
    batch_size: int = Field(
        default=4,
        alias="batchSize",
        ge=1,
        le=64,
        description=(
            "Batch size khi train. Tăng sẽ nhanh hơn nhưng tốn VRAM. Máy VRAM thấp nên dùng 1-4."
        ),
        examples=[4],
    )
    num_processes: int = Field(
        default=4,
        alias="numProcesses",
        ge=1,
        le=32,
        description="Số process CPU dùng cho preprocess và F0 extraction.",
        examples=[4],
    )
    gpu_devices_train: str = Field(
        default="0",
        alias="gpuDevicesTrain",
        pattern=r"^\d+(?:-\d+)*$",
        description=(
            "GPU ids dùng cho training theo format RVC: '0', '0-1', '0-1-2'. "
            "Máy 1 GPU giữ '0'."
        ),
        examples=["0"],
    )
    gpus_for_rmvpe: str = Field(
        default="0",
        alias="gpusForRmvpe",
        pattern=r"^(?:-|(?:\d+(?:-\d+)*))$",
        description=(
            "GPU ids dùng riêng cho f0Method=rmvpe_gpu. Dùng '0' cho GPU đầu tiên, "
            "'0-1' cho nhiều GPU, hoặc '-' cho DirectML path."
        ),
        examples=["0"],
    )
    speaker_id: int = Field(
        default=0,
        alias="speakerId",
        ge=0,
        description="Speaker id ghi vào filelist.txt. Single-speaker model gần như luôn dùng 0.",
        examples=[0],
    )
    save_only_latest: bool = Field(
        default=True,
        alias="saveOnlyLatest",
        description=(
            "Nếu true, chỉ giữ checkpoint mới nhất để tiết kiệm disk. Nếu false, giữ nhiều checkpoint."
        ),
    )
    cache_dataset_in_gpu: bool = Field(
        default=False,
        alias="cacheDatasetInGpu",
        description=(
            "Cache dataset vào GPU để tăng tốc training. Chỉ bật khi VRAM dư; dễ OOM trên GPU nhỏ."
        ),
    )
    save_weights_every_epoch: bool = Field(
        default=False,
        alias="saveWeightsEveryEpoch",
        description=(
            "Nếu true, extract inference weight vào assets/weights mỗi lần save checkpoint. "
            "Tốn disk hơn, thường để false."
        ),
    )
    pretrained_g: str = Field(
        default="",
        alias="pretrainedG",
        max_length=500,
        description=(
            "Path pretrained Generator trên server, phải nằm dưới rvc_my_server/assets. "
            "Để rỗng để tự chọn theo sampleRate/version/ifF0, ví dụ assets/pretrained_v2/f0G40k.pth."
        ),
        examples=[""],
    )
    pretrained_d: str = Field(
        default="",
        alias="pretrainedD",
        max_length=500,
        description=(
            "Path pretrained Discriminator trên server, phải nằm dưới rvc_my_server/assets. "
            "Để rỗng để tự chọn, ví dụ assets/pretrained_v2/f0D40k.pth."
        ),
        examples=[""],
    )
    preprocess_per: float = Field(
        default=3.7,
        alias="preprocessPer",
        ge=1.0,
        le=10.0,
        description=(
            "Độ dài mỗi slice audio khi preprocess, tính bằng giây. Default RVC thường 3.7. "
            "Nhỏ hơn dễ xử lý đoạn ngắn, lớn hơn giữ ngữ cảnh dài hơn."
        ),
        examples=[3.7],
    )
    disable_preprocess_parallel: bool = Field(
        default=False,
        alias="disablePreprocessParallel",
        description=(
            "Nếu true, preprocess chạy tuần tự thay vì multiprocessing. Hữu ích khi debug hoặc máy yếu."
        ),
    )
    extract_info: str = Field(
        default="Extracted model.",
        alias="extractInfo",
        max_length=500,
        description="Chuỗi info ghi vào metadata của file model.pth sau khi extract small model.",
        examples=["Trained from mobile upload."],
    )
    index_kmeans_threshold: int = Field(
        default=200000,
        alias="indexKmeansThreshold",
        ge=10000,
        le=2000000,
        description=(
            "Nếu tổng số vector Hubert vượt ngưỡng này, pipeline dùng MiniBatchKMeans "
            "để giảm vector trước khi build FAISS index."
        ),
        examples=[200000],
    )
    index_kmeans_centers: int = Field(
        default=10000,
        alias="indexKmeansCenters",
        ge=100,
        le=100000,
        description=(
            "Số cluster center khi dùng KMeans cho index. Cao hơn giữ nhiều thông tin hơn nhưng chậm/tốn RAM."
        ),
        examples=[10000],
    )
    index_batch_size: int = Field(
        default=8192,
        alias="indexBatchSize",
        ge=1024,
        le=65536,
        description="Số vector add vào FAISS mỗi batch. Tăng có thể nhanh hơn nhưng tốn RAM hơn.",
        examples=[8192],
    )
    index_nprobe: int = Field(
        default=1,
        alias="indexNprobe",
        ge=1,
        le=64,
        description=(
            "FAISS IVF nprobe ghi vào index. Cao hơn có thể retrieval tốt hơn nhưng inference chậm hơn."
        ),
        examples=[1],
    )

    @model_validator(mode="after")
    def require_audio_inputs(self):
        if not self.audio_upload_ids and not self.audio_object_paths:
            raise ValueError("Either audioUploadIds or audioObjectPaths must be provided")
        return self

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "title": "Giọng nữ đọc truyện",
                "description": "Dataset thu trong phòng yên tĩnh.",
                "audioUploadIds": [
                    "audio_upload_1779267563260_ac4083e7-cc7b-4c0e-9b56-e284dfc751f1"
                ],
                "sampleRate": "40k",
                "version": "v2",
                "ifF0": True,
                "f0Method": "rmvpe",
                "totalEpochs": 50,
                "saveEveryEpoch": 5,
                "batchSize": 4,
                "numProcesses": 4,
                "gpuDevicesTrain": "0",
                "gpusForRmvpe": "0",
                "speakerId": 0,
                "saveOnlyLatest": True,
                "cacheDatasetInGpu": False,
                "saveWeightsEveryEpoch": False,
                "pretrainedG": "",
                "pretrainedD": "",
                "preprocessPer": 3.7,
                "disablePreprocessParallel": False,
                "extractInfo": "Trained from mobile upload.",
                "indexKmeansThreshold": 200000,
                "indexKmeansCenters": 10000,
                "indexBatchSize": 8192,
                "indexNprobe": 1,
            }
        },
    )


class DeleteTrainingUploadsRequest(BaseModel):
    audio_upload_ids: Optional[list[str]] = Field(
        default=None,
        alias="audioUploadIds",
        min_length=1,
        max_length=100,
        description=(
            "Danh sách 1-100 audioUploadId cần xoá. Khuyến nghị dùng field này "
            "thay vì objectPaths."
        ),
        examples=[
            [
                "audio_upload_1779267563260_ac4083e7-cc7b-4c0e-9b56-e284dfc751f1"
            ]
        ],
    )
    object_paths: Optional[list[str]] = Field(
        default=None,
        alias="objectPaths",
        min_length=1,
        max_length=100,
        description=(
            "Danh sách 1-100 Storage object paths cần xoá. Chỉ dùng khi query deleteAll=false. "
            "Mỗi path phải thuộc prefix train_uploads/{currentUserId}/. Giữ để tương thích; "
            "nên dùng audioUploadIds."
        ),
        examples=[
            [
                "train_uploads/user_123/upload_456_001_voice_01.wav",
                "train_uploads/user_123/upload_456_002_voice_02.wav",
            ]
        ],
    )

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "audioUploadIds": [
                    "audio_upload_1779267563260_ac4083e7-cc7b-4c0e-9b56-e284dfc751f1"
                ]
            }
        },
    )


class ListTrainJobsQuery(BaseModel):
    limit: Optional[int] = Field(
        default=10,
        ge=1,
        le=100,
        description="Số item mỗi trang, từ 1 đến 100.",
    )
    start_after: Optional[str] = Field(
        default=None,
        alias="startAfter",
        description="Cursor trainJobId của item cuối trang trước.",
    )

    model_config = ConfigDict(populate_by_name=True)
