"""A collected numerical oracle must not change another financial producer."""
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.parametrize('precision,rounding',[(28,'ROUND_DOWN'),(17,'ROUND_CEILING')])
def test_numeric_oracle_import_and_execution_restore_the_callers_decimal_context(precision,rounding):
    folder=Path(__file__).resolve().parent
    script='''
from decimal import getcontext
import decimal,importlib.util,sys,unittest
from pathlib import Path
folder=Path(sys.argv[1]);sys.path[:0]=[str(folder.parent),str(folder.parent.parent/'W5')]
ctx=getcontext();ctx.prec=int(sys.argv[2]);ctx.rounding=getattr(decimal,sys.argv[3])
ctx.flags[decimal.Inexact]=True
before=repr(ctx)
spec=importlib.util.spec_from_file_location('isolated_numeric_oracle',folder/'test_approved_v04_numeric.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
assert repr(getcontext())==before, 'oracle import changed caller arithmetic'
result=unittest.TestResult();unittest.defaultTestLoader.loadTestsFromTestCase(module.NumericSpecTests).run(result)
assert result.wasSuccessful(),(result.errors,result.failures)
assert repr(getcontext())==before, 'oracle execution changed caller arithmetic'
'''
    result=subprocess.run([sys.executable,'-c',script,str(folder),str(precision),rounding],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
