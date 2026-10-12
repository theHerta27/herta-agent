import unittest

from scripts.gpt_sovits.speech_text import speech_chunks


class SpeechTextTests(unittest.TestCase):
    def test_short_first_sentence_and_long_tail_are_not_dropped(self):
        text = "来了？今天想弄清什么。\n" + "连续文本" * 100 + "最后的问题。"
        chunks = speech_chunks(text)
        self.assertEqual("".join(chunks), text)
        self.assertLessEqual(max(map(len, chunks)), 120)
        self.assertIn("来了？今天想弄清什么。", chunks[0])
