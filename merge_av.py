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

# 编码器配置
# 格式: {gpu_type: {codec: encoder_name}}
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
# 视频流 ID 通常以 30 开头且较小，音频流 ID 通常以 30 开头且较大
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

        # 尝试识别视频和音频文件
        video_file = None
        audio_file = None

        for stream_id, filepath in files:
            if stream_id in VIDEO_STREAM_IDS:
                video_file = filepath
            elif stream_id in AUDIO_STREAM_IDS:
                audio_file = filepath

        # 如果无法通过已知 ID 识别，使用启发式方法：较小的 ID 通常是视频
        if video_file is None or audio_file is None:
            sorted_files = sorted(files, key=lambda x: int(x[0]))
            if len(sorted_files) >= 2:
                # 检查文件大小：视频文件通常比音频大
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


def prompt_encoding_choice() -> tuple:
    """
    交互式提示用户选择编码方式。
    返回: (av1: bool, lossless: bool, crf: int)
    """
    print("\n请选择编码方式:")
    print("  [1] 直接复制（最快，零质量损失）")
    print("  [2] AV1 视觉无损编码（CRF=23，体积小 ~50%）")
    print("  [3] AV1 真正无损编码（数学意义无损）")
    print("  [4] AV1 自定义 CRF 值")
    print()

    while True:
        choice = input("请输入选项 [1-4]，默认为 1: ").strip()
        if choice == "" or choice == "1":
            return False, False, 23
        elif choice == "2":
            return True, False, 23
        elif choice == "3":
            return True, True, 0
        elif choice == "4":
            while True:
                crf_input = input("请输入 CRF 值 [0-63]，默认为 23: ").strip()
                if crf_input == "":
                    return True, False, 23
                try:
                    crf = int(crf_input)
                    if 0 <= crf <= 63:
                        return True, False, crf
                    print("错误: CRF 范围为 0~63，请重新输入")
                except ValueError:
                    print("错误: 请输入有效数字")
        else:
            print("无效选项，请输入 1-4")


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

    # 确认是否继续
    confirm = input("\n是否继续合并？[Y/n]: ").strip().lower()
    if confirm == "n":
        print("已取消")
        sys.exit(0)

    # 选择编码方式
    av1, lossless, crf = prompt_encoding_choice()

    # 执行合并
    for video, audio, output in pairs:
        print(f"\n{'='*60}")
        print(f"正在合并: {output.name}")
        merge(str(video), str(audio), str(output), av1, lossless, crf)

    print(f"\n{'='*60}")
    print(f"全部完成！共合并 {len(pairs)} 个文件")


def detect_av1_encoder() -> str:
    """检测当前 ffmpeg 支持的 AV1 编码器，返回第一个可用的。"""
    result = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
    for enc in AV1_ENCODERS:
        if enc in result.stdout:
            return enc
    sys.exit(
        "错误: 当前 ffmpeg 不支持任何 AV1 编码器。\n"
        "请安装包含 libsvtav1 或 libaom-av1 支持的 ffmpeg 版本。\n"
        "下载地址: https://ffmpeg.org/download.html"
    )


def build_video_codec_args(av1: bool, lossless: bool, crf: int, encoder: str) -> list:
    """根据编码模式返回视频编码参数列表。"""
    if not av1:
        return ["-c:v", "copy"]

    args = ["-c:v", encoder]

    if lossless:
        if encoder == "libsvtav1":
            # SVT-AV1 通过 --lossless 1 实现无损
            args += ["-svtav1-params", "lossless=1"]
        elif encoder == "libaom-av1":
            args += ["-lossless", "1"]
        elif encoder == "librav1e":
            args += ["-qp", "0"]
    else:
        # CRF 模式：视觉无损推荐 0-23，默认 23
        args += ["-crf", str(crf)]
        if encoder == "libsvtav1":
            # SVT-AV1 需要同时指定 -preset（0=最慢最好 ~ 13=最快）
            args += ["-preset", "6"]
        elif encoder == "libaom-av1":
            # libaom 默认速度极慢，-cpu-used 控制速度（0=最慢 ~ 8=最快）
            args += ["-cpu-used", "4", "-row-mt", "1"]

    return args


def merge(
    video_path: str,
    audio_path: str,
    output_path: str,
    av1: bool,
    lossless: bool,
    crf: int,
) -> None:
    for p in (video_path, audio_path):
        if not Path(p).is_file():
            sys.exit(f"错误: 文件不存在 -> {p}")

    encoder = detect_av1_encoder() if av1 else ""
    video_codec_args = build_video_codec_args(av1, lossless, crf, encoder)

    if av1:
        mode = "真正无损" if lossless else f"视觉无损 (CRF={crf})"
        print(f"AV1 编码模式: {mode}，编码器: {encoder}")

    cmd = [
        "ffmpeg",
        "-i",
        video_path,
        "-i",
        audio_path,
        *video_codec_args,
        "-c:a",
        "copy",  # 音频流直接复制
        "-map",
        "0:v:0",  # 取第一个输入的视频流
        "-map",
        "1:a:0",  # 取第二个输入的音频流
        "-y",
        output_path,
    ]

    print("执行命令:", " ".join(cmd))
    result = subprocess.run(cmd)

    if result.returncode != 0:
        sys.exit(f"ffmpeg 执行失败，返回码: {result.returncode}")

    print(f"\n合并完成 -> {output_path}")


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
        "--av1",
        action="store_true",
        help="使用 AV1 编码视频以减小文件体积（默认: 直接复制流）",
    )
    parser.add_argument(
        "--lossless",
        action="store_true",
        help="AV1 真正无损编码（需配合 --av1 使用，文件体积大于 CRF 模式）",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=23,
        metavar="N",
        help="AV1 CRF 质量值，范围 0（无损）~ 63（最差），默认 23（视觉无损）",
    )
    args = parser.parse_args()

    # 检查必需参数
    if not all([args.video, args.audio, args.output]):
        parser.error(
            "手动模式需要提供 video、audio 和 output 三个参数，或不提供参数进入自动检测模式"
        )

    if args.lossless and not args.av1:
        parser.error("--lossless 需要配合 --av1 一起使用")
    if not (0 <= args.crf <= 63):
        parser.error("--crf 范围为 0 ~ 63")

    merge(args.video, args.audio, args.output, args.av1, args.lossless, args.crf)


if __name__ == "__main__":
    main()
