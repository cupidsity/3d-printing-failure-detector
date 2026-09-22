# run with: python3 -m unittest discover Tools/Scripts/tests

import difflib
import importlib.machinery
import importlib.util
import os
import shutil
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


def zero_context_diff(old_text, new_text):
    # the same shape of diff the hook asks git for (-U0)
    return '\n'.join(difflib.unified_diff(old_text.splitlines(), new_text.splitlines(), 'a', 'b', n=0, lineterm=''))


def scoped(old_text, new_text):
    return hook.scoped_functions(zero_context_diff(old_text, new_text), old_text.splitlines(), new_text.splitlines())


class FunctionDetectionTest(unittest.TestCase):
    FUSION = textwrap.dedent('''\
        class Fusion:
            def fuse(self, scores):
                return max(scores)

            def reset(self):
                self.history = []


        def load_config(path):
            return path
    ''')

    def test_methods_are_qualified_with_their_class(self):
        changed = self.FUSION.replace('return max(scores)', 'return sum(scores) / len(scores)')
        self.assertEqual(scoped(self.FUSION, changed), (['Fusion.fuse'], []))

    def test_changing_a_definition_line_does_not_list_the_function_above(self):
        changed = self.FUSION.replace('def reset(self):', 'def reset(self, keep_last=False):')
        self.assertEqual(scoped(self.FUSION, changed), (['Fusion.reset'], []))

    def test_removed_functions_are_marked_deleted(self):
        changed = self.FUSION.replace('\n\ndef load_config(path):\n    return path\n', '\n')
        self.assertEqual(scoped(self.FUSION, changed), ([], ['load_config']))

    def test_removed_class_is_reported_once_not_per_method(self):
        changed = self.FUSION[self.FUSION.index('def load_config'):]
        self.assertEqual(scoped(self.FUSION, changed), ([], ['Fusion']))

    def test_nested_functions_count_as_their_outer_function(self):
        old_text = 'def fuse(scores):\n    def weight(score):\n        return score\n    return max(map(weight, scores))\n'
        new_text = old_text.replace('return score', 'return score * 2')
        self.assertEqual(scoped(old_text, new_text), (['fuse'], []))

    def test_code_inside_a_triple_quoted_string_is_ignored(self):
        old_text = 'SAMPLE = """\nclass Fake:\n    def method(self):\n        return 1\n"""\n'
        new_text = old_text.replace('return 1', 'return 2')
        self.assertEqual(scoped(old_text, new_text), ([], []))

    def test_triple_quote_inside_an_ordinary_string_does_not_hide_code(self):
        # this exact line in the test file once made every function below it look deleted
        old_text = "def first():\n    sample = 'x = \"\"\"'\n    return sample\n\n\ndef second():\n    return 1\n"
        new_text = old_text.replace('return 1', 'return 2')
        self.assertEqual(scoped(old_text, new_text), (['second'], []))

    def test_calls_inside_a_body_are_not_listed(self):
        old_text = 'export function DetectionStatus(props) {\n  const status = getStatus(props.id);\n  return status;\n}\n'
        new_text = old_text.replace('getStatus(', 'getDetectionStatus(')
        self.assertEqual(scoped(old_text, new_text), (['DetectionStatus'], []))

    def test_javascript_closing_brace_belongs_to_its_function(self):
        old_text = 'class Monitor {\n  start() {\n    poll();\n  }\n}\n'
        new_text = old_text.replace('    poll();\n  }', '    poll();\n  }  // done polling')
        self.assertEqual(scoped(old_text, new_text), (['Monitor.start'], []))

    def test_typescript_arrow_functions_are_definitions(self):
        old_text = 'export const getDetectionStatus = async (printerId: string): Promise<Status> => {\n  return fetchStatus(printerId);\n};\n'
        new_text = old_text.replace('fetchStatus(printerId)', 'fetchStatus(printerId, true)')
        self.assertEqual(scoped(old_text, new_text), (['getDetectionStatus'], []))

    def test_c_function_headers_keep_their_qualified_name(self):
        diff_text = textwrap.dedent('''\
            @@ -40 +40 @@ void Stepper::home(int axis)
            -    if (limit_hit(axis))
            +    if (limit_hit(axis) && !skip)
        ''')
        self.assertEqual(hook.c_functions(diff_text), (['Stepper::home'], []))

    def test_removed_line_that_looks_like_a_diff_header_is_still_a_change(self):
        # "--- x" inside a hunk is a removed line "-- x", not the file header
        old_text = 'def load_config():\n    query = 1\n-- old sql comment\n'
        new_text = 'def load_config():\n    query = 1\n-- new sql comment\n'
        diff_text = zero_context_diff(old_text, new_text)
        self.assertIn('--- old sql comment', diff_text)
        self.assertEqual(len(hook.parse_hunks(diff_text)[0][3]), 2)


class NewMessageTest(unittest.TestCase):
    def test_layout_matches_the_standard(self):
        # git lists changes sorted by path
        changes = [
            hook.Change('R', 'detection/client.py', old_path='detection/moonraker.py'),
            hook.Change('M', 'detection/fusion.py', functions=['Fusion.fuse'], deleted_functions=['legacy_fuse']),
            hook.Change('A', 'detection/spaghetti.py'),
            hook.Change('A', 'detection/tests/test_spaghetti.py'),
        ]
        lines, _ = hook.build_new_message(changes, 'Average detector scores',
                                          'https://github.com/owner/repo/issues/24', '#')
        self.assertEqual(lines, [
            '[Detection] Average detector scores',
            'https://github.com/owner/repo/issues/24',
            '',
            hook.REVIEWER_PLACEHOLDER,
            '',
            hook.DESCRIPTION_PLACEHOLDER,
            '',
            'Test: detection/tests/test_spaghetti.py',
            '',
            '* detection/client.py: Renamed from detection/moonraker.py.',
            '* detection/fusion.py:',
            '(Fusion.fuse):',
            '(legacy_fuse): Deleted.',
            '* detection/spaghetti.py: Added.',
            '* detection/tests/test_spaghetti.py: Added.',
        ])

    def test_no_issue_line_and_no_prefix_across_folders(self):
        changes = [hook.Change('M', 'detection/fusion.py'), hook.Change('M', 'printer/client.py')]
        lines, _ = hook.build_new_message(changes, None, None, '#')
        self.assertEqual(lines[:3], [hook.TITLE_PLACEHOLDER, '', hook.REVIEWER_PLACEHOLDER])

    def test_issue_title_already_tagged_is_not_prefixed_again(self):
        lines, _ = hook.build_new_message([hook.Change('M', 'frontend/app.tsx')], '[Frontend] Show confidence', None, '#')
        self.assertEqual(lines[0], '[Frontend] Show confidence')

    def test_several_tests_are_aligned_under_each_other(self):
        changes = [hook.Change('A', 'detection/tests/test_a.py'), hook.Change('M', 'frontend/src/status.test.tsx')]
        self.assertEqual(hook.test_lines(changes), ['Tests: detection/tests/test_a.py',
                                                    '       frontend/src/status.test.tsx'])


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

    def test_function_list_is_rebuilt_in_order_keeping_notes(self):
        existing = ['Title', '', '* detection/fusion.py:', '(fuse): Average instead of max.', '(stale_helper):', '(load_config):']
        changes = [hook.Change('M', 'detection/fusion.py', functions=['Fusion', 'Fusion.fuse', 'load_config'])]
        lines, hints = hook.build_amended_message(existing, changes, '#')
        # the old bare "fuse" note moves to its qualified name, and the generated
        # line for a function no longer touched disappears
        self.assertEqual(lines[2:], ['* detection/fusion.py:', '(Fusion):', '(Fusion.fuse): Average instead of max.', '(load_config):'])
        self.assertEqual(len(hints), 1)

    def test_noted_function_that_left_the_change_is_shown_in_hints(self):
        existing = ['Title', '', '* detection/fusion.py:', '(old_path): Explained something.', '  More detail.']
        changes = [hook.Change('M', 'detection/fusion.py', functions=['new_path'])]
        lines, hints = hook.build_amended_message(existing, changes, '#')
        self.assertEqual(lines[2:], ['* detection/fusion.py:', '(new_path):'])
        self.assertIn('#    (old_path): Explained something.', hints)
        self.assertIn('#      More detail.', hints)

    def test_deleted_marker_is_recomputed_not_kept(self):
        existing = ['Title', '', '* detection/fusion.py:', '(fuse): Deleted.', '(reset): Clears history.']
        changes = [hook.Change('M', 'detection/fusion.py', functions=['fuse'], deleted_functions=['reset'])]
        lines, _ = hook.build_amended_message(existing, changes, '#')
        self.assertEqual(lines[2:], ['* detection/fusion.py:', '(fuse):', '(reset): Deleted. Clears history.'])

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
        self.assertTrue(message.startswith('[Detection] ' + hook.TITLE_PLACEHOLDER))
        self.assertIn(hook.REVIEWER_PLACEHOLDER, message)

        # the developer writes their explanation, then review asks for another file
        written = message.replace('(fuse_confidence):', '(fuse_confidence): Average instead of max.')
        self.git('commit', '--amend', '--quiet', '-m', written)
        self.write('detection/thresholds.py', 'PAUSE_THRESHOLD = 0.8\n')
        self.git('add', '.')
        self.run_sd1('amend', '--quiet')

        updated = self.last_message()
        self.assertIn('(fuse_confidence): Average instead of max.', updated)
        self.assertIn('* detection/thresholds.py: Added.', updated)

    def test_plain_amend_leaves_the_message_alone(self):
        self.write('detection/fusion.py', 'def fuse_confidence(scores):\n    return min(scores)\n')
        self.git('add', '.')
        self.git('commit', '--amend', '--quiet', '--no-edit')
        self.assertEqual(self.last_message(), 'initial')

    def test_alias_works_from_a_subdirectory_with_relative_paths(self):
        # the alias points at Tools/Scripts/git-sd1 inside the clone, so give this
        # scratch repository its own copy the way a real clone has one
        scripts = self.repository / 'Tools' / 'Scripts'
        shutil.copytree(SCRIPTS_DIRECTORY / 'hooks', scripts / 'hooks')
        shutil.copy2(GIT_SD1, scripts / 'git-sd1')
        subprocess.run([sys.executable, str(scripts / 'git-sd1'), 'setup'], cwd=self.repository,
                       env=self.environment, check=True, capture_output=True)

        self.write('detection/fusion.py', 'def fuse_confidence(scores):\n    return min(scores)\n')
        self.write('detection/unrelated.py', 'x = 1\n')
        self.git('add', 'detection/unrelated.py')
        # "fusion.py" only means detection/fusion.py if git sd1 runs from where it was typed
        subprocess.run(['git', 'sd1', 'commit', '--quiet', 'fusion.py'], cwd=self.repository / 'detection',
                       env=self.environment, check=True, capture_output=True)
        message = self.last_message()
        self.assertIn('* detection/fusion.py:', message)
        self.assertNotIn('unrelated.py', message)

    def test_setup_does_not_overwrite_a_hand_written_hook(self):
        hooks_directory = Path(self.git('rev-parse', '--absolute-git-dir').strip()) / 'hooks'
        (hooks_directory / 'prepare-commit-msg').write_text('#!/bin/sh\necho mine\n')
        result = subprocess.run([sys.executable, str(GIT_SD1), 'setup'], cwd=self.repository,
                                env=self.environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('echo mine', (hooks_directory / 'prepare-commit-msg').read_text())


if __name__ == '__main__':
    unittest.main()
