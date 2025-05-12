import cli2
import prompt2


class PromptTask(cli2.Task):
    def __init__(self, name, template, parser=None, model=None):
        self.template = template
        self.parser = parser
        self.model = model
        super().__init__(name)

    async def run(self, executor, context):
        prompt = prompt2.Prompt(self.template, **context)
        model = self.model or context['model']
        return await model(prompt, self.parser)
