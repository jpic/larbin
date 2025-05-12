"""
Base Workflowant plugin which you can inherit from.

Plugins register themselves over the ``larbin_workflow`` entrypoint, and are
exposed on the command line for every context.

To create your own plugin, create a Python package with an entrypoint like:

.. code-block:: python

    'larbin_workflow': [
        'plugin_name = your.module:ClassName',
    ]

Install the package and ``plugin_name`` will appear in the larbin command line.
"""

import asyncio
import cli2
import functools
import importlib.metadata
import os
import prompt2
import re
import shlex
import textwrap
from larbin import project


class Plugin:
    """
    Base class for larbin plugins.

    Plugins provide specific functionalities accessible via the larbin CLI.
    They interact with the project context and external tools like AI models.

    :param context: The main application context object.
    :type context: larbin.Context
    """
    def __init__(self, context):
        """
        Initialize the plugin with the application context.

        :param context: The application context containing project info,
                        paths, data, etc.
        :type context: larbin.Context
        """
        self.context = context

    @property
    def project(self):
        """
        Get the project object associated with the current context.

        :return: The project instance.
        :rtype: larbin.project.Project
        """
        return self.context.project

