"""Synthetic permission and accounting scenarios."""
import copy
import os
import subprocess
import sys
from pathlib import Path
import unittest
import test_upload_plan as fixtures
import upload_plan as u
from operation_report import summarize, markdown


class ConfirmationReport(unittest.TestCase):
    setUp = fixtures.Planning.setUp
    row = fixtures.Planning.row
    snap = fixtures.Planning.snap
    file = fixtures.Planning.file
    plan = fixtures.Planning.plan
    verified = fixtures.Planning.verified
    def auth(self, p, **kwargs):
        return dict(action='complete-upload', runId=p['runId'], context=p['context'],
                    source='post-upload-confirmation', userStatement='确认点击完成上传', evidenceRef='human:1', **kwargs)

    def test_old_boolean_is_not_authorization(self):
        p = self.plan([dict(path=self.file())], [self.row()], mode='change', completeRequested=True)
        ev = self.verified(p)
        u.record(self.root, p['runId'], ev)
        self.assertFalse(u.check_submission(self.root, p['runId'], ev['snapshot'])['ready'])
        with self.assertRaises(ValueError):
            u.finalize(self.root, p['runId'], dict(snapshot=ev['snapshot'], accepted=True, evidenceRef='x', serverState='x'))
        u.authorize(self.root, p['runId'], self.auth(p))
        self.assertTrue(u.check_submission(self.root, p['runId'], ev['snapshot'])['ready'])

    def test_authorization_scope_and_partial_limits(self):
        p = self.plan([], taskLimit='partial')
        with self.assertRaises(ValueError):
            u.authorize(self.root, p['runId'], self.auth(p))
        p = self.plan([])
        a = self.auth(p)
        a['context'] = dict(p['context'], profession='给排水')
        with self.assertRaises(ValueError):
            u.authorize(self.root, p['runId'], a)
        a = self.auth(p)
        a['userStatement'] = ''
        with self.assertRaises(ValueError):
            u.authorize(self.root, p['runId'], a)

    def test_authorization_never_overrides_blockers_or_snapshot(self):
        p = self.plan([dict(path=self.file())], [self.row()], mode='change')
        u.authorize(self.root, p['runId'], self.auth(p))
        self.assertFalse(u.check_submission(self.root, p['runId'], self.snap([self.row()]))['ready'])
        ev = self.verified(p)
        u.record(self.root, p['runId'], ev)
        bad = copy.deepcopy(ev['snapshot'])
        bad['complete'] = False
        self.assertFalse(u.check_submission(self.root, p['runId'], bad)['ready'])
        bad['complete'] = True
        bad['context']['profession'] = '结构'
        self.assertFalse(u.check_submission(self.root, p['runId'], bad)['ready'])

    def test_report_multi_profession_conservation_reuse_materials(self):
        p = self.plan([dict(path=self.file())], [self.row()], mode='change')
        u.record(self.root, p['runId'], self.verified(p))
        p = u.read(u.run_path(self.root, p['runId']))
        q = copy.deepcopy(p)
        q['runId'] = 'a' * 32
        q['context']['profession'] = '给排水'
        q['items'][0]['action'] = 'add'
        for kind, action in [('drawing', 'update'), ('directory', 'update'), ('cancellation', 'cancel'), ('cancellation', 'cancel')]:
            i = copy.deepcopy(q['items'][0])
            i['kind'], i['action'] = kind, action
            if kind == 'drawing':
                i['reusedFrom'] = {'runId': p['runId']}
            q['items'].append(i)
        r = summarize([p, q])
        s = r['operationSummary']
        self.assertEqual((s['drawings'], s['updated'], s['added'], s['reusedDrawings']), (2, 1, 1, 1))
        self.assertEqual((s['directoryTargets'], s['cancellationTargets'], s['cancellationFiles']), (1, 2, 1))
        self.assertEqual(sum(x['drawings'] for x in r['byProfession'].values()), s['drawings'])
        self.assertEqual(sum(r['statusCounts'].values()), len(r['details']))
        text = markdown(r)
        self.assertIn('成功上传 2 张', text)
        self.assertIn('给排水专业 1 张', text)
        self.assertIn('尚待用户确认', text)
        self.assertIn('目录未更新', text)
        self.assertIn(p['items'][0]['path'], text)
        p['authorization'] = {'action': 'complete-upload'}
        self.assertIn('尚待用户确认', markdown(summarize([p])))
        with self.assertRaises(ValueError):
            summarize([p, p])
        q['context']['profession'] = '建筑'
        with self.assertRaises(ValueError):
            summarize([p, q])

    def test_report_unknown_not_success_and_materials_separate(self):
        p = self.plan([dict(path=self.file())], [self.row()], mode='change')
        p['items'][0]['status'] = 'unknown'
        r = u.report(p)
        self.assertEqual(r['operationSummary']['drawings'], 0)
        self.assertEqual(r['statusCounts'], {'unknown': 1})
        self.assertIn('提交条件受阻', markdown(r))

    def test_recovered_and_legacy_receipts_not_counted_as_new(self):
        p = self.plan([dict(path=self.file())], [self.row()], mode='change')
        ev = self.verified(p)
        ev['items'][0]['executionSource'] = 'recovered'
        r = u.record(self.root, p['runId'], ev)
        self.assertEqual(r['operationSummary']['drawings'], 0)
        self.assertEqual(r['operationSummary']['reusedDrawings'], 1)
        saved = u.read(u.run_path(self.root, p['runId']))
        del saved['items'][0]['result']['executionSource']
        self.assertEqual(u.report(saved)['operationSummary']['legacyVerifiedTargets'], 1)
        self.assertEqual(u.report(saved)['operationSummary']['drawings'], 0)

    def test_null_authorization_invalid_limit_and_failure_reason(self):
        with self.assertRaises(ValueError):
            self.plan([], taskLimit='typo')
        p = self.plan([dict(path=self.file())])
        for key in ('userStatement', 'evidenceRef'):
            a = self.auth(p)
            a[key] = None
            with self.assertRaises(ValueError):
                u.authorize(self.root, p['runId'], a)
        p['items'][0].update(status='failed', result={'reason': '服务器拒绝材料'})
        self.assertIn('服务器拒绝材料', markdown(u.report(p)))

    def test_cli_check_denied_exit_and_markdown_report(self):
        p = self.plan([])
        snap = self.base / 'snapshot.json'
        u.write(snap, self.snap())
        command = [sys.executable, str(Path(u.__file__)), '--project', str(self.root)]
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        denied = subprocess.run(command + ['check-submit', p['runId'], str(snap)], capture_output=True, env=env)
        self.assertEqual(denied.returncode, 2)
        self.assertIn('尚待用户', denied.stdout.decode('utf-8'))
        result = subprocess.run(command + ['report', p['runId'], '--format', 'markdown'], capture_output=True, env=env)
        self.assertEqual(result.returncode, 0)
        self.assertIn('成功上传 0 张', result.stdout.decode('utf-8'))
