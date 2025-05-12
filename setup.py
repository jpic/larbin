from setuptools import setup


setup(
    name='larbin',
    versioning='dev',
    setup_requires='setupmeta',
    install_requires=[
        'cli2',
        'prompt2',
        'flow2',
        'tree-sitter',
        'tree-sitter-language-pack',
        'sqlalchemy[asyncio]',
        'aiosqlite',
        'markdown-it-py',
    ],
    author='James Pic',
    author_email='jamespic@gmail.com',
    url='https://github.com/yourlabs/larbin',
    include_package_data=True,
    license='MIT',
    keywords='cli',
    python_requires='>=3.6',
    entry_points={
        'console_scripts': [
            'larbin = larbin.cli:cli.entry_point',
        ],
        'larbin': [
            'autocontext = larbin.plugins.autocontext:AutoContextPlugin',
            'ask = larbin.plugins.ask:AskPlugin',
            'plan = larbin.plugins.plan:PlanPlugin',
            'code = larbin.plugins.code:CodePlugin',
            'do = larbin.plugins.do:DoPlugin',
            'inspect = larbin.plugins.inspect:InspectPlugin',
            'prompt = larbin.plugins.prompt:PromptPlugin',
            'tdd = larbin.plugins.tdd:TddPlugin',
            'repomap = larbin.plugins.repomap.plugin:RepoMapPlugin',
        ],
        'template2': [
            'larbin = larbin.template2:Code2Template2Plugin',
        ],
        'flow2_paths': [
            'larbin = larbin.flow2:paths',
        ],
        'prompt2_paths': [
            'larbin = larbin.prompt2:paths',
        ],
        'prompt2_parser': [
            'larbin.wholefiles = larbin.prompt2:WholefilesParser',
            'larbin.searchreplace = larbin.prompt2:SearchReplaceParser',
            'larbin.diffmd = larbin.prompt2:DiffMarkdownParser',
            'larbin.pathlist = larbin.prompt2:PathList',
        ],
    },
)
