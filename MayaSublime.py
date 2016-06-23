# ST2/ST3 compat
from __future__ import print_function

import re
import sys
import time
import os.path
import fnmatch
import textwrap

from telnetlib import Telnet

import sublime
import sublime_plugin


if sublime.version() < '3000':
    # we are on ST2 and Python 2.X
    _ST3 = False
else:
    _ST3 = True


# Our default plugin settings
_settings = {
    'host': '127.0.0.1',
    'mel_port': 7001,
    'py_port': 7002,
    'strip_sending_comments': True
}


class send_to_mayaCommand(sublime_plugin.TextCommand):

    # A template wrapper for sending Python source safely
    # over the socket.
    # Executes in a private namespace to avoid collisions
    # with the main environment in Maya.
    # Also handles catches and printing exceptions so that
    # they are not masked.
    PY_CMD_TEMPLATE = textwrap.dedent('''
		import traceback
		import __main__

		namespace = __main__.__dict__.get('_sublime_SendToMaya_plugin')
		if not namespace:
			namespace = __main__.__dict__.copy()
			__main__.__dict__['_sublime_SendToMaya_plugin'] = namespace

		try:
			if {ns}:
				namespace['__file__'] = {fp!r}
				{xtype}({cmd!r}, namespace, namespace)
			else:
				{xtype}({cmd!r})
		except:
			traceback.print_exc()
	''')

    # Match single-line comments in MEL/Python
    RX_COMMENT = re.compile(r'^\s*(//|#)')

    def run(self, edit, send_package=False):

        print("send:{0}".format(send_package))
        # Do we have a valid source language?
        syntax = self.view.settings().get('syntax')

        if re.search(r'python', syntax, re.I):
            lang = 'python'
            sep = '\n'

        elif re.search(r'mel', syntax, re.I):
            lang = 'mel'
            sep = '\r'

        else:
            print('No Maya-Recognized Language Found')
            return

        isPython = (lang == 'python')

        # Apparently ST3 doesn't always sync up its latest
        # plugin settings?
        if _ST3 and _settings['host'] == None:
            sync_settings()

        host = _settings['host']
        port = _settings[
            'py_port'] if lang == 'python' else _settings['mel_port']

        # Check the current selection size to determine
        # how we will send the source to be executed.
        selections = self.view.sel()  # Returns type sublime.RegionSet
        selSize = 0
        for sel in selections:
            if not sel.empty():
                selSize += 1

        if selSize == 0:
            current_file = self.view.file_name()
            if send_package:
                parent_dir = os.path.dirname(current_file)
                python_files = fnmatch.filter(os.listdir(parent_dir), "*.py")
                for f in python_files:
                    fullpath = os.path.join(parent_dir, f)
                    if fullpath == current_file or f == "__init__.py":
                        continue
                    else:
                        self.exec_file(host, port, isPython,
                                       lang, sep, fullpath)
                    print(os.path.join(parent_dir, f))

                # exec current file
                self.exec_file(host, port, isPython,
                               lang, sep, current_file)

            else:
                self.exec_file(host, port, isPython, lang, sep, current_file)
        else:
            self.exec_selection(host, port, lang, isPython, sep)

    def exec_file(self, host, port, isPython, lang, sep, file_path):
        snips = []
        execType = 'execfile'

        print("Nothing Selected, Attempting to exec entire file")

        if self.view.is_dirty():
            sublime.error_message("Save Changes Before Maya Source/Import")
            return

        if file_path is None:
            sublime.error_message(
                "File must be saved before sending to Maya")
            return

        plat = sublime_plugin.sys.platform
        if plat == 'win32':
            file_path = file_path.replace('\\', '\\\\')
            print("FILE PATH:", file_path)

        if isPython:
            snips.append(file_path)
        else:
            snips.append('rehash; source "{0}";'.format(file_path))

        mCmd = str(sep.join(snips))
        if not mCmd:
            return

        print('Sending {0}:\n{1!r}\n...'.format(lang, mCmd[:200]))

        if isPython:
            # We need to wrap our source string into a template
            # so that it gets executed properly on the Maya side
            no_collide = _settings['no_collisions']
            opts = dict(xtype=execType, cmd=mCmd, fp=file_path, ns=no_collide)
            mCmd = self.PY_CMD_TEMPLATE.format(**opts)

        self.send_to_maya(host, port, mCmd)

    def exec_selection(self, host, port, isPython, lang, sep):
        snips = []
        execType = 'exec'
        file_path = ''

        substr = self.view.substr
        match = self.RX_COMMENT.match
        stripComments = _settings['strip_comments']

        # Build up all of the selected lines, while removing single-line comments
        # to simplify the amount of data being sent.
        for sel in selections:
            if stripComments:
                snips.extend(line for line in substr(
                    sel).splitlines() if not match(line))
            else:
                snips.extend(substr(sel).splitlines())

        mCmd = str(sep.join(snips))
        if not mCmd:
            return

        print('Sending {0}:\n{1!r}\n...'.format(lang, mCmd[:200]))

        if isPython:
            # We need to wrap our source string into a template
            # so that it gets executed properly on the Maya side
            no_collide = _settings['no_collisions']
            opts = dict(xtype=execType, cmd=mCmd, fp=file_path, ns=no_collide)
            mCmd = self.PY_CMD_TEMPLATE.format(**opts)

        self.send_to_maya(host, port, mCmd)

    def send_to_maya(self, host, port, mCmd):
        c = None

        try:
            c = Telnet(host, int(port), timeout=3)
            if _ST3:
                c.write(mCmd.encode(encoding='UTF-8'))
            else:
                c.write(mCmd)

        except Exception:
            e = sys.exc_info()[1]
            err = str(e)
            sublime.error_message(
                "Failed to communicate with Maya (%(host)s:%(port)s)):\n%(err)s" % locals(
                )
            )
            raise

        else:
            time.sleep(.1)

        finally:
            if c is not None:
                c.close()


def settings_obj():
    return sublime.load_settings("MayaSublime.sublime-settings")


def sync_settings():
    so = settings_obj()
    _settings['host'] = so.get('maya_hostname')
    _settings['py_port'] = so.get('python_command_port')
    _settings['mel_port'] = so.get('mel_command_port')
    _settings['strip_comments'] = so.get('strip_sending_comments')
    _settings['no_collisions'] = so.get('no_collisions')


settings_obj().clear_on_change("MayaSublime.settings")
settings_obj().add_on_change("MayaSublime.settings", sync_settings)
sync_settings()
