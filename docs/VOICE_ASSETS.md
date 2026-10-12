# 大黑塔音色资源

用户于2026-10-12授权本机使用、改名和移动 `theHerta` 资源。7个文件已整理至本机忽略目录 `models/voice/the-herta/v2proplus/`；权重、参考音频及原始 `大黑塔.zip` 不提交 Git。

| 文件 | 用途 | SHA256 |
| --- | --- | --- |
| `gpt.ckpt` | GPT 权重，295个张量 | `42a7603edab3ee53fd27f13bfb264b0a2a4235f484a72dd1d98bc33c7f8d4af1` |
| `sovits.pth` | v2ProPlus 权重，678个张量 | `22232f03b9184d43370d634719f8bda825dbda8d7381d395b6cc3ba8c5a30948` |
| `references/neutral.wav` | 中立，7.314秒 | `1a5ca77638a2b751091ac97fa52b0cc444489fa42de81ba515968a2f1088ed55` |
| `references/surprised.wav` | 吃惊，4.302秒 | `093df3f3ce4699424861b93512310375f557bc7885a31239f2c87acf7d44d93e` |
| `references/happy.wav` | 开心，3.245秒 | `54223327082775f9cd070cfbc17fbf3a22e3317d60363f745cfd0e3b4c44027f` |
| `references/angry.wav` | 生气，3.301秒 | `adbf68241fd01bdf6878c5bc490d247537e9c64d1d98bb57ffe6510eb3fc1aef` |
| `references/sad.wav` | 难过，7.623秒 | `2303f0673c58bd6237d818963520feec1e4a1cc6b2f1770b991749a40ccf45fc` |

全部参考音频为48kHz、单声道、16位PCM；没有重采样、裁剪或其他修改。`manifest.json` 记录原文件名、大小、哈希、时长与参考文本。参考文本来自文件名，尚未人工核对。另逐个比对原 ZIP 内7个成员，与规范化文件的 SHA256 全部一致。

`.pth` 的头部 ASCII `06` 是[GPT-SoVITS 官方定义的 v2ProPlus 标识](https://raw.githubusercontent.com/RVC-Boss/GPT-SoVITS/main/GPT_SoVITS/process_ckpt.py)，不是损坏证据。检查时只在内存中恢复 ZIP 头，原文件未修改。两组权重都使用 `torch.load(weights_only=True, map_location="cpu")` 读取；`.pth` 所需的 `utils.HParams` 按[官方配置类](https://raw.githubusercontent.com/RVC-Boss/GPT-SoVITS/main/GPT_SoVITS/utils.py)审阅后，映射到无方法、无导入、无自定义反序列化的本地空配置类，未运行上游 Python 或使用 `weights_only=False`。

上述为最初资源核验。V2.5现已接入独立GPT-SoVITS stdio Provider，真实本机CUDA推理、Piper切换、暂停继续/重播/取消及桌面回归通过；ASR继续使用faster-whisper。更新证据见PERSONALIZATION_ACCEPTANCE.md。权重与参考录音仅保存在本机及私人发行目录，不上传源码仓库。

复查整理后文件与原 ZIP：

```powershell
.\.venv\Scripts\python.exe scripts\verify_voice_resources.py
```
