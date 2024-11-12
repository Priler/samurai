import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from configurator import config, make_config
if not make_config("config.ini"):
    exit(1)
import heroku_config

from utils import Gender
from lru_cache import detect_gender

class GenderDetectionTests(unittest.TestCase):
    def test_male(self):
        test_names = ["😎 Абрахам", "Алексей", "Тони", "Иннокентий", "Аркадий", "Виктор"]
        for name in test_names:
            with self.subTest(name=name):
                self.assertEqual(detect_gender(name), Gender.MALE,
                    f"Failed for name: {name}")

    def test_female(self):
        test_names = ["👧 Александра", "Катя", "Ксения", "Ксюша", "Антонина", "Настя", "👧👧Лиза👧👧", "Ника", "Лея"]
        for name in test_names:
            with self.subTest(name=name):
                self.assertEqual(detect_gender(name), Gender.FEMALE,
                    f"Failed for name: {name}")

    def test_unknown(self):
        test_names = ["Almaz", "Kamaz", "💎 Алмаз 💎", "Дивергент", "Лейндаль", "Унга Бунга 🌺"]
        for name in test_names:
            with self.subTest(name=name):
                self.assertEqual(detect_gender(name), Gender.UNKNOWN,
                    f"Failed for name: {name}")