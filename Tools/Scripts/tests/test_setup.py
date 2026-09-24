# run with: python3 -m unittest discover Tools/Scripts/tests

import importlib.machinery
import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIRECTORY = Path(__file__).resolve().parents[1]
GIT_SD1 = SCRIPTS_DIRECTORY / 'git-sd1'
SHIM = SCRIPTS_DIRECTORY / 'git-sd1.cmd'


def load_git_sd1():
    loader = importlib.machinery.SourceFileLoader('git_sd1', str(GIT_SD1))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


git_sd1 = load_git_sd1()


class PathInstructionsTest(unittest.TestCase):
    def test_powershell_gets_powershell_commands(self):
        lines = git_sd1.path_instructions(r'C:\Users\layla\detector\Tools\Scripts', windows=True)
        self.assertTrue(any('$env:Path' in line for line in lines))
        self.assertTrue(any('SetEnvironmentVariable' in line for line in lines))
        self.assertTrue(all(r'C:\Users\layla\detector\Tools\Scripts' in line
                            for line in lines if line.startswith('    ')))

    def test_unix_shells_get_an_export_line(self):
        lines = git_sd1.path_instructions('/home/caleb/detector/Tools/Scripts', windows=False)
        self.assertIn('    export PATH="/home/caleb/detector/Tools/Scripts:$PATH"', lines)


class PermanentPathTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home)
        self.scripts = '/Users/layla/detector/Tools/Scripts'

    @unittest.skipIf(git_sd1.WINDOWS, 'reads the registry on windows instead')
    def test_a_profile_that_sets_the_directory_counts(self):
        (self.home / '.zshrc').write_text(f'export PATH="{self.scripts}:$PATH"\n')
        self.assertTrue(git_sd1.path_is_permanent(self.scripts, home=self.home))

    @unittest.skipIf(git_sd1.WINDOWS, 'reads the registry on windows instead')
    def test_the_home_directory_written_as_a_variable_counts(self):
        # how a profile is normally written, and what the expanded path misses
        scripts = self.home / 'Projects' / 'detector' / 'Tools' / 'Scripts'
        for spelling in ('$HOME/Projects/detector/Tools/Scripts',
                         '${HOME}/Projects/detector/Tools/Scripts',
                         '~/Projects/detector/Tools/Scripts'):
            (self.home / '.zshrc').write_text(f'export PATH="{spelling}:$PATH"\n')
            self.assertTrue(git_sd1.path_is_permanent(scripts, home=self.home), spelling)

    @unittest.skipIf(git_sd1.WINDOWS, 'reads the registry on windows instead')
    def test_profiles_that_never_mention_it_do_not(self):
        (self.home / '.zshrc').write_text('alias ll="ls -l"\n')
        (self.home / '.bashrc').write_text('export PATH="/opt/other:$PATH"\n')
        self.assertFalse(git_sd1.path_is_permanent(self.scripts, home=self.home))

    @unittest.skipIf(git_sd1.WINDOWS, 'reads the registry on windows instead')
    def test_no_profiles_at_all(self):
        self.assertFalse(git_sd1.path_is_permanent(self.scripts, home=self.home))


class WindowsShimTest(unittest.TestCase):
    def setUp(self):
        self.contents = SHIM.read_bytes()

    def test_crlf_line_endings(self):
        # cmd.exe mis-parses a batch file saved with unix line endings
        self.assertNotIn(b'\n', self.contents.replace(b'\r\n', b''))

    def test_runs_the_script_beside_it_with_every_argument(self):
        text = self.contents.decode()
        self.assertIn('set "script=%~dp0git-sd1"', text)
        # %* so `git-sd1 commit --issue 24` reaches the script intact
        self.assertEqual(text.count('"%script%" %*'), 3)

    def test_tries_the_launcher_before_a_bare_python(self):
        interpreters = [line.split()[0] for line in self.contents.decode().splitlines()
                        if line.endswith('"%script%" %*')]
        self.assertEqual(interpreters, ['py', 'python', 'python3'])


if __name__ == '__main__':
    unittest.main()
