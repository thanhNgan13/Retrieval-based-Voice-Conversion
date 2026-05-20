from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from random import shuffle
from typing import Callable, Optional

import numpy as np
from sklearn.cluster import MiniBatchKMeans

from src.services import infer_engine

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, str], None]


@dataclass
class RvcTrainingParams:
    experiment_name: str
    input_dir: Path
    sample_rate: str = "40k"
    version: str = "v2"
    if_f0: bool = True
    speaker_id: int = 0
    num_processes: int = 4
    f0_method: str = "rmvpe"
    gpus_for_rmvpe: str = "0"
    gpu_devices_train: str = "0"
    save_every_epoch: int = 5
    total_epochs: int = 50
    batch_size: int = 4
    save_only_latest: bool = True
    cache_dataset_in_gpu: bool = False
    save_weights_every_epoch: bool = False
    pretrained_g: str = ""
    pretrained_d: str = ""
    preprocess_per: float = 3.7
    disable_preprocess_parallel: bool = False
    extract_info: str = "Extracted model."
    index_kmeans_threshold: int = 200000
    index_kmeans_centers: int = 10000
    index_batch_size: int = 8192
    index_nprobe: int = 1

    @property
    def sr_value(self) -> int:
        return {"32k": 32000, "40k": 40000, "48k": 48000}[self.sample_rate]


def _server_root() -> Path:
    return infer_engine.SERVER_ROOT


def _load_rvc_config():
    root = _server_root()
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    saved_argv = sys.argv
    sys.argv = ["rvc_train_worker"]
    try:
        from configs.config import Config

        return Config()
    finally:
        sys.argv = saved_argv


def _run(args: list[str], cwd: Path, on_line: Optional[Callable[[str], None]] = None) -> None:
    logger.info("Execute: %s", " ".join(args))
    process = subprocess.Popen(
        args,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )
    assert process.stdout is not None
    for line in process.stdout:
        line = line.rstrip("\n")
        if on_line:
            on_line(line)
        logger.info(line)
    process.wait()
    if process.returncode:
        raise RuntimeError("%s exited with %s" % (args[1], process.returncode))


def _check_required_assets(root: Path, p: RvcTrainingParams) -> None:
    missing = []
    for path in [
        root / "assets" / "hubert" / "hubert_base.pt",
        root / "logs" / "mute" / "0_gt_wavs",
        root / "logs" / "mute" / "3_feature256",
        root / "logs" / "mute" / "3_feature768",
        root / "logs" / "mute" / "2a_f0",
        root / "logs" / "mute" / "2b-f0nsf",
    ]:
        if not path.exists():
            missing.append(str(path))
    if p.if_f0 and p.f0_method.startswith("rmvpe"):
        rmvpe = root / "assets" / "rmvpe" / "rmvpe.pt"
        if not rmvpe.is_file():
            missing.append(str(rmvpe))
    if missing:
        raise FileNotFoundError("Missing required RVC training assets: %s" % missing)


def _step_preprocess(root: Path, config, p: RvcTrainingParams, cb: ProgressCallback) -> None:
    cb("preprocess", 10, "Preprocessing uploaded audio")
    exp_path = root / "logs" / p.experiment_name
    exp_path.mkdir(parents=True, exist_ok=True)
    (exp_path / "preprocess.log").write_text("", encoding="utf-8")
    _run(
        [
            config.python_cmd,
            "infer/modules/train/preprocess.py",
            str(p.input_dir),
            str(p.sr_value),
            str(p.num_processes),
            str(exp_path),
            str(p.disable_preprocess_parallel or config.noparallel),
            "%.1f" % p.preprocess_per,
        ],
        root,
    )


def _step_extract_f0_and_features(
    root: Path,
    config,
    p: RvcTrainingParams,
    cb: ProgressCallback,
) -> None:
    exp_path = root / "logs" / p.experiment_name
    (exp_path / "extract_f0_feature.log").write_text("", encoding="utf-8")

    if p.if_f0:
        cb("extract_f0", 25, "Extracting F0")
        if p.f0_method != "rmvpe_gpu":
            _run(
                [
                    config.python_cmd,
                    "infer/modules/train/extract/extract_f0_print.py",
                    str(exp_path),
                    str(p.num_processes),
                    p.f0_method,
                ],
                root,
            )
        else:
            ids = p.gpus_for_rmvpe.split("-") if p.gpus_for_rmvpe != "-" else []
            if ids:
                for idx, gpu_id in enumerate(ids):
                    _run(
                        [
                            config.python_cmd,
                            "infer/modules/train/extract/extract_f0_rmvpe.py",
                            str(len(ids)),
                            str(idx),
                            gpu_id,
                            str(exp_path),
                            str(config.is_half),
                        ],
                        root,
                    )
            else:
                _run(
                    [
                        config.python_cmd,
                        "infer/modules/train/extract/extract_f0_rmvpe_dml.py",
                        str(exp_path),
                    ],
                    root,
                )

    cb("extract_features", 40, "Extracting Hubert features")
    gpus = p.gpu_devices_train.split("-") if p.gpu_devices_train else ["0"]
    for idx, gpu_id in enumerate(gpus):
        _run(
            [
                config.python_cmd,
                "infer/modules/train/extract_feature_print.py",
                config.device,
                str(len(gpus)),
                str(idx),
                gpu_id,
                str(exp_path),
                p.version,
                str(config.is_half),
            ],
            root,
        )


def _write_filelist(root: Path, config, p: RvcTrainingParams) -> None:
    exp_path = root / "logs" / p.experiment_name
    gt_wavs_dir = exp_path / "0_gt_wavs"
    feature_dir = exp_path / ("3_feature256" if p.version == "v1" else "3_feature768")

    if p.if_f0:
        f0_dir = exp_path / "2a_f0"
        f0nsf_dir = exp_path / "2b-f0nsf"
        names = (
            {name.split(".")[0] for name in os.listdir(gt_wavs_dir)}
            & {name.split(".")[0] for name in os.listdir(feature_dir)}
            & {name.split(".")[0] for name in os.listdir(f0_dir)}
            & {name.split(".")[0] for name in os.listdir(f0nsf_dir)}
        )
    else:
        names = {name.split(".")[0] for name in os.listdir(gt_wavs_dir)} & {
            name.split(".")[0] for name in os.listdir(feature_dir)
        }

    if not names:
        raise RuntimeError("No valid training samples after preprocess/feature extraction")

    rows = []
    speaker_id = str(p.speaker_id)
    for name in names:
        if p.if_f0:
            rows.append(
                "%s/%s.wav|%s/%s.npy|%s/%s.wav.npy|%s/%s.wav.npy|%s"
                % (
                    str(gt_wavs_dir).replace("\\", "\\\\"),
                    name,
                    str(feature_dir).replace("\\", "\\\\"),
                    name,
                    str(f0_dir).replace("\\", "\\\\"),
                    name,
                    str(f0nsf_dir).replace("\\", "\\\\"),
                    name,
                    speaker_id,
                )
            )
        else:
            rows.append(
                "%s/%s.wav|%s/%s.npy|%s"
                % (
                    str(gt_wavs_dir).replace("\\", "\\\\"),
                    name,
                    str(feature_dir).replace("\\", "\\\\"),
                    name,
                    speaker_id,
                )
            )

    fea_dim = 256 if p.version == "v1" else 768
    root_s = str(root).replace("\\", "\\\\")
    if p.if_f0:
        for _ in range(2):
            rows.append(
                "%s/logs/mute/0_gt_wavs/mute%s.wav|%s/logs/mute/3_feature%s/mute.npy|%s/logs/mute/2a_f0/mute.wav.npy|%s/logs/mute/2b-f0nsf/mute.wav.npy|%s"
                % (root_s, p.sample_rate, root_s, fea_dim, root_s, root_s, speaker_id)
            )
    else:
        for _ in range(2):
            rows.append(
                "%s/logs/mute/0_gt_wavs/mute%s.wav|%s/logs/mute/3_feature%s/mute.npy|%s"
                % (root_s, p.sample_rate, root_s, fea_dim, speaker_id)
            )
    shuffle(rows)
    (exp_path / "filelist.txt").write_text("\n".join(rows), encoding="utf-8")

    config_key = "v1/%s.json" % p.sample_rate if p.version == "v1" or p.sample_rate == "40k" else "v2/%s.json" % p.sample_rate
    config_save_path = exp_path / "config.json"
    if not config_save_path.exists():
        config_save_path.write_text(
            json.dumps(
                config.json_config[config_key],
                ensure_ascii=False,
                indent=4,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


def _resolve_pretrained_paths(p: RvcTrainingParams) -> tuple[str, str]:
    if p.pretrained_g or p.pretrained_d:
        return p.pretrained_g, p.pretrained_d

    suffix = "" if p.version == "v1" else "_v2"
    f0_prefix = "f0" if p.if_f0 else ""

    def candidate(kind: str) -> str:
        return "assets/pretrained%s/%s%s%s.pth" % (
            suffix,
            f0_prefix,
            kind,
            p.sample_rate,
        )

    pg = candidate("G")
    pd = candidate("D")
    return (pg if os.path.isfile(pg) else "", pd if os.path.isfile(pd) else "")


def _step_train(root: Path, config, p: RvcTrainingParams, cb: ProgressCallback) -> None:
    cb("train", 55, "Training RVC model")
    _write_filelist(root, config, p)
    pretrained_g, pretrained_d = _resolve_pretrained_paths(p)
    args = [
        config.python_cmd,
        "infer/modules/train/train.py",
        "-e",
        p.experiment_name,
        "-sr",
        p.sample_rate,
        "-f0",
        "1" if p.if_f0 else "0",
        "-bs",
        str(p.batch_size),
        "-te",
        str(p.total_epochs),
        "-se",
        str(p.save_every_epoch),
        "-l",
        "1" if p.save_only_latest else "0",
        "-c",
        "1" if p.cache_dataset_in_gpu else "0",
        "-sw",
        "1" if p.save_weights_every_epoch else "0",
        "-v",
        p.version,
    ]
    if p.gpu_devices_train:
        args.extend(["-g", p.gpu_devices_train])
    if pretrained_g:
        args.extend(["-pg", pretrained_g])
    if pretrained_d:
        args.extend(["-pd", pretrained_d])
    if not pretrained_g or not pretrained_d:
        logger.warning(
            "No pretrained %s found for version=%s sample_rate=%s if_f0=%s. "
            "Training will start from scratch and may need more epochs.",
            "G/D" if not pretrained_g and not pretrained_d else ("G" if not pretrained_g else "D"),
            p.version,
            p.sample_rate,
            p.if_f0,
        )
    _run(args, root)


def _step_train_index(root: Path, p: RvcTrainingParams, cb: ProgressCallback) -> Path:
    cb("build_index", 80, "Building FAISS retrieval index")
    import faiss

    exp_path = root / "logs" / p.experiment_name
    feature_dir = exp_path / ("3_feature256" if p.version == "v1" else "3_feature768")
    npys = [np.load(str(feature_dir / name)) for name in sorted(os.listdir(feature_dir))]
    if not npys:
        raise RuntimeError("No Hubert feature files found for index training")

    big_npy = np.concatenate(npys, 0)
    big_npy = big_npy[np.random.permutation(big_npy.shape[0])]
    if big_npy.shape[0] > p.index_kmeans_threshold:
        n_cpu = os.cpu_count() or 4
        big_npy = (
            MiniBatchKMeans(
                n_clusters=p.index_kmeans_centers,
                verbose=True,
                batch_size=256 * n_cpu,
                compute_labels=False,
                init="random",
            )
            .fit(big_npy)
            .cluster_centers_
        )

    np.save(str(exp_path / "total_fea.npy"), big_npy)
    n_ivf = min(int(16 * np.sqrt(big_npy.shape[0])), big_npy.shape[0] // 39)
    if n_ivf < 1:
        n_ivf = 1
    index = faiss.index_factory(
        256 if p.version == "v1" else 768,
        "IVF%s,Flat" % n_ivf,
    )
    index_ivf = faiss.extract_index_ivf(index)
    index_ivf.nprobe = p.index_nprobe
    index.train(big_npy)
    for i in range(0, big_npy.shape[0], p.index_batch_size):
        index.add(big_npy[i : i + p.index_batch_size])

    added_name = "added_IVF%s_Flat_nprobe_%s_%s_%s.index" % (
        n_ivf,
        index_ivf.nprobe,
        p.experiment_name,
        p.version,
    )
    index_path = exp_path / added_name
    faiss.write_index(index, str(index_path))
    return index_path


def _extract_small_weights(root: Path, p: RvcTrainingParams, output_name: str) -> Path:
    from infer.lib.train.process_ckpt import extract_small_model

    weights_dir = root / "assets" / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)
    exp_path = root / "logs" / p.experiment_name
    checkpoints = sorted(
        exp_path.glob("G_*.pth"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    if not checkpoints:
        raise FileNotFoundError("No G_*.pth checkpoint found in %s" % exp_path)

    result = extract_small_model(
        str(checkpoints[0]),
        output_name,
        p.sample_rate,
        int(p.if_f0),
        p.extract_info,
        p.version,
    )
    if "Success" not in result:
        raise RuntimeError(result)
    return weights_dir / ("%s.pth" % output_name)


def run_rvc_training_pipeline(
    params: RvcTrainingParams,
    output_model_name: str,
    progress: ProgressCallback,
) -> tuple[Path, Path]:
    root = _server_root()
    os.chdir(root)
    _check_required_assets(root, params)
    config = _load_rvc_config()

    try:
        _step_preprocess(root, config, params, progress)
        _step_extract_f0_and_features(root, config, params, progress)
        _step_train(root, config, params, progress)
        index_path = _step_train_index(root, params, progress)
        progress("extract_model", 90, "Extracting inference checkpoint")
        model_path = _extract_small_weights(root, params, output_model_name)
        progress("finalize", 95, "Finalizing trained model")
        return model_path, index_path
    except Exception:
        logger.error("RVC training pipeline failed:\n%s", traceback.format_exc())
        raise
