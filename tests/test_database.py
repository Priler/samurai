import subprocess
import sys
import unittest
from pathlib import Path


class DatabaseStartupTests(unittest.TestCase):
    def test_sqlite_import_without_mysql_driver(self):
        script = """
import builtins
import sys
from types import ModuleType, SimpleNamespace

config_module = ModuleType('config')
config_module.config = SimpleNamespace(db=SimpleNamespace(url='sqlite+aiosqlite:///:memory:'))
sys.modules['config'] = config_module
original_import = builtins.__import__

def without_mysql(name, *args, **kwargs):
    if name == 'pymysql' or name.startswith('pymysql.'):
        raise ModuleNotFoundError('MySQL driver deliberately unavailable')
    return original_import(name, *args, **kwargs)

builtins.__import__ = without_mysql
from db.database import _is_transient_db_error
assert _is_transient_db_error(OSError('connection lost'))
assert not _is_transient_db_error(ValueError('invalid query'))
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
