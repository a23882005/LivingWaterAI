"""Family W8 05/08/09/14 real menu wiring; synthetic sources, no web I/O."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import importlib.util
import unittest

ROOT=Path(__file__).resolve().parents[1]
FAMILY=ROOT.parent

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

P=load(ROOT/"on_demand_public.py","w8_test_public")
MENU=load(FAMILY/"W7"/"family_menu.py","w8_test_public_menu")

class Login:
    user_id="JO"
    def require_login(self):return self.user_id
    def logout(self):return {"status":"LOGGED_OUT"}
    def login(self,user,password):return {"status":"LOGIN_OK"}

class Entry:
    def current_snapshot(self):
        return {"tables":{
            "portfolio_instrument":[{"instrument_key":"V","ticker":"VT"}],
            "portfolio_position":[
                {"account_key":"IB","instrument_key":"V",
                 "quantity_decimal":"2","as_of_utc":"2026-10-27T00:00:00Z"}]}}

class PublicHandlersTests(unittest.TestCase):
    def setUp(self):
        self.auth=Login()
        self.entry=Entry()
        self.handlers=P.public_handlers(self.entry,self.auth)

    def test_four_handlers_connected(self):
        self.assertEqual(set(self.handlers),{"research_candidates","market_news",
                                             "holding_news","account"})

    def test_market_news_invokes_chatgpt_tool(self):
        r=self.handlers["market_news"]({})
        self.assertEqual(r["status"],"TOOL_FETCH_REQUIRED")
        self.assertEqual(r["max_items"],10)
        self.assertEqual(r["trade_authorization"],"NONE")

    def test_holding_news_only_uses_latest_owned_tickers(self):
        r=self.handlers["holding_news"]({})
        self.assertEqual(r["status"],"TOOL_FETCH_REQUIRED")
        self.assertEqual([q["ticker"] for q in r["ticker_queries"]],["VT"])
        with self.assertRaisesRegex(ValueError,"TICKER_NOT_IN_CURRENT_HOLDINGS"):
            self.handlers["holding_news"]({"ticker":"NVDA"})

    def test_research_requires_criteria_without_fabricating(self):
        a=self.handlers["research_candidates"]({})
        self.assertEqual(a["status"],"NEEDS_CRITERIA")
        b=self.handlers["research_candidates"]({"theme":"全球型ETF",
                                                "tickers":["VT","QQQ"]})
        self.assertEqual(b["status"],"TOOL_FETCH_REQUIRED")
        self.assertEqual(len(b["source_queries"]),3)

    def test_research_rejects_private_file_override(self):
        with self.assertRaisesRegex(ValueError,"INVALID_RESEARCH_PAYLOAD"):
            self.handlers["research_candidates"]({"db_path":"/tmp/other.db"})

    def test_real_source_evidence_is_retained_not_promoted_to_buy(self):
        now=datetime.now(timezone.utc).isoformat()
        def evidence(operation,query,max_items):
            return [{"title":"Unit-test evidence","url":"https://example.com/verified",
                     "published_at_utc":now,"source":"Synthetic Unit Test"}]
        h=P.public_handlers(self.entry,self.auth,trusted_public_fetcher=evidence)
        r=h["research_candidates"]({"tickers":["VT"]})
        self.assertEqual(r["status"],"RESEARCH_EVIDENCE")
        self.assertTrue(r["candidate_instruments"][0]["held_in_current_portfolio"])
        self.assertEqual(r["buy_recommendation"],"NOT_EVALUATED")
        self.assertEqual(r["candidate_instruments"][0]["v82_decision"],"NOT_EVALUATED")
        self.assertEqual(h["market_news"]({})["status"],"OK")

    def test_unverified_old_articles_fail_closed(self):
        stale=(datetime.now(timezone.utc)-timedelta(days=8)).isoformat()
        def bad(operation,query,max_items):
            return [{"title":"Old news","url":"https://example.com/stale",
                     "published_at_utc":stale,"source":"Test"}]
        h=P.public_handlers(self.entry,self.auth,trusted_public_fetcher=bad)
        with self.assertRaisesRegex(ValueError,"STALE_OR_FUTURE_NEWS_ITEM"):
            h["market_news"]({})

    def test_account_options_change_staged_no_false_success(self):
        r=self.handlers["account"]({})
        self.assertEqual(r["status"],"ACCOUNT_OPTIONS")
        result=self.handlers["account"]({"action":"change_password",
                                          "current_password":"old",
                                          "new_password":"new"})
        self.assertEqual(result["status"],"ACCOUNT_CHANGE_WRITEBACK_REQUIRED")
        self.assertNotIn("old",str(result))
        self.assertNotIn("new",str(result))
        menu=MENU.FamilyMenu(self.auth,project_name="Joseph",login_account="JO",
                             handlers=self.handlers)
        self.assertEqual(menu.select(14,payload={"action":"change_password",
                        "current_password":"old","new_password":"new"})["status"],
                         "ACCOUNT_CHANGE_WRITEBACK_REQUIRED")
        self.assertEqual(menu.select(14,payload={"action":"logout"})["status"],
                         "COMPLETED")

    def test_w7_menu_does_not_mark_missing_public_data_done(self):
        menu=MENU.FamilyMenu(self.auth,project_name="Joseph",login_account="JO",
                             handlers=self.handlers)
        self.assertEqual(menu.select(8)["status"],"TOOL_FETCH_REQUIRED")
        self.assertEqual(menu.select(9)["status"],"TOOL_FETCH_REQUIRED")
        self.assertEqual(menu.select(5)["status"],"NEEDS_CRITERIA")

if __name__=="__main__":
    unittest.main()
