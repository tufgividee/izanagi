import json
import unittest

from izanagi.base import _filter_content, _filter_markdown, _filter_notebook


class MarkdownFilterTests(unittest.TestCase):
    def test_embedded_base64_image_payload_is_removed(self):
        content = (
            "# Results\n\n"
            "![training chart](data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAUA)\n"
        )
        config = {
            "markdown": {
                "strip_embedded_media": True,
                "preserve_alt_text": True,
                "preserve_image_reference": True,
            }
        }

        filtered = _filter_markdown(content, config)

        self.assertIn("training chart", filtered)
        self.assertNotIn("iVBORw0KGgoAAAANSUhEUgAAAAUA", filtered)

    def test_remote_image_reference_is_preserved(self):
        content = "![architecture](https://example.com/architecture.png)\n"
        config = {
            "markdown": {
                "strip_embedded_media": True,
                "preserve_alt_text": True,
                "preserve_image_reference": True,
            }
        }

        filtered = _filter_markdown(content, config)

        self.assertIn("architecture", filtered)
        self.assertIn("https://example.com/architecture.png", filtered)

    def test_filter_can_be_disabled(self):
        content = "![chart](data:image/png;base64,ABCDEF123456)\n"
        config = {
            "markdown": {
                "strip_embedded_media": False,
                "preserve_alt_text": True,
                "preserve_image_reference": True,
            }
        }

        filtered = _filter_markdown(content, config)

        self.assertEqual(filtered, content)


class NotebookFilterTests(unittest.TestCase):
    def setUp(self):
        self.notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "metadata": {},
                    "source": [
                        "# Results\n",
                        "![chart](data:image/png;base64,ABCDEF123456)\n",
                    ],
                },
                {
                    "cell_type": "code",
                    "execution_count": 7,
                    "metadata": {},
                    "source": ["print('hello')"],
                    "outputs": [
                        {
                            "output_type": "stream",
                            "name": "stdout",
                            "text": ["hello\n"],
                        }
                    ],
                },
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }

    def _config(self, *, include_source=True):
        return {
            "ipynb": {
                "include_source": include_source,
                "include_outputs": False,
                "include_execution_counts": False,
            },
            "markdown": {
                "strip_embedded_media": True,
                "preserve_alt_text": True,
                "preserve_image_reference": True,
            },
        }

    def test_notebook_source_outputs_and_execution_counts_follow_config(self):
        config = self._config()

        filtered = json.loads(
            _filter_notebook(json.dumps(self.notebook), config)
        )

        markdown_cell = filtered["cells"][0]
        code_cell = filtered["cells"][1]

        self.assertIn("# Results", "".join(markdown_cell["source"]))
        self.assertIn("chart", "".join(markdown_cell["source"]))
        self.assertNotIn(
            "ABCDEF123456",
            "".join(markdown_cell["source"]),
        )

        self.assertIn("print('hello')", "".join(code_cell["source"]))
        self.assertNotIn("outputs", code_cell)
        self.assertNotIn("execution_count", code_cell)

    def test_notebook_source_can_be_excluded(self):
        config = self._config(include_source=False)

        filtered = json.loads(
            _filter_notebook(json.dumps(self.notebook), config)
        )

        for cell in filtered["cells"]:
            self.assertNotIn("source", cell)

    def test_malformed_notebook_json_is_preserved(self):
        content = '{"cells": [not valid JSON]}'
        config = self._config()

        self.assertEqual(_filter_notebook(content, config), content)

    def test_filter_content_dispatches_by_extension(self):
        content = json.dumps(self.notebook).encode("utf-8")
        config = self._config()

        filtered = json.loads(
            _filter_content("example.ipynb", content, config)
        )

        self.assertNotIn("outputs", filtered["cells"][1])


if __name__ == "__main__":
    unittest.main()