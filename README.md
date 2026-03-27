# merge_av

将两个分离的 MP4 文件（一个仅含视频、一个仅含音频）合并为单个含音视频的 MP4。
支持直接流复制（默认）、H.265 或 AV1 重编码，**支持 GPU 硬件加速**，并提供**智能优化（自动试压）**模式。

## 依赖

- Python 3.7+
- [ffmpeg](https://ffmpeg.org/download.html)（需已安装并加入系统 PATH）
- [InquirerPy](https://github.com/kazhala/InquirerPy)（可选，提供交互式选择菜单）

```bash
pip install InquirerPy
```

> 未安装 InquirerPy 时自动降级为键盘输入序号模式，功能不受影响。

## Windows 构建（生成独立 .exe）

项目支持使用 PyInstaller 打包为单文件可执行程序，无需安装 Python 即可运行。

### 前置条件

- 已安装 Python 3.7+ 并配置好虚拟环境
- 已安装 [ffmpeg](https://ffmpeg.org/download.html) 并加入系统 PATH

### 构建步骤

```bat
REM 方式一：直接双击运行
build.bat

REM 方式二：命令行执行
.venv\Scripts\activate
pip install pyinstaller
pyinstaller merge_av.spec --clean --noconfirm
```

构建完成后，可执行文件位于 `dist\merge_av.exe`。

> **注意：** 打包后的 .exe 仍需系统中已安装 ffmpeg 才能正常工作。

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
3. **交互式选择编码方式**（直接复制 / 智能优化 / H.265 / AV1）
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
| `--auto-optimize` | 智能优化：自动试压并选择满足质量阈值下体积最小的方案 |
| `--h265` | H.265/HEVC 编码（兼容性好） |
| `--av1` | AV1 编码（体积最小） |
| `--av1 --lossless` | AV1 数学意义上的真正无损编码 |
| `--optimize-preset {fast,balanced,quality}` | 智能优化预设：快 / 平衡 / 高精度（默认 balanced） |
| `--quality-metric {ssim,vmaf}` | 智能优化质量指标（默认 ssim） |
| `--quality-threshold N` | 自定义质量阈值（SSIM 默认 0.99，VMAF 默认 95） |
| `--sample-seconds N` | 每段采样时长（默认由预设决定） |
| `--sample-count N` | 采样段数量（默认由预设决定） |
| `--min-saving N` | 最小节省阈值 %（低于此值回退 copy，默认由预设决定） |
| `--crf N` | 自定义质量，H.265: **0~51**，AV1: **0~63**，默认 **23** |
| `--gpu nvidia` | 使用 NVIDIA GPU 加速 |
| `--gpu amd` | 使用 AMD GPU 加速 |
| `--gpu intel` | 使用 Intel 核显加速 |
| `--gpu cpu` | 强制使用 CPU 软件编码 |

> 约束：`--auto-optimize` 不能与 `--h265 / --av1 / --lossless` 同时使用。

## 示例

```bash
# 自动检测并合并（交互式选择编码和 GPU）
python merge_av.py

# 智能优化（自动试压，默认平衡预设）
python merge_av.py video_only.mp4 audio_only.mp4 output.mp4 --auto-optimize

# 智能优化（快速预设，优先速度）
python merge_av.py video_only.mp4 audio_only.mp4 output.mp4 --auto-optimize --optimize-preset fast

# 智能优化（高精度预设，优先效果）
python merge_av.py video_only.mp4 audio_only.mp4 output.mp4 --auto-optimize --optimize-preset quality

# 智能优化 + 更严格 SSIM 阈值
python merge_av.py video_only.mp4 audio_only.mp4 output.mp4 --auto-optimize --quality-metric ssim --quality-threshold 0.995

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

## 智能优化说明

智能优化模式会：

1. 根据可用编码器构建候选方案（H.265/AV1 + 多组 CRF）
2. 在视频多个采样片段上进行试编码
3. 计算质量指标（`SSIM` 或 `VMAF`）
4. 在“质量达到阈值”的候选中选择预计体积最小者
5. 如果预计节省低于 `--min-saving`，自动回退为 `copy`

预设默认参数：

- `fast`：`sample-seconds=8`，`sample-count=2`，`min-saving=3`
- `balanced`：`sample-seconds=12`，`sample-count=3`，`min-saving=5`
- `quality`：`sample-seconds=18`，`sample-count=5`，`min-saving=2`

> 使用 `--quality-metric vmaf` 时，如果当前 ffmpeg 未包含 `libvmaf`，程序会自动回退到 `SSIM`。

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
