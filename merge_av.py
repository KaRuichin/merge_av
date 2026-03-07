"""
merge_av.py
将一个纯视频 MP4 和一个纯音频 MP4 合并为单个含音视频的 MP4 文件。
支持直接流复制（默认）、H.265 或 AV1 重编码，支持 GPU 硬件加速。

用法:
    # 自动检测模式（无参数时自动扫描当前目录，交互式选择编码和 GPU）
    python merge_av.py

    # 直接复制（最快，无质量损失）
    python merge_av.py <video.mp4> <audio.mp4> <output.mp4>

    # H.265 编码
    python merge_av.py <video.mp4> <audio.mp4> <output.mp4> --h265

    # AV1 视觉无损编码（体积更小）
    python merge_av.py <video.mp4> <audio.mp4> <output.mp4> --av1

    # 使用 NVIDIA GPU 加速
    python merge_av.py <video.mp4> <audio.mp4> <output.mp4> --h265 --gpu nvidia

    # AV1 自定义质量（CRF 0=无损 ~ 63=最差，默认 23）
    python merge_av.py <video.mp4> <audio.mp4> <output.mp4> --av1 --crf 28
"""

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

try:
    from InquirerPy import inquirer as inq
    from InquirerPy.base.control import Choice

    INTERACTIVE_UI = True
except ImportError:
    INTERACTIVE_UI = False

# 编码器配置
# 格式: {gpu_type: {codec: [encoder_list]}}
ENCODERS = {
    # 软件编码器
    "cpu": {
        "h265": ["libx265"],
        "av1": ["libsvtav1", "libaom-av1", "librav1e"],
    },
    # NVIDIA GPU (NVENC)
    "nvidia": {
        "h265": ["hevc_nvenc"],
        "av1": ["av1_nvenc"],
    },
    # AMD GPU (AMF)
    "amd": {
        "h265": ["hevc_amf"],
        "av1": ["av1_amf"],
    },
    # Intel GPU (QSV)
    "intel": {
        "h265": ["hevc_qsv"],
        "av1": ["av1_qsv"],
    },
}

# GPU 显示名称
GPU_NAMES = {
    "nvidia": "NVIDIA (NVENC)",
    "amd": "AMD (AMF)",
    "intel": "Intel (QSV)",
    "cpu": "CPU (软件编码)",
}

# B站等平台常见的流 ID（用于区分视频/音频）
VIDEO_STREAM_IDS = {
    "30116",
    "30112",
    "30080",
    "30077",
    "30076",
    "30033",
    "30032",
    "30011",
    "30016",
}
AUDIO_STREAM_IDS = {"30280", "30232", "30216", "30250", "30251"}


# ---------------------------------------------------------------------------
# 交互式 UI 辅助函数（支持 ↑↓ 方向键 + 键盘数字键）
# ---------------------------------------------------------------------------


def interactive_select(message: str, choices: list, default_index: int = 0):
    """
    交互式选择菜单。
    - 安装了 InquirerPy 时: 支持 ↑↓ 方向键、数字键快速跳转。
    - 未安装时: 降级为键盘输入序号。
    choices: [(显示文本, 返回值), ...]
    返回选中项的值。
    """
    if INTERACTIVE_UI:
        choice_objs = [
            Choice(value=val, name=f" {i + 1}. {name}")
            for i, (name, val) in enumerate(choices)
        ]
        prompt = inq.select(
            message=message,
            choices=choice_objs,
            default=(
                choice_objs[default_index].value
                if default_index < len(choices)
                else None
            ),
            instruction="(↑↓ 选择，数字键快选，Enter 确认)",
        )
        # 注册数字键 1-9 快捷跳转
        for idx in range(min(len(choices), 9)):

            def _make_handler(target):
                def _handler(event):
                    prompt.content_control.selected_choice_index = target

                return _handler

            prompt.register_kb(str(idx + 1))(_make_handler(idx))

        return prompt.execute()

    # 降级: 纯键盘输入
    print(f"\n{message}")
    for i, (name, _) in enumerate(choices):
        print(f"  [{i + 1}] {name}")
    print()
    while True:
        inp = input(
            f"请输入选项 [1-{len(choices)}]，默认为 {default_index + 1}: "
        ).strip()
        if inp == "":
            return choices[default_index][1]
        try:
            idx = int(inp) - 1
            if 0 <= idx < len(choices):
                return choices[idx][1]
        except ValueError:
            pass
        print(f"无效选项，请输入 1-{len(choices)}")


def interactive_confirm(message: str, default: bool = True) -> bool:
    """交互式确认提示。"""
    if INTERACTIVE_UI:
        return inq.confirm(message=message, default=default).execute()
    suffix = "[Y/n]" if default else "[y/N]"
    result = input(f"{message} {suffix}: ").strip().lower()
    if result == "":
        return default
    return result in ("y", "yes")


def interactive_number(message: str, default: int, min_val: int, max_val: int) -> int:
    """交互式数字输入。"""
    if INTERACTIVE_UI:
        return int(
            inq.number(
                message=message,
                default=default,
                min_allowed=min_val,
                max_allowed=max_val,
                float_allowed=False,
            ).execute()
        )
    while True:
        inp = input(f"{message} [{min_val}-{max_val}]，默认为 {default}: ").strip()
        if inp == "":
            return default
        try:
            val = int(inp)
            if min_val <= val <= max_val:
                return val
            print(f"错误: 范围为 {min_val}~{max_val}，请重新输入")
        except ValueError:
            print("错误: 请输入有效数字")


def get_available_encoders() -> dict:
    """检测 ffmpeg 支持的所有编码器，返回可用编码器字典。"""
    result = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
    output = result.stdout

    available = {}
    for gpu_type, codecs in ENCODERS.items():
        available[gpu_type] = {}
        for codec, encoder_list in codecs.items():
            for enc in encoder_list:
                if enc in output:
                    available[gpu_type][codec] = enc
                    break
    return available


def detect_gpus() -> list:
    """
    检测系统中可用的 GPU，返回 GPU 类型列表。
    优先返回独立显卡（NVIDIA > AMD > Intel）。
    """
    gpus = []

    # 检测 NVIDIA GPU
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            gpus.append(("nvidia", result.stdout.strip().split("\n")[0]))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 在 Windows 上通过 WMIC 检测显卡
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["wmic", "path", "win32_videocontroller", "get", "name"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                lines = [
                    line.strip()
                    for line in result.stdout.split("\n")
                    if line.strip() and line.strip() != "Name"
                ]
                for line in lines:
                    line_lower = line.lower()
                    if "nvidia" in line_lower and not any(
                        g[0] == "nvidia" for g in gpus
                    ):
                        gpus.append(("nvidia", line))
                    elif "amd" in line_lower or "radeon" in line_lower:
                        gpus.append(("amd", line))
                    elif "intel" in line_lower:
                        gpus.append(("intel", line))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # 始终添加 CPU 选项
    gpus.append(("cpu", "CPU 软件编码"))

    # 去重并按优先级排序：nvidia > amd > intel > cpu
    seen = set()
    unique_gpus = []
    priority = {"nvidia": 0, "amd": 1, "intel": 2, "cpu": 3}
    gpus.sort(key=lambda x: priority.get(x[0], 99))

    for gpu_type, gpu_name in gpus:
        if gpu_type not in seen:
            seen.add(gpu_type)
            unique_gpus.append((gpu_type, gpu_name))

    return unique_gpus


def detect_encoder(codec: str, gpu: str, available_encoders: dict) -> Optional[str]:
    """检测指定编解码器和 GPU 组合的可用编码器。"""
    if gpu in available_encoders and codec in available_encoders[gpu]:
        return available_encoders[gpu][codec]
    return None


def detect_media_pairs(directory: Path = None) -> list:
    """
    扫描目录中的 MP4 文件，检测符合命名模式的视频/音频配对。
    命名模式: <prefix>-<stream_id>.mp4，如 36502112568-1-30116.mp4
    返回: [(video_path, audio_path, suggested_output), ...]
    """
    if directory is None:
        directory = Path(__file__).parent

    mp4_files = list(directory.glob("*.mp4"))
    if not mp4_files:
        return []

    # 按前缀分组：pattern 匹配 "xxx-数字.mp4" 格式
    pattern = re.compile(r"^(.+)-(\d+)\.mp4$", re.IGNORECASE)
    groups = defaultdict(list)

    for f in mp4_files:
        match = pattern.match(f.name)
        if match:
            prefix, stream_id = match.groups()
            groups[prefix].append((stream_id, f))

    pairs = []
    for prefix, files in groups.items():
        if len(files) < 2:
            continue

        video_file = None
        audio_file = None

        for stream_id, filepath in files:
            if stream_id in VIDEO_STREAM_IDS:
                video_file = filepath
            elif stream_id in AUDIO_STREAM_IDS:
                audio_file = filepath

        # 启发式方法：文件大小判断
        if video_file is None or audio_file is None:
            sorted_files = sorted(files, key=lambda x: int(x[0]))
            if len(sorted_files) >= 2:
                file1, file2 = sorted_files[0][1], sorted_files[1][1]
                if file1.stat().st_size > file2.stat().st_size:
                    video_file, audio_file = file1, file2
                else:
                    video_file, audio_file = file2, file1

        if video_file and audio_file:
            output_name = f"{prefix}.mp4"
            output_path = directory / output_name
            pairs.append((video_file, audio_file, output_path))

    return pairs


def prompt_encoding_choice(available_encoders: dict, gpus: list) -> tuple:
    """
    交互式提示用户选择编码方式和 GPU。
    返回: (codec: str, lossless: bool, crf: int, gpu: str, encoder: str)
    codec: "copy" | "h265" | "av1"
    """
    choices = [
        ("直接复制（最快，零质量损失）", "copy"),
        ("H.265/HEVC 编码（兼容性好，体积小）", "h265"),
        ("H.265/HEVC 自定义 CRF 值", "h265_crf"),
        ("AV1 视觉无损编码（CRF=23，体积最小）", "av1"),
        ("AV1 真正无损编码（数学意义无损）", "av1_lossless"),
        ("AV1 自定义 CRF 值", "av1_crf"),
    ]

    result = interactive_select("请选择编码方式:", choices)

    if result == "copy":
        return "copy", False, 23, "cpu", "copy"
    elif result == "h265":
        gpu, encoder = prompt_gpu_choice("h265", available_encoders, gpus)
        return "h265", False, 23, gpu, encoder
    elif result == "h265_crf":
        gpu, encoder = prompt_gpu_choice("h265", available_encoders, gpus)
        crf = prompt_crf_choice("h265")
        return "h265", False, crf, gpu, encoder
    elif result == "av1":
        gpu, encoder = prompt_gpu_choice("av1", available_encoders, gpus)
        return "av1", False, 23, gpu, encoder
    elif result == "av1_lossless":
        gpu, encoder = prompt_gpu_choice("av1", available_encoders, gpus)
        return "av1", True, 0, gpu, encoder
    else:  # av1_crf
        gpu, encoder = prompt_gpu_choice("av1", available_encoders, gpus)
        crf = prompt_crf_choice("av1")
        return "av1", False, crf, gpu, encoder


def prompt_gpu_choice(codec: str, available_encoders: dict, gpus: list) -> tuple:
    """
    提示用户选择 GPU 进行编码。
    返回: (gpu_type: str, encoder: str)
    """
    valid_gpus = []
    for gpu_type, gpu_name in gpus:
        encoder = detect_encoder(codec, gpu_type, available_encoders)
        if encoder:
            valid_gpus.append((gpu_type, gpu_name, encoder))

    if not valid_gpus:
        sys.exit(
            f"错误: 未找到支持 {codec.upper()} 的编码器。\n"
            "请安装包含相应编码器的 ffmpeg 版本。"
        )

    if len(valid_gpus) == 1:
        gpu_type, gpu_name, encoder = valid_gpus[0]
        print(f"\n使用编码器: {encoder} ({gpu_name})")
        return gpu_type, encoder

    choices = []
    for i, (gpu_type, gpu_name, encoder) in enumerate(valid_gpus):
        recommend = " (推荐)" if i == 0 and gpu_type != "cpu" else ""
        name = f"{GPU_NAMES.get(gpu_type, gpu_type)}: {gpu_name}{recommend} [{encoder}]"
        choices.append((name, i))

    idx = interactive_select(f"请选择用于 {codec.upper()} 编码的设备:", choices)
    gpu_type, gpu_name, encoder = valid_gpus[idx]
    print(f"已选择: {GPU_NAMES.get(gpu_type, gpu_type)} - {encoder}")
    return gpu_type, encoder


def prompt_crf_choice(codec: str) -> int:
    """提示用户输入 CRF 值。"""
    if codec == "h265":
        default_crf, max_crf = 23, 51
    else:  # av1
        default_crf, max_crf = 23, 63

    return interactive_number(
        f"请输入 CRF 值（值越小质量越高）:",
        default=default_crf,
        min_val=0,
        max_val=max_crf,
    )


def build_video_codec_args(
    codec: str, lossless: bool, crf: int, encoder: str, gpu: str
) -> list:
    """根据编码模式返回视频编码参数列表。"""
    if codec == "copy":
        return ["-c:v", "copy"]

    args = ["-c:v", encoder]

    # H.265 编码参数
    if codec == "h265":
        if gpu == "cpu":
            # libx265 软件编码
            args += ["-crf", str(crf), "-preset", "medium"]
        elif gpu == "nvidia":
            # NVENC 硬件编码
            # NVENC 使用 -cq 代替 -crf，范围 0-51
            args += ["-rc", "vbr", "-cq", str(crf), "-preset", "p4"]
        elif gpu == "amd":
            # AMF 硬件编码
            args += ["-rc", "cqp", "-qp_i", str(crf), "-qp_p", str(crf)]
        elif gpu == "intel":
            # QSV 硬件编码
            args += ["-global_quality", str(crf), "-preset", "medium"]

    # AV1 编码参数
    elif codec == "av1":
        if lossless:
            if encoder == "libsvtav1":
                args += ["-svtav1-params", "lossless=1"]
            elif encoder == "libaom-av1":
                args += ["-lossless", "1"]
            elif encoder == "librav1e":
                args += ["-qp", "0"]
            elif gpu == "nvidia":
                # NVENC AV1 不支持真正无损，使用最高质量
                args += ["-rc", "constqp", "-qp", "0"]
            else:
                args += ["-crf", "0"]
        else:
            if gpu == "cpu":
                args += ["-crf", str(crf)]
                if encoder == "libsvtav1":
                    args += ["-preset", "6"]
                elif encoder == "libaom-av1":
                    args += ["-cpu-used", "4", "-row-mt", "1"]
            elif gpu == "nvidia":
                args += ["-rc", "vbr", "-cq", str(crf), "-preset", "p4"]
            elif gpu == "amd":
                args += ["-rc", "cqp", "-qp_i", str(crf), "-qp_p", str(crf)]
            elif gpu == "intel":
                args += ["-global_quality", str(crf), "-preset", "medium"]

    return args


def auto_merge_mode() -> None:
    """自动检测模式：扫描当前目录并合并检测到的音视频配对。"""
    script_dir = Path(__file__).parent
    print(f"扫描目录: {script_dir}")

    pairs = detect_media_pairs(script_dir)

    if not pairs:
        print("未检测到可合并的音视频文件配对。")
        print("文件命名需符合格式: <前缀>-<流ID>.mp4")
        print("例如: 36502112568-1-30116.mp4 和 36502112568-1-30280.mp4")
        sys.exit(0)

    print(f"\n检测到 {len(pairs)} 组可合并的文件:")
    for i, (video, audio, output) in enumerate(pairs, 1):
        print(f"\n  [{i}] {output.name}")
        print(f"      视频: {video.name}")
        print(f"      音频: {audio.name}")

    if not interactive_confirm("是否继续合并？"):
        print("已取消")
        sys.exit(0)

    # 检测可用编码器和 GPU
    print("\n正在检测系统编码器和 GPU...")
    available_encoders = get_available_encoders()
    gpus = detect_gpus()

    print("检测到的 GPU:")
    for gpu_type, gpu_name in gpus:
        print(f"  - {GPU_NAMES.get(gpu_type, gpu_type)}: {gpu_name}")

    # 选择编码方式
    codec, lossless, crf, gpu, encoder = prompt_encoding_choice(
        available_encoders, gpus
    )

    # 执行合并
    for video, audio, output in pairs:
        print(f"\n{'='*60}")
        print(f"正在合并: {output.name}")
        merge(str(video), str(audio), str(output), codec, lossless, crf, gpu, encoder)

    print(f"\n{'='*60}")
    print(f"全部完成！共合并 {len(pairs)} 个文件")


def merge(
    video_path: str,
    audio_path: str,
    output_path: str,
    codec: str,
    lossless: bool,
    crf: int,
    gpu: str = "cpu",
    encoder: str = "",
) -> None:
    """执行音视频合并。"""
    for p in (video_path, audio_path):
        if not Path(p).is_file():
            sys.exit(f"错误: 文件不存在 -> {p}")

    # 如果未指定编码器，自动检测
    if codec != "copy" and not encoder:
        available = get_available_encoders()
        encoder = detect_encoder(codec, gpu, available)
        if not encoder:
            sys.exit(f"错误: 未找到支持 {codec.upper()} 的编码器")

    video_codec_args = build_video_codec_args(codec, lossless, crf, encoder, gpu)

    if codec != "copy":
        mode = "真正无损" if lossless else f"CRF={crf}"
        print(f"编码模式: {codec.upper()} {mode}")
        print(f"编码器: {encoder} ({GPU_NAMES.get(gpu, gpu)})")

    cmd = [
        "ffmpeg",
        "-i",
        video_path,
        "-i",
        audio_path,
        *video_codec_args,
        "-c:a",
        "copy",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-y",
        output_path,
    ]

    print("执行命令:", " ".join(cmd))
    result = subprocess.run(cmd)

    if result.returncode != 0:
        sys.exit(f"ffmpeg 执行失败，返回码: {result.returncode}")

    print(f"\n合并完成 -> {output_path}")

    # 重编码时显示大小对比
    if codec != "copy":
        src_size = Path(video_path).stat().st_size + Path(audio_path).stat().st_size
        out_size = Path(output_path).stat().st_size
        ratio = (1 - out_size / src_size) * 100 if src_size else 0

        def _fmt_size(n: int) -> str:
            for unit in ("B", "KB", "MB", "GB"):
                if abs(n) < 1024:
                    return f"{n:.2f} {unit}"
                n /= 1024
            return f"{n:.2f} TB"

        # ANSI 颜色: 绿色=压缩, 红色=膨胀
        color = "\033[32m" if ratio > 0 else "\033[31m"
        reset = "\033[0m"

        print(f"\n  编码前大小: {_fmt_size(src_size)}")
        print(f"  编码后大小: {_fmt_size(out_size)}")
        if ratio > 0:
            print(f"  压缩率:     {color}-{ratio:.1f}%{reset}")
        else:
            print(f"  体积变化:   {color}+{abs(ratio):.1f}%{reset}")


def main() -> None:
    # 若无参数，进入自动检测模式
    if len(sys.argv) == 1:
        auto_merge_mode()
        return

    parser = argparse.ArgumentParser(
        description="将分离的视频 MP4 与音频 MP4 合并为单个 MP4 文件（需要已安装 ffmpeg）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("video", nargs="?", help="纯视频 MP4 文件路径")
    parser.add_argument("audio", nargs="?", help="纯音频 MP4 文件路径")
    parser.add_argument("output", nargs="?", help="输出 MP4 文件路径")
    parser.add_argument(
        "--h265",
        action="store_true",
        help="使用 H.265/HEVC 编码视频",
    )
    parser.add_argument(
        "--av1",
        action="store_true",
        help="使用 AV1 编码视频以减小文件体积",
    )
    parser.add_argument(
        "--gpu",
        choices=["nvidia", "amd", "intel", "cpu"],
        default=None,
        help="指定用于编码的 GPU（默认: 自动选择独立显卡）",
    )
    parser.add_argument(
        "--lossless",
        action="store_true",
        help="真正无损编码（需配合 --av1 使用）",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=23,
        metavar="N",
        help="CRF 质量值，H.265 范围 0~51，AV1 范围 0~63，默认 23",
    )
    args = parser.parse_args()

    # 检查必需参数
    if not all([args.video, args.audio, args.output]):
        parser.error(
            "手动模式需要提供 video、audio 和 output 三个参数，"
            "或不提供参数进入自动检测模式"
        )

    if args.h265 and args.av1:
        parser.error("--h265 和 --av1 不能同时使用")
    if args.lossless and not args.av1:
        parser.error("--lossless 需要配合 --av1 一起使用")

    # 确定编码类型
    if args.h265:
        codec = "h265"
        if not (0 <= args.crf <= 51):
            parser.error("H.265 的 --crf 范围为 0 ~ 51")
    elif args.av1:
        codec = "av1"
        if not (0 <= args.crf <= 63):
            parser.error("AV1 的 --crf 范围为 0 ~ 63")
    else:
        codec = "copy"

    # 检测编码器和 GPU
    gpu = args.gpu
    encoder = ""

    if codec != "copy":
        available = get_available_encoders()
        gpus = detect_gpus()

        if gpu is None:
            # 自动选择最优 GPU
            for gpu_type, _ in gpus:
                enc = detect_encoder(codec, gpu_type, available)
                if enc:
                    gpu = gpu_type
                    encoder = enc
                    break
        else:
            encoder = detect_encoder(codec, gpu, available)

        if not encoder:
            sys.exit(
                f"错误: 未找到支持 {codec.upper()} 的编码器。\n"
                f"尝试的 GPU: {gpu or '自动检测'}"
            )

        print(f"使用编码器: {encoder} ({GPU_NAMES.get(gpu, gpu)})")

    merge(
        args.video,
        args.audio,
        args.output,
        codec,
        args.lossless,
        args.crf,
        gpu or "cpu",
        encoder,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已取消操作。")
        sys.exit(130)
