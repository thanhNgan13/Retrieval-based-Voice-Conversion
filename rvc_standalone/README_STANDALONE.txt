THƯ MỤC RVC_STANDALONE — GÓI TRAIN ĐỘC LẬP
========================================

Mục tiêu: Bạn có thể COPY TOÀN BỘ thư mục này sang máy/ổ khác và huấn luyện mà KHÔNG cần
mã nguồn RVC-WebUI gốc ở thư mục cha.

Nội dung đã gói sẵn:
  - infer/          Mã train & thư viện RVC (bản sao đầy đủ từ repo gốc)
  - configs/        Cấu hình JSON cho train
  - i18n/           Đa ngôn ngữ (process_ckpt cần cho chuỗi "是" / "Yes")
  - training_pipeline/  Script điều phối: preprocess → F0+Hubert → train → index
  - requirements.txt   Phụ thuộc Python (giống repo gốc)
  - .env            Đường dẫn weights/index (có thể sửa)

Bạn vẫn phải TỰ ĐẶT FILE trọng lượng (không nằm trong repo vì dung lượng lớn):
  - assets/hubert/hubert_base.pt
  - assets/pretrained/ hoặc assets/pretrained_v2/  (G/D pretrained đúng 32k/40k/48k)
  - assets/rmvpe/   (nếu dùng RMVPE) — xem hướng dẫn RVC gốc
  - logs/mute/      Cấu trúc mute cho filelist (bản đầy đủ RVC/Colab có sẵn)

CÁCH TẢI VÀO assets/ (khuyến nghị)
---------------------------------
1) Mở terminal, cd vào thư mục rvc_standalone.
2) Cài: pip install requests
3) Chạy:
     python tools/download_assets.py

Script trên tải từ Hugging Face:
  https://huggingface.co/lj1995/VoiceConversionWebUI/tree/main
và đặt đúng vào assets/hubert, assets/pretrained, assets/pretrained_v2,
assets/rmvpe, assets/uvr5_weights, ...

Nếu chỉ train v2 + 40k, ít nhất vẫn nên tải đủ bộ (tránh thiếu khi đổi cấu hình).
Có thể tải từng file bằng trình duyệt tại link trên rồi copy vào đúng thư mục con của assets/.

Lưu ý GPU DirectML (AMD/Intel): có thể cần rmvpe.onnx thay cho rmvpe.pt — xem README gốc RVC.

Cách chạy:
  1) cd vào thư mục này (rvc_standalone)
  2) Python 3.8–3.10 khuyến nghị. Với fairseq: hạ pip TRƯỚC (pip 24.1+ hay lỗi omegaconf):
       python -m pip install -U "pip>=23.2,<24.1"
       pip install -r requirements.txt
     Hoặc: powershell -File tools/install_deps.ps1
  3) PyTorch GPU (NVIDIA): sau bước 2, cài torch + CUDA đúng driver, ví dụ:
       pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
  4) Mở RVC_training_standalone.ipynb hoặc gọi training_pipeline với cwd = rvc_standalone

Notebook / bootstrap luôn coi "gốc dự án" = CHÍNH thư mục rvc_standalone (không tham chiếu repo cha).

GOOGLE COLAB / KAGGLE (một file .ipynb)
--------------------------------------
- Chạy trên máy (trong thư mục rvc_standalone):  python tools/generate_colab_notebook.py
- Sẽ tạo: RVC_Train_Colab_Kaggle_Generated.ipynb  (chứa hướng dẫn tiếng Việt + mã base64 ghi
  training_pipeline và các file patch; clone repo RVC chính thức làm nền infer/configs).
- Upload file .ipynb lên Colab/Kaggle, bật GPU, chạy lần lượt các ô. Vẫn cần thư mục logs/mute
  (upload tay hoặc copy từ bản RVC đầy đủ) trước khi train.
