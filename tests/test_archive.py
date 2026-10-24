import copy
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from archive_store import official_version, save_snapshot, snapshot_from_run, verified_current, write_tree, GENERATED
from version_compare import compare, git, load_snapshot, tags, write_comparison
from github_sync import run_network, configure_remote, upload, UploadError
from test_updates import snapshot, character, module


class ArchiveTests(unittest.TestCase):
    def test_remote_rename_migrates_original_url_and_rejects_other_repositories(self):
        from archive_store import REPOSITORY
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); repo = root / 'repo'
            save_snapshot(repo, self.sample(root))
            git(repo, 'remote', 'add', 'origin', 'https://github.com/Siyin22/arknights-operator-data.git')
            for old in ('arknights-operator-data', 'arknights-update-tool'):
                git(repo, 'remote', 'set-url', 'origin', f'https://github.com/Siyin22/{old}.git')
                configure_remote(repo)
                self.assertEqual(git(repo, 'remote', 'get-url', 'origin').strip(), f'https://github.com/{REPOSITORY}.git')
            git(repo, 'remote', 'set-url', 'origin', 'https://github.com/someone/another.git')
            with self.assertRaisesRegex(UploadError, '不一致'):
                configure_remote(repo)

    def test_upload_rejects_tracked_runtime_settings_before_network_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); repo = root / 'repo'
            save_snapshot(repo, self.sample(root))
            (repo / 'settings.json').write_text('{}', encoding='utf-8')
            git(repo, 'add', '-f', 'settings.json')
            git(repo, 'commit', '-m', 'Accidentally track runtime settings')
            with patch('github_sync.run_network') as network:
                with self.assertRaisesRegex(UploadError, '应忽略'):
                    upload(repo)
                network.assert_not_called()

    def test_layout_migration_preserves_old_tags_and_saves_new_data_under_same_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); repo = root / 'repo'; sample = self.sample(root)
            save_snapshot(repo, sample)
            original_tag = git(repo, 'rev-parse', '78.2.0')
            data = repo / '版本数据'; data.mkdir()
            git(repo, 'mv', '--', *GENERATED, '版本数据/')
            # Current metadata must still supplement tags from the old root layout.
            sample['version']['client_version'] = '2.7.81'
            write_tree(data, sample, None, ['78.2.0'])
            (repo / '.gitignore').write_text('settings.json\n__pycache__/\n', encoding='utf-8')
            source = repo / 'src'; source.mkdir()
            (source / 'source.py').write_text('# maintained source\n', encoding='utf-8')
            git(repo, 'add', '-A')
            git(repo, 'commit', '-m', 'Unify tool and data layout')
            (repo / 'settings.json').write_text('{"game":"local"}', encoding='utf-8')
            self.assertEqual(load_snapshot(data, '78.2.0'), sample)
            self.assertEqual(verified_current(data), sample)
            sample['version']['official_version'] = '78.3.0'
            sample['operators']['char_a']['name'] = '新版名字'
            save_snapshot(data, sample)
            self.assertFalse((data / '.git').exists())
            self.assertTrue((source / 'source.py').is_file())
            self.assertNotIn('settings.json', git(repo, 'ls-files').splitlines())
            self.assertEqual(git(repo, 'status', '--porcelain'), '')
            self.assertEqual(verified_current(data), sample)
            self.assertEqual(load_snapshot(repo, '78.3.0'), sample)
            self.assertEqual(git(repo, 'rev-parse', '78.2.0'), original_tag)
            self.assertIn('char_a', compare(load_snapshot(data, '78.2.0'), sample)['operators']['changed'])

    def test_presentation_refresh_preserves_published_tag_and_validates_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);repo=root/'repo';sample=self.sample(root)
            save_snapshot(repo,sample)
            original=git(repo,'rev-parse','78.2.0')
            sample['version']['client_version']='2.7.81'
            write_tree(repo,sample,None,['78.2.0'])
            git(repo,'add','--',*GENERATED)
            git(repo,'commit','-m','Improve presentation and client metadata')
            self.assertEqual(git(repo,'rev-parse','78.2.0'),original)
            self.assertEqual(verified_current(repo),sample)
            self.assertFalse(save_snapshot(repo,sample)['created'])
            self.assertEqual(load_snapshot(repo,'78.2.0')['version']['client_version'],'2.7.81')

    def test_report_embeds_offline_export_and_escapes_data(self):
        from report_renderer import render_report
        with tempfile.TemporaryDirectory() as tmp:
            sample=self.sample(Path(tmp))
            sample['operators']['char_a']['name']='</script><script>alert(1)</script>'
            page=render_report(None,sample,compare(None,sample))
            self.assertNotIn('</script><script>alert(1)</script>',page)
            self.assertIn('导出本次资料',page)
            self.assertNotIn('window.print()',page)
            self.assertIn('html2canvas',page)
            self.assertNotIn('<script src=',page)

    def test_operator_extraction_accepts_hashed_names_only_for_needed_tables(self):
        from extract import operator_asset
        self.assertTrue(operator_asset(Path('excel/character_table9fc534.bytes')))
        self.assertTrue(operator_asset(Path('excel/battle_equip_table91e6b6.bytes')))
        self.assertTrue(operator_asset(Path('excel/data_version.txt')))
        self.assertFalse(operator_asset(Path('excel/uniequip_data.bytes')))
        self.assertFalse(operator_asset(Path('levels/level_main_01.bytes')))

    def sample(self, root):
        run = snapshot(root, 'run', 'resource-1', {'char_a': character()}, {'module_a': module('char_a')})
        (run / 'raw/excel/data_version.txt').write_text('VersionControl:78.2.0\n', encoding='utf-8')
        return snapshot_from_run(run)

    def test_version_is_official_and_malformed_version_is_rejected(self):
        self.assertEqual(official_version('Change:123\nVersionControl:78.2.0\n'), '78.2.0')
        with self.assertRaises(ValueError):official_version('2026-10-19')

    def test_repeat_is_noop_and_changed_same_version_never_rewrites_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); repo = root / 'repo'; sample = self.sample(root)
            self.assertTrue(save_snapshot(repo, sample)['created'])
            head = git(repo, 'rev-parse', 'HEAD')
            self.assertFalse(save_snapshot(repo, sample)['created'])
            self.assertEqual(git(repo, 'rev-parse', 'HEAD'), head)
            sample['operators']['char_a']['name'] = '不能覆盖旧版本'
            with self.assertRaisesRegex(ValueError, '内容不同'):save_snapshot(repo, sample)
            self.assertEqual(git(repo, 'rev-parse', '78.2.0'), head)
            self.assertEqual(git(repo, 'status', '--porcelain'), '')

    def test_two_versions_compare_added_changed_removed_without_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); repo = root / 'repo'; before = self.sample(root)
            save_snapshot(repo, before)
            after = copy.deepcopy(before)
            after['version']['official_version'] = '78.3.0'
            after['version']['resource_version'] = 'resource-2'
            after['operators']['char_a']['skills'][0]['levels'][-1]['description'] = '新的技能效果'
            after['operators']['char_b'] = copy.deepcopy(after['operators']['char_a'])
            after['operators']['char_b']['id'] = 'char_b'
            after['operators']['char_b']['name'] = '新增干员'
            after['modules']['module_b'] = copy.deepcopy(after['modules'].pop('module_a'))
            after['modules']['module_b']['id'] = 'module_b'
            save_snapshot(repo, after)
            self.assertEqual(tags(repo), ['78.2.0', '78.3.0'])
            self.assertEqual(verified_current(repo), after)
            old = load_snapshot(repo, '78.2.0'); new = load_snapshot(repo, '78.3.0')
            difference = compare(old, new)
            self.assertEqual(difference['operators']['added'], ['char_b'])
            self.assertEqual(difference['operators']['changed'], ['char_a'])
            self.assertEqual(difference['modules']['removed'], ['module_a'])
            self.assertFalse((repo / 'modules/module_a.json').exists())
            head = git(repo, 'rev-parse', 'HEAD')
            result = write_comparison(repo, '78.2.0', '78.3.0', root / 'comparison')
            self.assertIn('新的技能效果', result.read_text(encoding='utf-8'))
            self.assertIn('新增干员', result.read_text(encoding='utf-8'))
            self.assertEqual(git(repo, 'rev-parse', 'HEAD'), head)
            self.assertEqual(git(repo, 'status', '--porcelain'), '')

    def test_public_tree_has_no_raw_files_or_machine_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); repo = root / 'repo'
            save_snapshot(repo, self.sample(root))
            tracked = git(repo, 'ls-files').splitlines()
            self.assertFalse(any(p.startswith(('raw/', 'analysis/', 'schemas/')) for p in tracked))
            for name in tracked:
                text = (repo / name).read_text(encoding='utf-8')
                self.assertNotIn(str(root), text)
            (repo / 'operators/char_a.json').write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '本地修改'):verified_current(repo)

    def test_proxy_is_child_scoped_and_only_reads_retry(self):
        original = os.environ.copy()
        failure = subprocess.CompletedProcess([], 1, '', 'TLS connection failed')
        success = subprocess.CompletedProcess([], 0, 'ok', '')
        with patch('github_sync.proxy_available', return_value=True), patch('github_sync.subprocess.run', side_effect=[failure, success]) as run:
            self.assertEqual(run_network(['gh', 'api', 'user'], read_only=True), 'ok')
            self.assertEqual(run.call_args_list[0].kwargs['env']['HTTPS_PROXY'], 'http://127.0.0.1:7897')
            self.assertNotIn('HTTPS_PROXY', run.call_args_list[1].kwargs['env'])
        with patch('github_sync.proxy_available', return_value=True), patch('github_sync.subprocess.run', return_value=failure) as run:
            with self.assertRaises(UploadError):run_network(['gh', 'repo', 'create'])
            self.assertEqual(run.call_count, 1)
        self.assertEqual(dict(os.environ), original)


if __name__ == '__main__':unittest.main()
