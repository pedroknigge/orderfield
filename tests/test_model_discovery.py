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
argv_line = json.dumps(sys.argv[1:])
(root / 'argv.json').write_text(argv_line)
with (root / 'argv.jsonl').open('a') as log:
    log.write(argv_line + '\n')
(root / 'pid').write_text(str(os.getpid()))
if '--version' in sys.argv or sys.argv[1:] == ['-v']:
    print(os.environ.get('FAKE_VERSION', '0.0.0'))
    sys.exit(0)
if name == 'orca':
    if os.environ.get('ORCA_FAIL') == '1':
        sys.exit(7)
    path = root / 'orca.json'
    print(path.read_text() if path.exists() else '{"ok":false}')
    sys.exit(0)
if '/usage' in sys.argv or (name == 'claude' and '-p' in sys.argv and '--input-format' not in sys.argv):
    (root / 'usage_calls').write_text(name)
    if os.environ.get('USAGE_FAIL') == '1':
        sys.exit(7)
    path = root / 'usage_stdout.txt'
    sys.stdout.write(path.read_text() if path.exists() else '')
    sys.exit(0)
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
    if method == 'account/rateLimits/read':
        (root / 'usage_calls').write_text('codex')
        path = root / 'codex_limits.json'
        result = json.loads(path.read_text()) if path.exists() else {}
        print(json.dumps({'id': request['id'], 'result': result}), flush=True)
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

    def run_cli(self, adapter='codex', mode='ok', timeout='6', global_json=False, proc_timeout=12):
        args = ['--json', 'models'] if global_json else ['models', '--json']
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/of.py'), *args,
                                 '--adapter', adapter, '--timeout', timeout],
                                cwd=self.root, env={**self.env, 'FIXTURE_MODE':mode},
                                capture_output=True, text=True, timeout=proc_timeout)
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
        methods = [r.get('method') for r in self.requests()]
        self.assertEqual(methods[:4], ['initialize','initialized','model/list','model/list'])
        self.assertEqual(methods[4:], ['initialize','initialized','account/rateLimits/read'])
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
        argv = json.loads((self.root/'argv.jsonl').read_text().splitlines()[0])
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
                argvs = [json.loads(line) for line in (self.root/'argv.jsonl').read_text().splitlines()]
                self.assertEqual(argvs[0], ['models'])
                self.assertEqual(argvs[-1], ['-p', '/usage'])

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
        result, report = self.run_cli('codex','timeout','6', proc_timeout=20)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report['error'], 'timeout')
        # Model list and the usage probe each die inside the same bound.
        self.assertLess(time.monotonic()-start, 16)
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
                                env=self.env,cwd=self.root,capture_output=True,text=True,timeout=20)
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


class UsageHeadroom(unittest.TestCase):
    """Orca-first headroom. sin dato never fails the model command."""

    setUp = LiveModelDiscovery.setUp
    tearDown = LiveModelDiscovery.tearDown
    run_cli = LiveModelDiscovery.run_cli

    def test_parser_smallest_window_and_roster_tie_break(self):
        from of.model_discovery import roster
        from of_adapters import orca_rate_limits, parse_usage

        parsed = parse_usage(json.dumps({
            "rateLimits": {
                "primary": {"usedPercent": 0, "windowDurationMins": 10080, "resetsAt": 2000000000000},
                "secondary": {"usedPercent": 40, "windowDurationMins": 300, "resetsAt": 1900000000000},
            }
        }))
        self.assertEqual(parsed[0], 40.0)
        claude = parse_usage("\n".join([
            json.dumps({"type": "rate_limit_event", "rate_limit_info": {
                "rateLimitType": "seven_day", "utilization": 0.5, "resetsAt": 2000000000}}),
            json.dumps({"type": "rate_limit_event", "rate_limit_info": {
                "rateLimitType": "five_hour", "utilization": 0.25, "resetsAt": 1900000000}}),
        ]))
        self.assertEqual(claude[0], 25.0)
        partial = parse_usage(json.dumps({
            "rate_limit_info": {"rateLimitType": "five_hour", "resetsAt": 1900000000}}))
        self.assertIsNone(partial[0])
        self.assertIsNotNone(partial[1])
        self.assertIsNone(parse_usage("not-json"))
        self.assertIsNone(orca_rate_limits({"ok": True, "email": "account@example.com"}))
        self.assertEqual(roster([
            {"harness": "grok", "used_percent": 10.0, "resets_at": "2027-01-01T00:00:00Z"},
            {"harness": "codex", "used_percent": 10.0, "resets_at": "2026-01-01T00:00:00Z"},
            {"harness": "agy", "used_percent": 5.0, "resets_at": "2026-06-01T00:00:00Z"},
            {"harness": "cursor", "used_percent": "sin dato", "resets_at": "sin dato"},
        ]), ["agy", "codex", "grok"])

    def _install(self, name):
        file = self.root / name
        file.write_text(f'#!{sys.executable}\n' + FIXTURE)
        file.chmod(0o755)

    def test_orca_short_circuit_uses_smallest_window(self):
        self._install('orca')
        (self.root / 'orca.json').write_text(json.dumps({
            "ok": True, "email": "account@example.com", "token": "secret",
            "result": {"rateLimits": {
                "claude": {
                    "session": {"usedPercent": 80, "windowMinutes": 300, "resetsAt": 1800000000000},
                    "weekly": {"usedPercent": 10, "windowMinutes": 10080, "resetsAt": 1900000000000},
                },
                "codex": {"weekly": {"usedPercent": 10, "windowMinutes": 10080, "resetsAt": 1700000000000}},
                "grok": {"weekly": {"usedPercent": 10, "windowMinutes": 10080, "resetsAt": 2000000000000}},
                "cursor": None,
                "antigravity": {"session": {"usedPercent": 5, "windowMinutes": 300, "resetsAt": 1800000000000}},
            }},
        }))
        result = subprocess.run(
            [sys.executable, str(ROOT / 'scripts/of.py'), 'models', '--json', '--timeout', '6'],
            cwd=self.root, env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        body = json.loads(result.stdout)
        rows = {row['harness']: row for row in body['headroom']}
        self.assertEqual(list(rows), ['claude', 'codex', 'cursor', 'grok', 'agy'])
        self.assertEqual(rows['claude']['used_percent'], 80.0)
        self.assertEqual(rows['claude']['source'], 'orca')
        self.assertEqual(rows['agy']['used_percent'], 5.0)
        self.assertEqual(rows['cursor']['used_percent'], 'sin dato')
        self.assertEqual(rows['cursor']['source'], 'orca')
        self.assertEqual(body['roster'], ['agy', 'codex', 'grok', 'claude'])
        self.assertNotIn('secret', result.stdout)
        self.assertNotIn('account@', result.stdout)
        self.assertFalse((self.root / 'usage_calls').exists())
        requests = (self.root / 'requests.jsonl').read_text()
        self.assertNotIn('account/rateLimits/read', requests)

    def test_missing_rate_limits_fall_through_to_native_codex(self):
        self._install('orca')
        (self.root / 'orca.json').write_text('{"ok":true,"email":"account@example.com"}')
        (self.root / 'codex_limits.json').write_text(json.dumps({"rateLimits": {
            "primary": {"usedPercent": 0, "windowDurationMins": 10080, "resetsAt": 2000000000000},
            "secondary": {"usedPercent": 40, "windowDurationMins": 300, "resetsAt": 1900000000000},
        }}))
        result, _report = self.run_cli('codex')
        body = json.loads(result.stdout)
        row = body['headroom'][0]
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(row['harness'], 'codex')
        self.assertEqual(row['used_percent'], 40.0)
        self.assertEqual(row['source'], 'native')
        self.assertEqual((self.root / 'usage_calls').read_text(), 'codex')
        self.assertNotIn('account@', result.stdout)

    def test_missing_harness_is_sin_dato_and_exit_zero(self):
        empty = self.root / 'bin'
        empty.mkdir()
        result = subprocess.run(
            [sys.executable, str(ROOT / 'scripts/of.py'), 'models', '--json', '--timeout', '6'],
            cwd=self.root, env={**self.env, 'PATH': str(empty)},
            capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        body = json.loads(result.stdout)
        self.assertEqual([row['harness'] for row in body['headroom']],
                         ['claude', 'codex', 'cursor', 'grok', 'agy'])
        self.assertTrue(all(row['used_percent'] == 'sin dato' and row['source'] == 'none'
                            and row['resets_at'] == 'sin dato' for row in body['headroom']))
        self.assertEqual(body['roster'], [])

    def test_agy_usage_is_version_gated(self):
        payload = json.dumps({"usedPercent": 12, "windowMinutes": 300, "resetsAt": 1900000000})
        (self.root / 'usage_stdout.txt').write_text(payload)
        for version, called in (('1.1.10', False), ('1.1.11', True), ('unknown', False)):
            with self.subTest(version=version):
                marker = self.root / 'usage_calls'
                if marker.exists():
                    marker.unlink()
                result = subprocess.run(
                    [sys.executable, str(ROOT / 'scripts/of.py'), 'models', '--json',
                     '--adapter', 'agy', '--timeout', '6'],
                    cwd=self.root, env={**self.env, 'FAKE_VERSION': version},
                    capture_output=True, text=True, timeout=12)
                self.assertEqual(result.returncode, 0, result.stderr)
                row = json.loads(result.stdout)['headroom'][0]
                self.assertEqual(marker.exists(), called)
                if called:
                    self.assertEqual(row['used_percent'], 12.0)
                    self.assertEqual(row['source'], 'native')
                    self.assertEqual(marker.read_text(), 'agy')
                else:
                    self.assertEqual(row['used_percent'], 'sin dato')
                    self.assertEqual(row['source'], 'none')

    def test_claude_stream_event_and_usage_failure_does_not_fail(self):
        (self.root / 'usage_stdout.txt').write_text("\n".join([
            json.dumps({"type": "rate_limit_event", "rate_limit_info": {
                "rateLimitType": "seven_day", "utilization": 0.5, "resetsAt": 2000000000}}),
            json.dumps({"type": "rate_limit_event", "rate_limit_info": {
                "rateLimitType": "five_hour", "utilization": 0.25, "resetsAt": 1900000000}}),
        ]))
        result, report = self.run_cli('claude')
        self.assertEqual(result.returncode, 0, result.stderr)
        row = json.loads(result.stdout)['headroom'][0]
        self.assertEqual(row['used_percent'], 25.0)
        self.assertEqual(row['source'], 'native')
        self.assertEqual(report['status'], 'ok')
        self.assertNotIn('secret', result.stdout)
        failed = subprocess.run(
            [sys.executable, str(ROOT / 'scripts/of.py'), 'models', '--json',
             '--adapter', 'grok', '--timeout', '6'],
            cwd=self.root, env={**self.env, 'USAGE_FAIL': '1'},
            capture_output=True, text=True, timeout=12)
        self.assertEqual(failed.returncode, 0, failed.stderr)
        grow = json.loads(failed.stdout)
        self.assertEqual(grow['adapters'][0]['status'], 'ok')
        self.assertEqual(grow['headroom'][0]['source'], 'none')
        self.assertEqual(grow['headroom'][0]['used_percent'], 'sin dato')

    def test_doctor_points_at_headroom_without_probing(self):
        empty = self.root / 'bin'
        empty.mkdir()
        result = subprocess.run(
            [sys.executable, str(ROOT / 'scripts/of.py'), 'doctor'],
            cwd=self.root, env={**self.env, 'PATH': str(empty), 'HOME': str(self.root)},
            capture_output=True, text=True, timeout=20)
        self.assertIn('headroom', result.stdout)
        self.assertIn('sin dato', result.stdout)
        self.assertIn('of models --json', result.stdout)
        self.assertFalse((self.root / 'usage_calls').exists())
        self.assertFalse((self.root / 'pid').exists())


if __name__ == '__main__':
    unittest.main()
