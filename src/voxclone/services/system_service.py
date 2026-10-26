"""Doctor pre-flight diagnostics and storage utilization reporting."""

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess

from voxclone.config import AppConfig
from voxclone.storage.files import dir_size_mb


@dataclass(frozen=True)
class DoctorCheck:
    """Represents the outcome of a single system pre-flight check."""

    name: str
    ok: bool
    detail: str
    fix_hint: str


@dataclass(frozen=True)
class StorageReport:
    """Summary of disk utilization across VoxClone storage tiers."""

    profiles_mb: float
    outputs_mb: float
    models_mb: float
    work_mb: float


def _check_gpu_visible() -> DoctorCheck:
    """Check if nvidia-smi command is present and returns exit code 0."""
    try:
        res = subprocess.run(
            ["nvidia-smi"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
        if res.returncode == 0:
            return DoctorCheck(
                name="gpu_visible",
                ok=True,
                detail="NVIDIA GPU detected and nvidia-smi responded",
                fix_hint="",
            )
        return DoctorCheck(
            name="gpu_visible",
            ok=False,
            detail=f"nvidia-smi returned exit code {res.returncode}",
            fix_hint="Verify host NVIDIA GPU drivers and Docker GPU runtime flags.",
        )
    except FileNotFoundError:
        return DoctorCheck(
            name="gpu_visible",
            ok=False,
            detail="nvidia-smi binary not found",
            fix_hint="Install NVIDIA drivers and nvidia-container-toolkit.",
        )
    except Exception as exc:
        return DoctorCheck(
            name="gpu_visible",
            ok=False,
            detail=f"Error probing nvidia-smi: {exc!s}",
            fix_hint="Verify host GPU configuration.",
        )


def _check_cuda_available() -> DoctorCheck:
    """Lazily import torch and verify CUDA GPU runtime availability."""
    try:
        import torch  # type: ignore[import-untyped]

        if torch.cuda.is_available():
            dev_name = torch.cuda.get_device_name(0)
            return DoctorCheck(
                name="cuda_available",
                ok=True,
                detail=f"CUDA available ({dev_name})",
                fix_hint="",
            )
        return DoctorCheck(
            name="cuda_available",
            ok=False,
            detail="PyTorch installed but torch.cuda.is_available() is False",
            fix_hint="Ensure NVIDIA driver and CUDA container toolkit are configured.",
        )
    except ImportError:
        return DoctorCheck(
            name="cuda_available",
            ok=False,
            detail="PyTorch (torch) is not installed",
            fix_hint="Install PyTorch with CUDA support or run in fake engine mode.",
        )
    except Exception as exc:
        return DoctorCheck(
            name="cuda_available",
            ok=False,
            detail=f"CUDA probe error: {exc!s}",
            fix_hint="Check PyTorch CUDA installation.",
        )


def _check_audio_devices(config: AppConfig) -> tuple[DoctorCheck, DoctorCheck]:
    """Verify microphone input and speaker output streams."""
    if config.engine_mode == "fake":
        return (
            DoctorCheck(
                name="audio_input",
                ok=True,
                detail="null audio backend (fake engine mode)",
                fix_hint="",
            ),
            DoctorCheck(
                name="audio_output",
                ok=True,
                detail="null audio backend (fake engine mode)",
                fix_hint="",
            ),
        )

    try:
        import sounddevice as sd  # type: ignore[import-untyped]

        devices = sd.query_devices()
        input_dev = any(d.get("max_input_channels", 0) > 0 for d in devices)
        output_dev = any(d.get("max_output_channels", 0) > 0 for d in devices)

        in_check = DoctorCheck(
            name="audio_input",
            ok=input_dev,
            detail="Audio capture device found" if input_dev else "No audio input device detected",
            fix_hint="" if input_dev else "Ensure microphone is shared with WSLg (/mnt/wslg/PulseServer).",
        )
        out_check = DoctorCheck(
            name="audio_output",
            ok=output_dev,
            detail="Audio playback device found" if output_dev else "No audio output device detected",
            fix_hint="" if output_dev else "Verify PulseAudio output device configuration.",
        )
        return in_check, out_check
    except Exception as exc:
        return (
            DoctorCheck(
                name="audio_input",
                ok=False,
                detail=f"Audio input probe error: {exc!s}",
                fix_hint="Ensure libportaudio2 is installed and PulseAudio socket is accessible.",
            ),
            DoctorCheck(
                name="audio_output",
                ok=False,
                detail=f"Audio output probe error: {exc!s}",
                fix_hint="Verify WSLg audio forwarding is active.",
            ),
        )


def _check_ram() -> DoctorCheck:
    """Check available system memory (fail if free RAM < 2000 MB)."""
    try:
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            content = meminfo.read_text(encoding="utf-8")
            free_kb = 0
            for line in content.splitlines():
                if line.startswith("MemAvailable:"):
                    free_kb = int(line.split()[1])
                    break
                if line.startswith("MemFree:") and free_kb == 0:
                    free_kb = int(line.split()[1])
            free_mb = free_kb // 1024
            if free_mb >= 2000:
                return DoctorCheck(
                    name="ram_free_mb",
                    ok=True,
                    detail=f"Available RAM: {free_mb} MB (>= 2000 MB requirement)",
                    fix_hint="",
                )
            return DoctorCheck(
                name="ram_free_mb",
                ok=False,
                detail=f"Low available RAM: {free_mb} MB (< 2000 MB requirement)",
                fix_hint="Close background processes or allocate more memory to WSL2 in .wslconfig.",
            )
        # Windows / Non-proc fallback
        return DoctorCheck(
            name="ram_free_mb",
            ok=True,
            detail="System RAM check skipped on non-Linux host",
            fix_hint="",
        )
    except Exception as exc:
        return DoctorCheck(
            name="ram_free_mb",
            ok=False,
            detail=f"Failed reading RAM: {exc!s}",
            fix_hint="Check memory metrics.",
        )


def _check_disk(config: AppConfig) -> DoctorCheck:
    """Check available disk storage on data volume (fail if < 5 GB)."""
    try:
        usage = shutil.disk_usage(config.data_dir if config.data_dir.exists() else Path("."))
        free_gb = round(usage.free / (1024**3), 2)
        if free_gb >= 5.0:
            return DoctorCheck(
                name="disk_free_gb",
                ok=True,
                detail=f"Free disk space: {free_gb} GB (>= 5.0 GB requirement)",
                fix_hint="",
            )
        return DoctorCheck(
            name="disk_free_gb",
            ok=False,
            detail=f"Insufficient disk space: {free_gb} GB (< 5.0 GB requirement)",
            fix_hint="Free up disk storage on the container data mount.",
        )
    except Exception as exc:
        return DoctorCheck(
            name="disk_free_gb",
            ok=False,
            detail=f"Disk usage check failed: {exc!s}",
            fix_hint="Ensure data directory path exists and is readable.",
        )


def _check_model_cache() -> DoctorCheck:
    """Verify presence of cached AI weights in HuggingFace cache."""
    hf_home = os.environ.get("HF_HOME", "/models")
    cache_path = Path(hf_home)
    if not cache_path.exists():
        return DoctorCheck(
            name="model_cache",
            ok=False,
            detail=f"Model directory '{hf_home}' does not exist",
            fix_hint="Run 'system fetch-models' while online.",
        )

    # Check for expected model hub directories or markers
    has_models = any(cache_path.iterdir()) if cache_path.is_dir() else False
    if has_models:
        return DoctorCheck(
            name="model_cache",
            ok=True,
            detail=f"Cached models present under {hf_home}",
            fix_hint="",
        )
    return DoctorCheck(
        name="model_cache",
        ok=False,
        detail=f"Model cache at {hf_home} is empty",
        fix_hint="Run 'system fetch-models' to download required weights.",
    )


def _check_data_dirs_writable(config: AppConfig) -> DoctorCheck:
    """Verify that runtime storage directories are writable."""
    try:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        test_file = config.data_dir / ".write_probe"
        test_file.write_text("probe", encoding="utf-8")
        test_file.unlink()
        return DoctorCheck(
            name="data_dirs_writable",
            ok=True,
            detail=f"Directory '{config.data_dir}' is writable",
            fix_hint="",
        )
    except Exception as exc:
        return DoctorCheck(
            name="data_dirs_writable",
            ok=False,
            detail=f"Data directory write test failed: {exc!s}",
            fix_hint="Check folder permissions for non-root user voxclone.",
        )


def run_doctor(config: AppConfig) -> list[DoctorCheck]:
    """Execute all pre-flight diagnostic checks sequentially without throwing."""
    checks: list[DoctorCheck] = []

    # 1. GPU visible
    checks.append(_check_gpu_visible())
    # 2. CUDA available
    checks.append(_check_cuda_available())
    # 3 & 4. Audio in / out
    in_chk, out_chk = _check_audio_devices(config)
    checks.append(in_chk)
    checks.append(out_chk)
    # 5. RAM free
    checks.append(_check_ram())
    # 6. Disk free
    checks.append(_check_disk(config))
    # 7. Model cache
    checks.append(_check_model_cache())
    # 8. Data dirs writable
    checks.append(_check_data_dirs_writable(config))

    return checks


def get_storage_report(config: AppConfig) -> StorageReport:
    """Compute size utilization report across data tiers."""
    hf_home = Path(os.environ.get("HF_HOME", "/models"))
    return StorageReport(
        profiles_mb=dir_size_mb(config.profiles_dir),
        outputs_mb=dir_size_mb(config.outputs_dir),
        models_mb=dir_size_mb(hf_home),
        work_mb=dir_size_mb(config.work_dir),
    )


@dataclass(frozen=True)
class ModelFetchResult:
    """Status report for a model weights download attempt."""

    model_key: str
    repo_id: str
    ok: bool
    detail: str


MODEL_REPOS: dict[str, str] = {
    "tts": "SWivid/F5-TTS",
    "vc": "myshell-ai/OpenVoiceV2",
    "emotion": "j-hartmann/emotion-english-distilroberta-base",
}


def fetch_models(
    config: AppConfig,
    keys: list[str] | None = None,
) -> list[ModelFetchResult]:
    """Download or verify local presence of AI model weights from Hugging Face."""
    target_keys = keys or ["tts", "vc", "emotion"]
    results: list[ModelFetchResult] = []

    hf_home = Path(os.environ.get("HF_HOME", str(config.models_dir))).resolve()
    hf_home.mkdir(parents=True, exist_ok=True)

    if config.engine_mode == "fake":
        for k in target_keys:
            repo = MODEL_REPOS.get(k, f"mock/{k}")
            results.append(
                ModelFetchResult(
                    model_key=k,
                    repo_id=repo,
                    ok=True,
                    detail="Engine mode is 'fake'; mock weights verified without network transfer.",
                )
            )
        return results

    try:
        from huggingface_hub import snapshot_download  # type: ignore[import-untyped]
    except ImportError:
        for k in target_keys:
            repo = MODEL_REPOS.get(k, "unknown")
            results.append(
                ModelFetchResult(
                    model_key=k,
                    repo_id=repo,
                    ok=False,
                    detail="huggingface_hub package is not installed.",
                )
            )
        return results

    for k in target_keys:
        repo = MODEL_REPOS.get(k)
        if not repo:
            results.append(
                ModelFetchResult(
                    model_key=k,
                    repo_id="unknown",
                    ok=False,
                    detail=f"No Hugging Face repository mapping found for key '{k}'.",
                )
            )
            continue

        try:
            snapshot_download(
                repo_id=repo,
                local_dir=hf_home / k,
                local_dir_use_symlinks=False,
                resume_download=True,
            )
            results.append(
                ModelFetchResult(
                    model_key=k,
                    repo_id=repo,
                    ok=True,
                    detail=f"Weights successfully verified and cached in {hf_home / k}.",
                )
            )
        except Exception as exc:
            results.append(
                ModelFetchResult(
                    model_key=k,
                    repo_id=repo,
                    ok=False,
                    detail=f"Download failed: {exc!s}",
                )
            )

    return results

