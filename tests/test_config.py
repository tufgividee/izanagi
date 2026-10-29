import unittest
from copy import deepcopy

from izanagi.config import load_default_config, validate_config


class ConfigTests(unittest.TestCase):
    def test_default_config_loads(self):
        config = load_default_config()
        self.assertIsInstance(config, dict)

    def test_default_sections_exist(self):
        config = load_default_config()

        self.assertIn("project", config)
        self.assertIn("scan", config)
        self.assertIn("inclusions", config["scan"])
        self.assertIn("exclusions", config["scan"])
        self.assertIn("preamble", config)

    def test_inclusion_rules_must_be_a_list(self):
        config = deepcopy(load_default_config())
        config["scan"]["inclusions"]["rules"] = "*.py"

        with self.assertRaises(TypeError):
            validate_config(config)

    def test_empty_rule_is_rejected(self):
        config = deepcopy(load_default_config())
        config["scan"]["exclusions"]["rules"] = [".git/", ""]

        with self.assertRaises(ValueError):
            validate_config(config)


if __name__ == "__main__":
    unittest.main()