import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from configurator import config, make_config
if not make_config("config.ini"):
    exit(1)

from utils import check_name_for_violations

class GenderDetectionTests(unittest.TestCase):
    def test_nickname_violations(self):
        test_nicknames__violations = ["Вика (посмотрu пр0филь)", "Мила (загляни в проф)", "Лина (жми на профuль)",
                      "Нина (👉 профuль)", "блядь", "сука", "бесплатные бляди здесь"]

        test_nicknames__clean = ["Никита", "Laslo", "brandy :] xD 555 TF"]

        for name in test_nicknames__violations:
            with self.subTest(name=name):
                self.assertEqual(check_name_for_violations(name), False,
                    f"Failed for option: {name}")

        for name in test_nicknames__clean:
            with self.subTest(name=name):
                self.assertEqual(check_name_for_violations(name), True,
                    f"Failed for option: {name}")
