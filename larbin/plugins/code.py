import cli2
import larbin
import prompt2
import os


class CodePlugin(larbin.Plugin):
    @cli2.cmd
    async def code(self, *prompt, _cli2=None):
        """
        Edit files

        :param prompt: Your prompt, otherwise context prompt if any
        """
        if prompt:
            prompt = ' '.join(prompt)
        elif self.context.plan.exists():
            with self.context.plan.open('r') as f:
                prompt = f.read()
            print(cli2.t.g('READ PLAN'))
            print(cli2.highlight(prompt, 'Markdown'))
        else:
            return _cli2.help(error='Make a plan or pass a prompt argument')

        print(cli2.t.o.b('CODING'))
        model = prompt2.Model(['edit', 'editor'])
        prompt = prompt2.Prompt(content=prompt)
        prompt.content += await self.context.template()
        result = await model(
            prompt,
            os.getenv('EDIT_PARSER', 'larbin.searchreplace'),
        )
        await result.parser.apply(result)
