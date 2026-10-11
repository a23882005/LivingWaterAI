from decimal import Decimal
import pytest
from v75_runtime.work4_models import *
def test_static_profile_contract():
 x=Work4StaticRiskProfile(asset_id='SGOV',asset_credit_class='TREASURY',effective_duration_years=Decimal('.1'),source_lineage=['official'])
 assert x.asset_id=='SGOV'
 with pytest.raises(Exception): Work4StaticRiskProfile(asset_id='X',asset_credit_class='TREASURY',effective_duration_years=-1,source_lineage=['x'])
def test_optional_policy_null_is_legal():
 x=ExistingPositionPolicyInput(current_position_quantity=1); assert x.capital_gain_harvest_eligible is None
