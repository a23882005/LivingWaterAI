"""Dependency-free runner for unittest cases plus plain zero-argument probe tests."""
from pathlib import Path
import runpy
import unittest
root=Path(__file__).resolve().parent
result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover(str(root/'tests')))
if not result.wasSuccessful():raise SystemExit(1)
namespace=runpy.run_path(str(root/'tests/test_github_json_outbox.py'))
count=0
for name,fn in namespace.items():
    if name.startswith('test_') and callable(fn):fn();count+=1
print('PASS: unittest='+str(result.testsRun)+' public-state-tests='+str(count))
