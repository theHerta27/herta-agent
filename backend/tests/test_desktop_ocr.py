import io
import os
import unittest


@unittest.skipUnless(os.name == "nt", "Windows OCR")
class DesktopOCRTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_local_chinese_ocr_and_cleanup(self):
        from PIL import Image, ImageDraw, ImageFont

        from herta_agent.desktop.service import DesktopService

        image = Image.new("RGB", (1000, 220), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 56)
        draw.text((30, 40), "黑塔助手 HERTA 2026", font=font, fill="black")
        output = io.BytesIO()
        image.save(output, format="PNG")
        service = DesktopService()
        result = await service.ocr(output.getvalue())
        self.assertIn("2026", result["text"])
        self.assertIn("黑塔", result["text"])
        self.assertEqual(service.active_count, 0)
        await service.shutdown()

    async def test_invalid_oversized_and_truncated_images_are_rejected(self):
        from herta_agent.desktop.service import DesktopService
        from herta_agent.workspace.paths import WorkspaceError

        service = DesktopService()
        for value in (b"invalid", b"x" * 4_000_001, b"\x89PNG\r\n\x1a\n"):
            with self.assertRaises(WorkspaceError):
                await service.ocr(value)
        self.assertEqual(service.active_count, 0)
