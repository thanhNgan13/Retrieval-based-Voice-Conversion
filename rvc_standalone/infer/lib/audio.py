import platform, os
import ffmpeg
import numpy as np
import av
from io import BytesIO
import traceback
import re


def wav2(i, o, format):
    inp = av.open(i, "rb")
    if format == "m4a":
        format = "mp4"
    out = av.open(o, "wb", format=format)
    if format == "ogg":
        format = "libvorbis"
    if format == "mp4":
        format = "aac"

    ostream = out.add_stream(format)

    for frame in inp.decode(audio=0):
        for p in ostream.encode(frame):
            out.mux(p)

    for p in ostream.encode(None):
        out.mux(p)

    out.close()
    inp.close()


def load_audio(file, sr):
    try:
        file = clean_path(file)
        if os.path.exists(file) == False:
            raise RuntimeError(
                "You input a wrong audio path that does not exists, please fix it!"
            )
        # Dùng PyAV (av) thay vì subprocess ffmpeg CLI — PyAV dùng FFmpeg C libraries
        # linked vào Python extension, không spawn process nên không bị lỗi DLL
        # trên Python 3.11 Windows khi gọi từ multiprocessing child process.
        container = av.open(file, "r")
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=sr)
        chunks = []
        for frame in container.decode(audio=0):
            for out_frame in resampler.resample(frame):
                chunks.append(out_frame.to_ndarray().flatten())
        for out_frame in resampler.resample(None):
            chunks.append(out_frame.to_ndarray().flatten())
        container.close()
        if not chunks:
            return np.array([], dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32)
    except RuntimeError:
        raise
    except Exception as e:
        traceback.print_exc()
        raise RuntimeError(f"Failed to load audio: {e}")



def clean_path(path_str):
    if platform.system() == "Windows":
        path_str = path_str.replace("/", "\\")
    path_str = re.sub(r'[\u202a\u202b\u202c\u202d\u202e]', '', path_str)  # 移除 Unicode 控制字符
    return path_str.strip(" ").strip('"').strip("\n").strip('"').strip(" ")
