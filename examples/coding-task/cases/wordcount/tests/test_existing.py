import contextlib
import io
import unittest

from wordcount.cli import main
from wordcount.counts import summarize


class ExistingTests(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(
            summarize("pear apple pear"),
            {"total": 3, "unique": 2, "counts": {"apple": 1, "pear": 2}},
        )

    def test_text_output(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main(["--text", "pear apple pear"])
        self.assertEqual(output.getvalue(), "total=3 unique=2\napple: 1\npear: 2\n")

    def test_empty_text_output(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main([])
        self.assertEqual(output.getvalue(), "total=0 unique=0\n")
