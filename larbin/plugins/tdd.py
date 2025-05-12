import cli2
import larbin
import difflib
import flow2
import os
import re
from pathlib import Path


class TddPlugin(larbin.Plugin):
    @cli2.cmd
    async def tdd(self, *cmd, _cli2=None):
        """
        Run a crashing command and make the AI iterate on it.

        :param cmd: Command to run
        """
        cmd = ' '.join(cmd)

        test_commands = self.context.data.get('test_commands', None)
        if cmd:
            if not test_commands:
                self.context.update(test_commands=[cmd])
            test_commands = [cmd]
        elif not test_commands:
            return _cli2.help(
                error='Pass some cmd, ie. `larbin tdd py.test -xv`',
            )

        projjct_files = cli2.Find(flags='-type f').run()

        for cmd in test_commands:
            proc = cli2.Proc(cmd)
            while (await proc.wait()).rc != 0:
                # redact anything that looks like a memory address to benefit
                # from cache
                stdout = re.sub('0x[a-f0-9]{12}', '', proc.stdout)
                context = dict(stdout=stdout, project_files=project_files)
                flow = flow2.Flow('larbin.cmd')
                context = await flow.run(**context)
                await context['code'].parser.apply(context['code'])
                kroc = proc.clone()
