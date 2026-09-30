"""Exercise the public models CLI against real subprocess protocol fixtures."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from of.model_discovery import discover  # noqa: E402
from unittest.mock import patch  # noqa: E402

FIXTURE = r'''
import json, os, signal, subprocess, sys, time
from pathlib import Path
root = Path(os.environ['FIXTURE_HOME'])
mode = os.environ.get('FIXTURE_MODE', 'ok')
name = Path(sys.argv[0]).name
(root / 'argv.json').write_text(json.dumps(sys.argv[1:]))
(root / 'pid').write_text(str(os.getpid()))
if mode == 'timeout':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(60)
if mode == 'descendant':
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    (root / 'descendant').write_text(str(child.pid))
if mode == 'fail':
    print('account@example.com token=secret', file=sys.stderr)
    print('account@example.com token=secret')
    sys.exit(7)
if name in ('grok', 'agent', 'cursor-agent', 'agy'):
    if mode == 'empty':
        print('No models available for this account.')
    elif name == 'agy':
        print('Available models:\nfuture-z\tFuture Z\nfuture-a\tFuture A\nTip: use --model <id>')
    elif name == 'grok':
        print('You are logged in with account@example.com.\nDefault model: tomorrow-z\nAvailable models:\n  * tomorrow-z (default)\n  - future-a')
    else:
        print('\x1b[2mAvailable models\x1b[0m\n\nfuture-z - Future Z (current, default)\nfuture-a - Future A\n\nTip: use --model <id>')
    sys.exit(0)
for line in sys.stdin:
    request = json.loads(line)
    with (root / 'requests.jsonl').open('a') as log:
        log.write(line)
    if mode == 'invalid':
        print('invalid', flush=True)
        continue
    if name == 'claude':
        response = {'models': [{'value':'default', 'resolvedModel':'future-claude-999',
                     'displayName':'Default (recommended)', 'description':'From provider',
                     'supportedEffortLevels':['low','ultra'], 'account':'secret'},
                    {'value':'future-claude-abc', 'resolvedModel':'future-claude-abc'}]}
        print(json.dumps({'type':'control_response','response': {'request_id':'models',
              'subtype': 'error' if mode == 'rpc-error' else 'success', 'response':response}}), flush=True)
        continue
    method = request.get('method')
    if method == 'initialized':
        continue
    if method == 'initialize':
        result = {'userAgent':'secret'}
    else:
        cursor = request['params']['cursor']
        data = [{'id':'future-z', 'model':'resolved-z', 'isDefault':True,
                 'upgrade':'future-upgrade', 'description':'Provider recommendation',
                 'supportedReasoningEfforts':[{'reasoningEffort':'ultra','description':'Deep'}]},
                {'id':'hidden-secret', 'hidden':True}] if cursor is None else [{'id':'future-a'}]
        result = {'data': [] if mode == 'empty' else data,
                  'nextCursor': 'page2' if cursor is None or mode == 'cycle' else None}
    reply = {'id':request['id'], 'result':result}
    if mode == 'rpc-error' and method == 'model/list':
        reply = {'id':request['id'], 'error':{'code':-32000,'message':'token=secret'}}
    print(json.dumps(reply), flush=True)
'''


class LiveModelDiscovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name in ('codex', 'claude', 'grok', 'agent', 'cursor-agent', 'agy'):
            file = self.root / name
            file.write_text(f'#!{sys.executable}\n' + FIXTURE)
            file.chmod(0o755)
        self.env = {**os.environ, 'PATH': str(self.root), 'FIXTURE_HOME': str(self.root),
                    'OF_NO_UPDATE_CHECK': '1'}

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, adapter='codex', mode='ok', timeout='6', global_json=False):
        args = ['--json', 'models'] if global_json else ['models', '--json']
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/of.py'), *args,
                                 '--adapter', adapter, '--timeout', timeout],
                                cwd=self.root, env={**self.env, 'FIXTURE_MODE':mode},
                                capture_output=True, text=True, timeout=12)
        report = json.loads(result.stdout)['adapters'][0]
        return result, report

    def requests(self):
        return [json.loads(line) for line in (self.root/'requests.jsonl').read_text().splitlines()]

    def assert_stopped(self, path='pid'):
        pid = int((self.root/path).read_text())
        for _ in range(30):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            # A reparented zombie is stopped, awaiting the host's reaper.
            state = subprocess.run(['/bin/ps','-o','stat=','-p',str(pid)], capture_output=True,text=True).stdout.strip()
            if state.startswith('Z') or not state:
                return
            time.sleep(.02)
        self.fail(f'fixture process {pid} still running')

    def test_codex_pagination_visible_metadata_no_routing(self):
        result, report = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = report['models']
        self.assertEqual([r['model_id'] for r in rows], ['future-z','future-a'])
        self.assertEqual(rows[0]['resolved_model'], 'resolved-z')
        self.assertTrue(rows[0]['is_default'])
        self.assertEqual(rows[0]['recommendation'], 'future-upgrade')
        self.assertEqual(rows[0]['efforts'], [{'effort':'ultra','description':'Deep'}])
        self.assertTrue(all(r['price_public']=='unknown' for r in rows))
        self.assertIsNone(rows[1]['is_default'])
        self.assertEqual([r['method'] for r in self.requests()],
                         ['initialize','initialized','model/list','model/list'])
        self.assertFalse(self.requests()[2]['params']['includeHidden'])
        self.assertEqual(self.requests()[3]['params']['cursor'], 'page2')
        self.assertFalse((self.root/'.orderfield').exists())
        self.assertNotIn('secret', result.stdout)
        self.assert_stopped()

    def test_claude_only_initialize_and_alias_resolution(self):
        result, report = self.run_cli('claude')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report['models'][0]['resolved_model'], 'future-claude-999')
        self.assertIsNone(report['models'][0]['is_default'])
        self.assertEqual(report['models'][0]['display_name'],'Default (recommended)')
        self.assertEqual(self.requests(), [{'type':'control_request','request_id':'models',
                                           'request':{'subtype':'initialize'}}])
        argv = json.loads((self.root/'argv.json').read_text())
        self.assertEqual(argv[argv.index('--tools')+1], '')
        self.assertIn('--strict-mcp-config', argv)
        self.assertEqual(argv[argv.index('--setting-sources')+1], '')
        self.assertNotIn('secret', result.stdout)
        self.assert_stopped()

    def test_list_commands_preserve_provider_order_and_default(self):
        for adapter in ('grok','cursor'):
            with self.subTest(adapter=adapter):
                result, report = self.run_cli(adapter)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(len(report['models']), 2)
                self.assertTrue(report['models'][0]['is_default'])
                self.assertNotIn('account@', result.stdout)
                self.assertEqual(json.loads((self.root/'argv.json').read_text()), ['models'])

    def test_protocol_errors_are_explicit_without_raw_provider_details(self):
        for adapter, mode, error in [('codex','rpc-error','model_list_failed'),
                                     ('claude','rpc-error','initialize_failed'),
                                     ('codex','invalid','invalid_json'),
                                     ('codex','cycle','invalid_pagination'),
                                     ('codex','empty','empty_models'),
                                     ('grok','fail','command_failed')]:
            with self.subTest(adapter=adapter, mode=mode):
                result, report = self.run_cli(adapter, mode)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(report['error'], error)
                self.assertEqual(report['models'], [])
                self.assertNotIn('secret', result.stdout + result.stderr)
                self.assert_stopped()

    def test_agy_tab_separated_models_without_default_guess(self):
        result, report = self.run_cli('agy')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report['source'], 'agy models')
        self.assertEqual([r['model_id'] for r in report['models']], ['future-z', 'future-a'])
        self.assertEqual(report['models'][0]['display_name'], 'Future Z')
        self.assertTrue(all(r['is_default'] is None for r in report['models']))
        self.assert_stopped()

    def test_timeout_kills_uncooperative_process_within_bound(self):
        start = time.monotonic()
        result, report = self.run_cli('codex','timeout','6')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report['error'], 'timeout')
        self.assertLess(time.monotonic()-start, 10)
        self.assert_stopped()

    @unittest.skipUnless(os.name=='posix', 'POSIX process group cleanup')
    def test_success_stops_descendant(self):
        result, report = self.run_cli('codex','descendant')
        self.assertEqual(result.returncode, 0)
        self.assert_stopped()
        self.assert_stopped('descendant')

    def test_missing_unsupported_and_global_json(self):
        (self.root/'codex').unlink()
        result, report = self.run_cli(global_json=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report['status'], 'missing')
        result, report = self.run_cli('opencode')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report['status'], 'unsupported')

    def test_all_inventory_and_live_every_call(self):
        with patch.dict(os.environ,self.env):
            a = discover('claude')
            b = discover('claude')
        self.assertNotEqual(a['checked_at'],b['checked_at'])
        self.assertEqual(len(self.requests()),2)
        result = subprocess.run([sys.executable,str(ROOT/'scripts/of.py'),'models','--json'],
                                env=self.env,cwd=self.root,capture_output=True,text=True,timeout=8)
        self.assertEqual(result.returncode,0)
        self.assertEqual(len(json.loads(result.stdout)['adapters']),9)

    def test_empty_list_is_not_a_static_fallback(self):
        result, report = self.run_cli('cursor', 'empty')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report['error'], 'empty_models')
        self.assertEqual(report['models'], [])

    def test_invalid_timeout_never_launches_a_probe(self):
        for value in ('0', '-1', 'nan', 'inf', '121'):
            with self.subTest(value=value):
                result = subprocess.run([sys.executable, str(ROOT/'scripts/of.py'),
                                         'models','--adapter','codex','--timeout',value],
                                        env=self.env,cwd=self.root,capture_output=True,text=True)
                self.assertEqual(result.returncode,1)
                self.assertFalse((self.root/'pid').exists())

    def test_cursor_fallback_binary(self):
        (self.root/'agent').unlink()
        result, report = self.run_cli('cursor')
        self.assertEqual(result.returncode,0)
        self.assertEqual(report['models'][0]['display_name'],'Future Z')
        self.assertEqual(report['models'][1]['display_name'],'Future A')
        self.assertFalse(report['models'][1]['is_default'])


if __name__ == '__main__':
    unittest.main()
