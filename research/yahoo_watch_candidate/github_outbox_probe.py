"""GitHub-only synthetic probe. Never sends SMTP, reads holdings or credentials files.
Only the explicitly named synthetic JSON file is mutated. Prints counts/status only.
"""
import concurrent.futures
import os
import threading
from github_json_outbox import GithubContentsBackend, GithubJsonOutbox, deliver_once, event_key

PATH='research/yahoo_watch_candidate/state/probe.json'

def main():
    branch=os.environ['GITHUB_HEAD_REF'] if os.environ.get('GITHUB_HEAD_REF') else os.environ['GITHUB_REF_NAME']
    backend=GithubContentsBackend(token=os.environ['GITHUB_TOKEN'],repository=os.environ['GITHUB_REPOSITORY'],branch=branch,path=PATH)
    # Run + attempt distinguishes probes, but only its SHA256 is persisted.
    prefix='synthetic:'+os.environ['GITHUB_RUN_ID']+':'+os.environ['GITHUB_RUN_ATTEMPT']
    barrier=threading.Barrier(2)
    local=threading.local()
    class Race:
        def read(self):
            result=backend.read()
            if not getattr(local,'read_once',False):
                local.read_once=True
                barrier.wait(timeout=30)
            return result
        def compare_and_swap(self,sha,doc): backend.compare_and_swap(sha,doc)
    lock=threading.Lock(); calls=[]
    def fake_send():
        with lock: calls.append('SIMULATED_ONLY')
    key=event_key(prefix+':race')
    def run(): return deliver_once(GithubJsonOutbox(Race()),key,fake_send)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:run(),range(2)))
    assert calls==['SIMULATED_ONLY'], 'SYNTHETIC_SEND_COUNT_FAILED'
    assert sorted(results)==sorted(['SENT_SMTP_ACCEPTED','STATE_UNKNOWN_NO_SEND']), 'CAS_RACE_FAILED'
    assert deliver_once(GithubJsonOutbox(backend),key,fake_send)=='ALREADY_SENT', 'RESTART_DEDUP_FAILED'
    class Uncertain:
        def read(self): return backend.read()
        def compare_and_swap(self,sha,doc):
            backend.compare_and_swap(sha,doc)
            raise TimeoutError('synthetic-after-write')
    key2=event_key(prefix+':uncertain')
    assert deliver_once(GithubJsonOutbox(Uncertain()),key2,fake_send)=='STATE_UNKNOWN_NO_SEND'
    assert deliver_once(GithubJsonOutbox(backend),key2,fake_send)=='DELIVERY_UNKNOWN_RECONCILE_REQUIRED'
    assert calls==['SIMULATED_ONLY']
    print('PASS: remote CAS race, readback, restart dedup, uncertain write; real emails=0')

if __name__=='__main__': main()
