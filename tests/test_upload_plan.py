"""Synthetic opaque files only; no production system calls."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import upload_plan as u


class Planning(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'ledger'
        self.context = dict(site='http://example.test', WID='w1', OrgId='o1', unit='1号楼', profession='建筑')

    def row(self, bpid='b1', code='A-1', name='平面图', bgid='', versions=None):
        return dict(BPID=bpid, code=code, fullName=name, BGID=bgid, versions=versions or [])

    def snap(self, rows=(), complete=True):
        return dict(context=copy.deepcopy(self.context), rows=copy.deepcopy(list(rows)), complete=complete)

    def file(self, name='A-1_平面图.pack', content=b'opaque; intentionally not a PACK archive'):
        path = self.base / name
        path.write_bytes(content)
        return str(path)

    def plan(self, files, rows=(), mode='initial', **kw):
        request = dict(mode=mode, expectedStatus='竣工' if mode == 'completion' else '变更', files=files, **kw)
        return u.make_plan(self.root, self.snap(rows), request)

    def verified(self, p, bpid='b1', vsid='v2'):
        i = p['items'][0]
        row = self.row(bpid, i['uploadCode'], i['name'], versions=[dict(VSID=vsid, status=p['expectedStatus'])])
        snap = self.snap([row])
        result = dict(itemId=i['itemId'], state='verified', BPID=bpid, VSID=vsid,
                      fileSha256=i['sha256'], processing='success', evidenceRef='synthetic-response')
        return dict(snapshot=snap, items=[result])

    def test_dot_rename_opaque_content_and_reusable_mapping(self):
        original = self.file('A.1_平面图.pack')
        p = self.plan([dict(path=original)])
        self.assertEqual(p['items'][0]['uploadName'], 'A-1_平面图.pack')
        before = u.digest(original)
        u.rename(self.root, p['runId'])
        self.assertFalse(Path(original).exists())
        self.assertEqual(before, u.digest(self.base / 'A-1_平面图.pack'))
        u.record(self.root, p['runId'], self.verified(p))
        self.file('A.1_平面图.pack', b'a different version')
        q = self.plan([dict(path=original)], [self.row()], mode='change')
        self.assertEqual(q['items'][0]['BPID'], 'b1')
        self.assertEqual(q['items'][0]['uploadCode'], 'A-1')

    def test_dot_existing_keeps_code_and_path_b(self):
        p = self.plan([dict(path=self.file('A.1_平面图.pack'))], [self.row(code='A.1')], mode='change')
        self.assertEqual(p['items'][0]['route'], 'B')

    def test_new_pdf_and_gdb_use_add_existing_pdf_uses_target(self):
        for extension in ('.pdf', '.gdb'):
            p = self.plan([dict(path=self.file('A-1_平面图' + extension))])
            self.assertEqual(p['items'][0]['action'], 'add')
            self.assertEqual(p['items'][0]['route'], 'native-add')
        q = self.plan([dict(path=self.file('A-1_平面图.pdf'))], [self.row()], mode='change')
        self.assertEqual(q['items'][0]['route'], 'native-target')

    def test_collision_normalized_and_after_dot_conversion(self):
        for names in [('A.1_平面图.pack', 'A-1_立面图.pack'), ('Ａ-1_平面图.pack', 'a-1_立面图.pack')]:
            p = self.plan([dict(path=self.file(n)) for n in names])
            self.assertEqual([i['status'] for i in p['items']], ['blocked', 'blocked'])

    def test_ambiguous_name_and_unmatched_never_add_implicitly(self):
        rows = [self.row(), self.row('b2', 'A-2')]
        p = self.plan([dict(path=self.file('X_平面图.pack'))], rows, mode='change')
        self.assertEqual(p['items'][0]['status'], 'blocked')
        q = self.plan([dict(path=self.file('X_未知图.pack'))], rows, mode='change')
        self.assertEqual(q['items'][0]['status'], 'blocked')

    def test_mismatched_title_needs_confirmation(self):
        f = self.file('A-1_不同图名.pack')
        p = self.plan([dict(path=f)], [self.row()], mode='change')
        self.assertEqual(p['items'][0]['status'], 'blocked')
        q = self.plan([dict(path=f, matchConfirmed=True)], [self.row()], mode='change')
        self.assertEqual(q['items'][0]['status'], 'planned')

    def test_add_cancel_require_directory_and_notice(self):
        add = dict(path=self.file('A-2_立面图.pack'), action='add')
        cancel = dict(path=self.file('取消单.pdf'), action='cancel', kind='cancellation', BPID='b1', code='A-1', name='平面图')
        rows = [self.row(), self.row('dir', 'M-1', '目录')]
        p = self.plan([add, cancel], rows, mode='change')
        self.assertEqual(len(p['blockers']), 2)
        directory = dict(path=self.file('M-1_目录.pack'), kind='directory', directoryFor=['A-2', 'b1'])
        q = self.plan([add, cancel, directory], rows, mode='change')
        self.assertEqual(q['blockers'], [])
        bad = dict(cancel, kind='drawing')
        self.assertEqual(self.plan([bad], rows, mode='change')['items'][0]['status'], 'blocked')

    def test_shared_cancellation_not_renamed(self):
        path = self.file('取消变更单.pdf')
        rows = [self.row(), self.row('b2', 'A-2', '立面图')]
        files = [dict(path=path, action='cancel', kind='cancellation', BPID=r['BPID'], code=r['code'], name=r['fullName']) for r in rows]
        p = self.plan(files, rows, mode='change')
        self.assertEqual(u.rename(self.root, p['runId'])['renamed'], 0)
        self.assertTrue(Path(path).exists())

    def test_completion_selected_without_change_version_still_required(self):
        r = self.row(bgid='selected')
        self.assertEqual(len(self.plan([], [r], mode='completion')['blockers']), 1)
        r['versions'] = [dict(VSID='v1', status='竣工')]
        self.assertFalse(self.plan([], [r], mode='completion')['blockers'])
        del r['BGID']
        self.assertTrue(self.plan([], [r], mode='completion')['blockers'])

    def test_brownfield_missing_rows_not_deleted_and_project_isolation(self):
        u.sync(self.root, self.snap([self.row()]))
        u.sync(self.root, self.snap([]))
        self.assertEqual(len(u.read(self.root / 'catalog.json')['rows']), 1)
        other = self.snap([])
        other['context']['WID'] = 'different'
        with self.assertRaises(ValueError):
            u.sync(self.root, other)

    def test_selection_history_survives_empty_bgid_later(self):
        u.sync(self.root, self.snap([self.row(bgid='selected')]))
        u.sync(self.root, self.snap([self.row()]))
        p = self.plan([], [self.row()], mode='completion')
        self.assertTrue(p['blockers'])

    def test_plan_alone_binds_project_before_aliases(self):
        self.plan([dict(path=self.file())])
        self.context['WID'] = 'different'
        with self.assertRaises(ValueError):
            self.plan([])

    def test_incomplete_snapshot_blocks_automatic_add(self):
        p = u.make_plan(self.root, self.snap([], False), dict(mode='initial', expectedStatus='初次', files=[dict(path=self.file())]))
        self.assertTrue(p['blockers'])
        self.assertEqual(p['items'][0]['status'], 'blocked')

    def test_rename_refuses_overwrite_or_changed_source(self):
        src = self.file('A.1_平面图.pack')
        p = self.plan([dict(path=src)])
        dst = Path(self.file('A-1_平面图.pack', b'other'))
        with self.assertRaises(ValueError):
            u.rename(self.root, p['runId'])
        self.assertEqual(dst.read_bytes(), b'other')
        dst.unlink()
        Path(src).write_bytes(b'changed')
        with self.assertRaises(ValueError):
            u.rename(self.root, p['runId'])

    def test_two_phase_swap_and_crash_resume(self):
        a = self.file('X_甲.pack', b'one')
        b = self.file('Y_乙.pack', b'two')
        p = self.plan([dict(path=a), dict(path=b)])
        p['items'][0]['uploadName'] = Path(b).name
        p['items'][1]['uploadName'] = Path(a).name
        u.write(u.run_path(self.root, p['runId']), p)
        original = Path.rename
        count = 0
        def interrupted(path, target):
            nonlocal count
            count += 1
            if count == 4:
                raise OSError('simulated interruption while placing')
            return original(path, target)
        with patch.object(Path, 'rename', interrupted), self.assertRaises(OSError):
            u.rename(self.root, p['runId'])
        u.rename(self.root, p['runId'])
        self.assertEqual(Path(a).read_bytes(), b'two')
        self.assertEqual(Path(b).read_bytes(), b'one')
        u.rename(self.root, p['runId'])

    def test_record_requires_readback_processing_hash_and_new_version(self):
        r = self.row(versions=[dict(VSID='v1', status='变更')])
        p = self.plan([dict(path=self.file())], [r], mode='change')
        ev = self.verified(p)
        for field, value in [('processing', 'pending'), ('fileSha256', 'bad'), ('BPID', 'wrong')]:
            bad = copy.deepcopy(ev)
            bad['items'][0][field] = value
            with self.assertRaises(ValueError):
                u.record(self.root, p['runId'], bad)
        same = self.verified(p, vsid='v1')
        with self.assertRaises(ValueError):
            u.record(self.root, p['runId'], same)
        same['items'][0]['replacementEvidence'] = 'observed successful replacement response'
        self.assertEqual(u.record(self.root, p['runId'], same)['counts'], {'verified': 1})

    def test_finish_requires_receipt_and_correct_stage_and_freezes_run(self):
        p = self.plan([dict(path=self.file())], [self.row()], mode='change')
        ev = self.verified(p)
        u.record(self.root, p['runId'], ev)
        receipt = dict(snapshot=ev['snapshot'], accepted=True, evidenceRef='finish-response', serverState='已完成上传')
        bad = copy.deepcopy(receipt)
        bad['snapshot']['rows'][0]['versions'][0]['status'] = '错误阶段'
        with self.assertRaises(ValueError):
            u.finalize(self.root, p['runId'], bad)
        with self.assertRaises(ValueError):
            u.finalize(self.root, p['runId'], dict(receipt, accepted=False))
        self.assertTrue(u.finalize(self.root, p['runId'], receipt)['completeUpload'])
        with self.assertRaises(ValueError):
            u.record(self.root, p['runId'], ev)
        with self.assertRaises(ValueError):
            u.rename(self.root, p['runId'])

    def test_partial_and_unknown_cannot_finish(self):
        p = self.plan([dict(path=self.file())], [self.row()], mode='change', completeRequested=False)
        ev = self.verified(p)
        u.record(self.root, p['runId'], ev)
        receipt = dict(snapshot=ev['snapshot'], accepted=True, evidenceRef='x', serverState='x')
        with self.assertRaises(ValueError):
            u.finalize(self.root, p['runId'], receipt)
        q = self.plan([dict(path=self.file())], [self.row()], mode='change')
        unknown = dict(snapshot=self.snap([self.row()]), items=[dict(itemId=q['items'][0]['itemId'], state='unknown')])
        u.record(self.root, q['runId'], unknown)
        with self.assertRaises(ValueError):
            u.finalize(self.root, q['runId'], receipt)

    def test_cancel_status_cannot_exempt_completion_requirement(self):
        p = self.plan([], [], mode='completion')
        receipt = dict(snapshot=self.snap([self.row(bgid='selected')]), accepted=True, evidenceRef='x', serverState='x')
        with self.assertRaises(ValueError):
            u.finalize(self.root, p['runId'], receipt)

    def test_replan_reuses_verified_add_without_uploading_again(self):
        file = self.file('A.1_平面图.pack')
        old = self.plan([dict(path=file, action='add')], mode='change')
        ev = self.verified(old)
        u.record(self.root, old['runId'], ev)
        directory = self.file('M-1_目录.pack')
        new = u.make_plan(self.root, ev['snapshot'], dict(mode='change', expectedStatus='变更',
            reuseVerifiedFrom=[old['runId']], files=[dict(path=file, action='add'),
            dict(path=directory, action='add', kind='directory', directoryFor=['A.1'])]))
        self.assertEqual(new['blockers'], [])
        self.assertEqual([i['status'] for i in new['items']], ['verified', 'planned'])
        self.assertEqual(new['items'][0]['action'], 'add')
        self.assertEqual(new['items'][0]['reusedFrom']['runId'], old['runId'])


if __name__ == '__main__':
    unittest.main()
