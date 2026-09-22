# run with: python3 -m unittest discover Tools/Scripts/tests

import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPTS_DIRECTORY = Path(__file__).resolve().parents[1]
GIT_SD1 = SCRIPTS_DIRECTORY / 'git-sd1'


def load_hook():
    # the hook has no .py extension (git requires the exact name), so it needs an explicit loader
    loader = importlib.machinery.SourceFileLoader('prepare_commit_msg', str(SCRIPTS_DIRECTORY / 'hooks' / 'prepare-commit-msg'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


hook = load_hook()


class FunctionDetectionTest(unittest.TestCase):
    def test_hunk_header_names_the_enclosing_python_function(self):
        diff_text = textwrap.dedent('''\
            @@ -10 +10 @@ def fuse_confidence(scores):
            -    return max(scores)
            +    return sum(scores) / len(scores)
        ''')
        self.assertEqual(hook.functions_from_diff(diff_text, '.py'), ['fuse_confidence'])

    def test_hunk_starting_on_a_definition_ignores_the_previous_function(self):
        diff_text = textwrap.dedent('''\
            @@ -20 +20 @@ def unrelated_function():
            -def pause_print(client):
            +def pause_print(client, reason):
        ''')
        self.assertEqual(hook.functions_from_diff(diff_text, '.py'), ['pause_print'])

    def test_calls_inside_a_body_are_not_listed(self):
        diff_text = textwrap.dedent('''\
            @@ -5 +5 @@ export function DetectionStatus(props) {
            -  const status = getStatus(props.id);
            +  const status = getDetectionStatus(props.id);
        ''')
        self.assertEqual(hook.functions_from_diff(diff_text, '.tsx'), ['DetectionStatus'])

    def test_typescript_arrow_functions_are_definitions(self):
        diff_text = textwrap.dedent('''\
            @@ -0,0 +1,3 @@
            +export const getDetectionStatus = async (printerId: string): Promise<Status> => {
        ''')
        self.assertEqual(hook.functions_from_diff(diff_text, '.ts'), ['getDetectionStatus'])

    def test_c_function_headers(self):
        diff_text = textwrap.dedent('''\
            @@ -40 +40 @@ static int home_axis(struct stepper *motor)
            -    if (limit_hit(motor))
            +    if (limit_hit(motor) && !skip)
        ''')
        self.assertEqual(hook.functions_from_diff(diff_text, '.c'), ['home_axis'])

    def test_removed_line_that_looks_like_a_diff_header_is_still_a_change(self):
        # "--- x" inside a hunk is a removed line "-- x", not the file header
        diff_text = '@@ -3 +3 @@ def load_config():\n--- old sql comment\n+-- new sql comment\n'
        self.assertEqual(hook.functions_from_diff(diff_text, '.py'), ['load_config'])


class NewMessageTest(unittest.TestCase):
    def test_layout_matches_the_standard(self):
        changes = [
            hook.Change('M', 'detection/fusion.py', functions=['fuse_confidence']),
            hook.Change('A', 'detection/spaghetti.py'),
            hook.Change('R', 'printer/client.py', old_path='printer/moonraker.py'),
        ]
        lines, _ = hook.build_new_message(changes, 'Detection: average detector scores',
                                          'https://github.com/owner/repo/issues/24', '#')
        self.assertEqual(lines, [
            'Detection: average detector scores',
            'https://github.com/owner/repo/issues/24',
            '',
            hook.REVIEWER_PLACEHOLDER,
            '',
            hook.DESCRIPTION_PLACEHOLDER,
            '',
            '* detection/fusion.py:',
            '(fuse_confidence):',
            '* detection/spaghetti.py: Added.',
            '* printer/client.py: Renamed from printer/moonraker.py.',
        ])

    def test_placeholders_are_used_without_an_issue(self):
        lines, _ = hook.build_new_message([], None, None, '#')
        self.assertEqual(lines[:2], [hook.TITLE_PLACEHOLDER, ''])


class AmendedMessageTest(unittest.TestCase):
    EXISTING = textwrap.dedent('''\
        Frontend: display detection confidence
        https://github.com/owner/repo/issues/24

        Reviewed by Caleb Feng.

        Shows the fused confidence on the monitoring page.

        * frontend/src/components/DetectionStatus.tsx:
        (DetectionStatus): Render the confidence bar.
        * frontend/src/styles/old.css: Tweaked colors for the bar.

        Signed-off-by: lilly <lilly@example.com>
    ''').splitlines()

    def test_keeps_notes_adds_new_files_and_reports_dropped_ones(self):
        changes = [
            hook.Change('M', 'frontend/src/components/DetectionStatus.tsx', functions=['DetectionStatus', 'formatPercent']),
            hook.Change('A', 'frontend/src/services/detection.ts'),
        ]
        lines, hints = hook.build_amended_message(self.EXISTING, changes, '#')
        self.assertEqual(lines, [
            'Frontend: display detection confidence',
            'https://github.com/owner/repo/issues/24',
            '',
            'Reviewed by Caleb Feng.',
            '',
            'Shows the fused confidence on the monitoring page.',
            '',
            '* frontend/src/components/DetectionStatus.tsx:',
            '(DetectionStatus): Render the confidence bar.',
            '(formatPercent):',
            '* frontend/src/services/detection.ts: Added.',
            '',
            'Signed-off-by: lilly <lilly@example.com>',
        ])
        self.assertIn('#    * frontend/src/styles/old.css: Tweaked colors for the bar.', hints)

    def test_rename_keeps_the_note_under_the_new_path(self):
        existing = ['Title', '', '* printer/moonraker.py: Talks to the Moonraker API.']
        changes = [hook.Change('R', 'printer/client.py', old_path='printer/moonraker.py')]
        lines, hints = hook.build_amended_message(existing, changes, '#')
        self.assertEqual(lines, ['Title', '', '* printer/client.py: Talks to the Moonraker API.'])
        self.assertEqual(len(hints), 1)

    def test_function_mentioned_in_a_note_is_not_repeated(self):
        existing = ['Title', '', '* detection/fusion.py: Rewrote fuse_confidence to average.']
        changes = [hook.Change('M', 'detection/fusion.py', functions=['fuse_confidence'])]
        lines, _ = hook.build_amended_message(existing, changes, '#')
        self.assertEqual(lines[-1], '* detection/fusion.py: Rewrote fuse_confidence to average.')

    def test_git_comments_and_scissors_stay_at_the_bottom(self):
        text = 'Title\n\n# Please enter the commit message\n# ------------------------ >8 ------------------------\n# diff\n+added'
        body, comments = hook.split_comments(text, '#')
        self.assertEqual(body, ['Title', ''])
        self.assertEqual(comments[-1], '+added')


class EndToEndTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)
        # isolate from the developer's own git config (templates, hooksPath, signing)
        self.environment = {
            **os.environ,
            'GIT_CONFIG_GLOBAL': os.devnull,
            'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_EDITOR': 'true',
            'GIT_AUTHOR_NAME': 'tester', 'GIT_AUTHOR_EMAIL': 'tester@example.com',
            'GIT_COMMITTER_NAME': 'tester', 'GIT_COMMITTER_EMAIL': 'tester@example.com',
        }
        self.git('init', '--quiet')
        (self.repository / '.gitattributes').write_text('*.py diff=python\n')
        self.write('detection/fusion.py', 'def fuse_confidence(scores):\n    return max(scores)\n')
        self.git('add', '.')
        self.git('commit', '--quiet', '-m', 'initial')
        self.run_sd1('setup')

    def tearDown(self):
        self.temporary_directory.cleanup()

    def git(self, *arguments):
        return subprocess.run(['git', *arguments], cwd=self.repository, env=self.environment,
                              check=True, capture_output=True, text=True).stdout

    def run_sd1(self, *arguments):
        return subprocess.run([sys.executable, str(GIT_SD1), *arguments], cwd=self.repository,
                              env=self.environment, check=True, capture_output=True, text=True)

    def write(self, relative_path, content):
        path = self.repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def last_message(self):
        return self.git('log', '-1', '--format=%B').strip()

    def test_commit_then_update_after_review(self):
        self.write('detection/fusion.py', 'def fuse_confidence(scores):\n    return sum(scores) / len(scores)\n')
        self.git('add', '.')
        self.run_sd1('commit', '--quiet')
        message = self.last_message()
        self.assertIn('* detection/fusion.py:\n(fuse_confidence):', message)
        self.assertIn(hook.REVIEWER_PLACEHOLDER, message)

        # the developer writes their explanation, then review asks for another file
        written = message.replace('(fuse_confidence):', '(fuse_confidence): Average instead of max.')
        self.git('commit', '--amend', '--quiet', '-m', written)
        self.write('detection/thresholds.py', 'PAUSE_THRESHOLD = 0.8\n')
        self.git('add', '.')
        self.run_sd1('commit', '--update', '--quiet')

        updated = self.last_message()
        self.assertIn('(fuse_confidence): Average instead of max.', updated)
        self.assertIn('* detection/thresholds.py: Added.', updated)

    def test_plain_amend_leaves_the_message_alone(self):
        self.write('detection/fusion.py', 'def fuse_confidence(scores):\n    return min(scores)\n')
        self.git('add', '.')
        self.git('commit', '--amend', '--quiet', '--no-edit')
        self.assertEqual(self.last_message(), 'initial')

    def test_setup_does_not_overwrite_a_hand_written_hook(self):
        hooks_directory = Path(self.git('rev-parse', '--absolute-git-dir').strip()) / 'hooks'
        (hooks_directory / 'prepare-commit-msg').write_text('#!/bin/sh\necho mine\n')
        result = subprocess.run([sys.executable, str(GIT_SD1), 'setup'], cwd=self.repository,
                                env=self.environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('echo mine', (hooks_directory / 'prepare-commit-msg').read_text())


if __name__ == '__main__':
    unittest.main()
