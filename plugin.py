import subprocess
import sys

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

sys.path += ['.']
import msglen


def patchfile(fname, pat, subst):
    out = ''
    with open(fname) as f:
        while True:
            line = f.readline()
            fpos = line.find(pat)
            if fpos != -1:
                line = subst
            out += line
            if len(line) == 0:
                break

    with open(fname, 'w') as f:
        f.write(out)


class SpecialBuildHook(BuildHookInterface):
    PLUGIN_NAME = 'special'

    def initialize(self, *args):
        super().initialize(*args)
        rc = subprocess.check_output(['git', 'rev-parse', 'HEAD'])

        commitid = rc[0:6].decode('latin1')
        # print(commitid)

        patchfile('msglen/__init__.py',
                  '__commit__',
                  f'__commit__ = "{commitid}"\n')

        rc = subprocess.run(['git', 'tag', '-f', f'{msglen.__version__}'])
        assert rc.returncode == 0
