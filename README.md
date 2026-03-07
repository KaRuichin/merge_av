# merge_av

将两个分离的 MP4 文件（一个仅含视频、一个仅含音频）合并为单个含音视频的 MP4。
支持直接流复制（默认）或 AV1 重编码以大幅减小文件体积。

## 依赖

- Python 3.7+
- [ffmpeg](https://ffmpeg.org/download.html)（需已安装并加入系统 PATH，且包含 AV1 编码器）

## 用法

### 自动检测模式（推荐）

直接运行脚本，无需参数：

```bash
python merge_av.py
```

程序会自动：

1. 扫描当前目录，检测符合 B站等平台命名格式的文件配对
2. 列出检测到的视频/音频配对
3. 交互式提示选择编码方式
4. 批量执行合并

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
| `--av1` | AV1 视觉无损编码（CRF=23），体积比 H.264 小 ~50% |
| `--av1 --lossless` | AV1 数学意义上的真正无损编码 |
| `--av1 --crf N` | 自定义质量，**0**=无损，**23**=默认，**63**=最差 |

## 示例

```bash
# 自动检测并合并（交互式选择编码）
python merge_av.py

# 直接合并（不重编码）
python merge_av.py video_only.mp4 audio_only.mp4 output.mp4

# AV1 视觉无损（推荐，体积最小）
python merge_av.py video_only.mp4 audio_only.mp4 output.mp4 --av1

# AV1 真正无损
python merge_av.py video_only.mp4 audio_only.mp4 output.mp4 --av1 --lossless

# AV1 自定义质量（值越小质量越高）
python merge_av.py video_only.mp4 audio_only.mp4 output.mp4 --av1 --crf 18
```

## AV1 编码说明

程序会按优先级自动选择可用的 AV1 编码器：

| 编码器 | 特点 |
|--------|------|
| `libsvtav1` | 速度快（推荐），Meta/Intel 出品 |
| `libaom-av1` | 压缩率最高，但速度慢 |
| `librav1e` | Xiph 出品，折中方案 |

> **提示：** CRF 0~23 通常视觉无损，相比 H.264 体积减少 40~60%，编码时间较长属正常现象。
