"""One local parse/conversion request; no user paths or network operations."""

import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

MAX_TEXT = 200000


def safe_docx(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 2000 or sum(e.file_size for e in entries) > 64 * 1024 * 1024:
            raise ValueError("DOCX解压后超过范围。")
        for entry in entries:
            if entry.file_size > 10 * 1024 * 1024 or (
                entry.file_size > 1000 * max(1, entry.compress_size)
            ):
                raise ValueError("DOCX附件或压缩率超过范围。")
            if entry.filename.endswith(".rels"):
                from xml.etree import ElementTree

                for rel in ElementTree.fromstring(archive.read(entry)):
                    if rel.attrib.get("TargetMode") == "External" and not rel.attrib.get(
                        "Type", ""
                    ).endswith("/hyperlink"):
                        raise ValueError("DOCX包含外部附件引用，拒绝转换。")


def pdf(data):
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data), strict=True)
    if reader.is_encrypted or len(reader.pages) > 200:
        raise ValueError("暂不处理加密或超过200页的PDF。")
    return reader


def extract(data, suffix):
    warnings, segments, truncated = [], [], False
    if suffix == ".pdf":
        reader = pdf(data)
        values = (
            (f"第{i + 1}页", f"页{i + 1}", page.extract_text() or "")
            for i, page in enumerate(reader.pages)
        )
        units = len(reader.pages)
    elif suffix == ".docx":
        from docx import Document

        safe_docx(data)
        doc = Document(io.BytesIO(data))
        from docx.text.paragraph import Paragraph

        values = []
        paragraph_number, table_number = 0, 0
        for block in doc.iter_inner_content():
            if isinstance(block, Paragraph):
                paragraph_number += 1
                anchor = f"段落{paragraph_number}"
                values.append((anchor, anchor, block.text))
            else:
                table_number += 1
                for index, row in enumerate(block.rows):
                    anchor = f"表{table_number}行{index + 1}"
                    values.append((anchor, anchor, " | ".join(cell.text for cell in row.cells)))
        units = len(values)
    else:
        text = data.decode("utf-8-sig")
        lines = text.splitlines()
        units = len(lines)
        values = ((f"第{i + 1}行", f"行{i + 1}", line) for i, line in enumerate(lines))
    remaining = MAX_TEXT
    for label, anchor, text in values:
        if not text.strip():
            continue
        if not remaining or len(segments) >= 2000:
            truncated = True
            break
        segments.append({"label": label, "anchor": anchor, "text": text[:remaining]})
        truncated |= len(text) > remaining
        remaining -= min(remaining, len(text))
    if not segments:
        warnings.append("未抽取到正文，可能是扫描件；请使用截图OCR或带文字层的版本。")
    if truncated:
        warnings.append("正文已截断；总结和检索只覆盖已抽取范围。")
    if suffix == ".docx":
        warnings.append("DOCX抽取覆盖正文段落与表格行；不含页眉、脚注和图片正文。")
    return {"segments": segments, "units": units, "warnings": warnings, "truncated": truncated}


def transform(files, request):
    from pypdf import PdfWriter

    writer = PdfWriter()
    kind = request["kind"]
    if kind == "docx_pdf":
        if len(files) != 1 or files[0]["suffix"] != ".docx":
            raise ValueError("请选择一个DOCX文件。")
        safe_docx(files[0]["data"])
        engine = Path(
            os.environ.get(
                "HERTA_LIBREOFFICE",
                str(
                    Path(__file__).resolve().parents[3]
                    / ".local/libreoffice/unpacked/program/soffice.com"
                ),
            )
        )
        if not engine.is_file():
            raise ValueError("本机LibreOffice转换引擎未准备好。")
        with tempfile.TemporaryDirectory(prefix="herta-docx-") as folder:
            source = Path(folder) / "input.docx"
            source.write_bytes(files[0]["data"])
            profile = (Path(folder) / "profile").as_uri()
            result = subprocess.run(
                [
                    str(engine),
                    f"-env:UserInstallation={profile}",
                    "--headless",
                    "--nologo",
                    "--nodefault",
                    "--norestore",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    folder,
                    str(source),
                ],
                capture_output=True,
                timeout=30,
                creationflags=0x08000000 if os.name == "nt" else 0,
            )
            output = Path(folder) / "input.pdf"
            if result.returncode or not output.is_file():
                raise ValueError("DOCX转PDF失败，请检查文档。")
            data = output.read_bytes()
            pdf(data)
            return data
    if kind == "images":
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = 16000000
        images = []
        for file in files:
            image = Image.open(io.BytesIO(file["data"]))
            if image.width * image.height > 16000000:
                raise ValueError("图片超过1600万像素。")
            images.append(image.convert("RGB"))
        output = io.BytesIO()
        images[0].save(output, format="PDF", save_all=True, append_images=images[1:])
        return output.getvalue()
    for file in files:
        reader = pdf(file["data"])
        chosen = request["pages"] if kind == "split" else range(1, len(reader.pages) + 1)
        for number in chosen:
            if not 1 <= number <= len(reader.pages):
                raise ValueError("页码超出PDF范围。")
            page = reader.pages[number - 1]
            if kind == "rotate":
                page.rotate(request["rotation"])
            writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def main():
    try:
        raw = sys.stdin.buffer.read(90 * 1024 * 1024 + 1)
        if len(raw) > 90 * 1024 * 1024:
            raise ValueError("文档请求超过范围。")
        request = json.loads(raw)
        files = [
            {**file, "data": base64.b64decode(file["data"], validate=True)}
            for file in request["files"]
        ]
        if request["kind"] == "read":
            result = extract(files[0]["data"], files[0]["suffix"])
        else:
            data = transform(files, request)
            if len(data) > 32 * 1024 * 1024:
                raise ValueError("转换结果超过32 MiB。")
            result = {"data": base64.b64encode(data).decode()}
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=True))
    except Exception as error:
        message = (
            str(error) if isinstance(error, ValueError) else "文档损坏、格式不支持或处理超时。"
        )
        print(json.dumps({"ok": False, "error": message}, ensure_ascii=True))


if __name__ == "__main__":
    main()
