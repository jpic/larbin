import cli2
import larbin
import prompt2


class PlanPlugin(larbin.Plugin):
    @cli2.cmd(color='yellow')
    async def plan(self, *prompt):
        """
        Plan management

        Without arguments: print current plan if any, otherwise spawn EDITOR
        With prompt arguments: generate a plan if none, otherwise refine it.

        :param prompt: Your prompt, otherwise latest prompt will be used if any
        """
        if not prompt:
            if self.context.plan.exists():
                cli2.editor(path=self.context.plan)
                return
            elif prompt := self.context.context_prompt(prompt):
                pass
            else:
                prompt = cli2.editor('Prompt here to generate a plan')
        else:
            prompt = ' '.join(prompt)

        if not self.context.data.get('paths', None):
            if cli2.confirm('No files in context, figure them out?'):
                await self.context.plugins['autocontext'].autocontext(prompt)

        previous_plan = None
        if self.context.plan.exists():
            with self.context.plan.open('r') as f:
                previous_plan = f.read()

        prompt = prompt2.Prompt(
            'larbin.plan',
            previous_plan=previous_plan,
            prompt=prompt,
        )
        prompt.content += await self.context.template()

        model = prompt2.Model(['plan', 'architect'])
        if self.context.plan.exists():
            print(cli2.t.o.b('UPDATING PLAN'))
        else:
            print(cli2.t.o.b('GENERATING PLAN'))
        result = await model(prompt)

        with self.context.plan.open('w') as f:
            f.write(result)
