# merge_av

将两个分离的 MP4 文件（一个仅含视频、一个仅含音频）合并为单个含音视频的 MP4。
支持直接流复制（默认）、H.265 或 AV1 重编码，**支持 GPU 硬件加速**。

## 依赖

- Python 3.7+
- [ffmpeg](https://ffmpeg.org/download.html)（需已安装并加入系统 PATH）
- [InquirerPy](https://github.com/kazhala/InquirerPy)（可选，提供交互式选择菜单）

```bash
pip install InquirerPy
```

> 未安装 InquirerPy 时自动降级为键盘输入序号模式，功能不受影响。

## 支持的编码器

| 类型 | H.265/HEVC | AV1 |
|------|------------|-----|
| **NVIDIA** (NVENC) | `hevc_nvenc` | `av1_nvenc` |
| **AMD** (AMF) | `hevc_amf` | `av1_amf` |
| **Intel** (QSV) | `hevc_qsv` | `av1_qsv` |
| **CPU** (软件) | `libx265` | `libsvtav1` / `libaom-av1` |

## 用法

### 自动检测模式（推荐）

直接运行脚本，无需参数：

```bash
python merge_av.py
```

程序会自动：

1. 扫描当前目录，检测符合 B站等平台命名格式的文件配对
2. 列出检测到的视频/音频配对
3. **交互式选择编码方式**（直接复制 / H.265 / AV1）
4. **交互式选择 GPU**（默认优先使用独立显卡）
5. 批量执行合并

交互式菜单支持以下操作方式（需安装 InquirerPy）：

- **↑↓ 方向键** 移动光标后 Enter 确认
- **数字键 1-9** 快速跳转到对应选项

支持的文件命名格式：`<前缀>-<流ID>.mp4`，例如：

- `36502112568-1-30116.mp4`（视频）
- `36502112568-1-30280.mp4`（音频）

### 手动模式

```bash
python merge_av.py <video.mp4> <audio.mp4> <output.mp4> [选项]
```

| 选项 | 说明 |
|------|------|
| _(无)_ | 直接复制流，最快，零质量损失 |
| `--h265` | H.265/HEVC 编码（兼容性好） |
| `--av1` | AV1 编码（体积最小） |
| `--av1 --lossless` | AV1 数学意义上的真正无损编码 |
| `--crf N` | 自定义质量，H.265: **0~51**，AV1: **0~63**，默认 **23** |
| `--gpu nvidia` | 使用 NVIDIA GPU 加速 |
| `--gpu amd` | 使用 AMD GPU 加速 |
| `--gpu intel` | 使用 Intel 核显加速 |
| `--gpu cpu` | 强制使用 CPU 软件编码 |

## 示例

```bash
# 自动检测并合并（交互式选择编码和 GPU）
python merge_av.py

# 直接合并（不重编码）
python merge_av.py video_only.mp4 audio_only.mp4 output.mp4

# H.265 编码（自动选择最佳 GPU）
python merge_av.py video_only.mp4 audio_only.mp4 output.mp4 --h265

# H.265 编码，指定使用 NVIDIA GPU
python merge_av.py video_only.mp4 audio_only.mp4 output.mp4 --h265 --gpu nvidia

# AV1 视觉无损（推荐，体积最小）
python merge_av.py video_only.mp4 audio_only.mp4 output.mp4 --av1

# AV1 编码，使用 AMD GPU 加速
python merge_av.py video_only.mp4 audio_only.mp4 output.mp4 --av1 --gpu amd

# AV1 真正无损
python merge_av.py video_only.mp4 audio_only.mp4 output.mp4 --av1 --lossless

# AV1 自定义质量（值越小质量越高）
python merge_av.py video_only.mp4 audio_only.mp4 output.mp4 --av1 --crf 18
```

## GPU 加速说明

程序会自动检测系统中的显卡，并按以下优先级选择：

1. **NVIDIA** (NVENC) - 速度快，质量好
2. **AMD** (AMF) - 速度快
3. **Intel** (QSV) - 集成显卡加速
4. **CPU** (软件编码) - 兼容性最好，但速度较慢

> **提示：** 硬件加速编码速度通常是软件编码的 5-10 倍，但压缩率略低。
> 追求最小体积请使用 CPU 软件编码；追求速度请使用 GPU 硬件加速。

## 编码格式对比

| 格式 | 压缩率 | 兼容性 | 编码速度 |
|------|--------|--------|----------|
| **直接复制** | - | 最好 | 最快 |
| **H.265/HEVC** | 好 | 好 | 中等 |
| **AV1** | 最好 | 一般 | 较慢 |

> **推荐：**
>
> - 只需合并不重编码 → 直接复制
> - 需要广泛兼容性 → H.265
> - 追求最小体积 → AV1
