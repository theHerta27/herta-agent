"""Apply narrow, repeatable local inference hardening to the pinned upstream copy."""
import os
from pathlib import Path
import json
ROOT = Path(os.environ["HERTA_VOICE_RUNTIME"]).resolve() / "upstream"
patches_file = ROOT.parent / "upstream-patches.json"
patches = json.loads(patches_file.read_text(encoding="utf-8")) if patches_file.exists() else []
def replace(file, old, new):
    target = ROOT / file
    source = target.read_text(encoding="utf-8")
    if new in source:
        return
    assert old in source, file
    target.write_text(source.replace(old, new), encoding="utf-8")
    patches.append({"path": file, "before": old, "after": new})

target = ROOT / "GPT_SoVITS/process_ckpt.py"
source = target.read_text(encoding="utf-8")
marker = "\nfrom strict_loading import load_sovits_new\n"
if marker not in source:
    # Drop the entire original final function so unrestricted loading code cannot run.
    source = source[:source.index("def load_sovits_new(sovits_path):")] + marker
    target.write_text(source, encoding="utf-8")
    patches.append({"path": "GPT_SoVITS/process_ckpt.py", "change": "Replace final unrestricted loader with strict_loading.load_sovits_new"})
replace("GPT_SoVITS/TTS_infer_pack/TTS.py", "weights_only=False", "weights_only=True")
replace("GPT_SoVITS/sv.py", "weights_only=False", "weights_only=True")
replace("GPT_SoVITS/text/chinese2.py", "\nis_g2pw = True", "\nis_g2pw = False")
replace("GPT_SoVITS/text/LangSegmenter/langsegmenter.py", "fast_langdetect.infer.LangDetectConfig(cache_dir=Path(__file__).parent.parent.parent / \"pretrained_models\" / \"fast_langdetect\")", "fast_langdetect.infer.LangDetectConfig(custom_model_path=str(Path(fast_langdetect.__file__).parent / \"resources\" / \"lid.176.ftz\"), cache_dir=Path(__file__).parent.parent.parent / \"pretrained_models\" / \"fast_langdetect\")")
# Chinese-only local inference uses the maintained pypinyin fallback. This avoids
# G2PW's implicit online model download and unrestricted pickle pronunciation cache.
patches_file.write_text(json.dumps(patches, indent=2), encoding="utf-8")
print(json.dumps({"patches": len(patches)}))
