# coding: utf-8
# Copyright 2013 The Font Bakery Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# See AUTHORS.txt for the list of Authors and LICENSE.txt for the License.
import codecs
import glob
import os.path as op
import yaml

from checker import run_set
from checker.base import BakeryTestCase
from cli.source import get_fontsource
from cli.system import os, shutil, run
from fixer import fix_font
from fontaine.builder import Director, Builder
from fontaine.ext.subsets import Extension as SubsetExtension


BAKERY_CONFIGURATION_DEFAULTS = op.join(op.dirname(__file__), 'defaults.yaml')


def copy_single_file(src, dest, log):
    """ Copies single filename from src directory to dest directory """
    if op.exists(src) and op.isfile(src):
        shutil.copy(src, dest, log=log)


class Bakery(object):
    """ Class to handle all parts of bakery process.

        Attributes:
            builddir: Path where to place baked fonts.
                If it does not exists object will create this one.
            config: Path to yaml file describing bake configuration.
                It has to be placed in the root of project directory.
            stdout_pipe: Optional attribute to make bakery process
                loggable.

                It is a class that must have defined `write` method. Eg:

                class stdlog:

                    @staticmethod
                    def write(msg, prefix=''):
                        pass
    """

    def __init__(self, config, builddir='build', stdout_pipe=None):
        self.builddir = os.path.abspath(builddir)
        self.project_root = op.dirname(config)
        self.stdout_pipe = stdout_pipe
        self.interactive = False

        try:
            configfile = open(config, 'r')
        except OSError:
            configfile = open(BAKERY_CONFIGURATION_DEFAULTS, 'r')
            self.stdout_pipe.write(('Cannot read configuration file.'
                                    ' Using defaults'))
        self.config = yaml.safe_load(configfile)

    def interactive():
        doc = "If True then user will be asked to apply autofix"

        def fget(self):
            return self._interactive

        def fset(self, value):
            self._interactive = value

        def fdel(self):
            del self._interactive

        return locals()
    interactive = property(**interactive())

    def prepare_sources(self, path):
        fontsource = get_fontsource(path, self.stdout_pipe)
        assert fontsource
        fontsource.family_name = self.config.get('familyname', '')

        if not fontsource.before_copy():
            return

        build_source_dir = op.join(self.builddir, 'sources')
        if not op.exists(build_source_dir):
            os.makedirs(build_source_dir)

        fontsource.copy(build_source_dir)

        fontsource.after_copy(self.builddir)
        return fontsource

    def run(self, with_upstream=False):
        # 1. Copy files to build/sources directory
        for path in self.config.get('process_files', []):
            self.prepare_sources(op.join(self.project_root, path))

        if not self.config.get('process_files', []):
            return  # no files to bake

        if with_upstream:
            self.upstream_tests()

        # 2. Copy licenses to build/sources directory
        self.copy_license()

        # 3. Copy FONTLOG file
        self.copy_fontlog_txt()

        # 4. Copy DESCRIPTION.en_us.html file
        self.copy_description_html()

        # 5. Copy METADATA.json file
        self.copy_metadata_json()

        # 6. Copy any TXT files selected by user
        self.copy_txt_files()

        # 7. TTFAutohint
        if self.config.get('ttfautohint', None):
            self.ttfautohint_process()

        # 8. Create subset files
        self.subset_process()

        # 9. Generate METADATA.json
        self.generate_metadata_json()

        # 10. Generate pyfontaine description of font
        self.pyfontaine_process()

        # 11. Run result tests
        self.result_tests_process()

        # 12. Run auto fixes
        self.autofix_process()

    def autofix_process(self):
        self.stdout_pipe.write('Applying autofixes\n', prefix='### ')
        _out_yaml = op.join(self.builddir, '.tests.yaml')
        fix_font(_out_yaml, self.builddir, interactive=self.interactive,
                 log=self.stdout_pipe)

    def result_tests_process(self):
        self.stdout_pipe.write('Run tests for baked files\n', prefix='### ')
        _out_yaml = op.join(self.builddir, '.tests.yaml')

        if op.exists(_out_yaml):
            return yaml.safe_load(open(_out_yaml, 'r'))

        result = {}
        os.chdir(self.builddir)
        for font in glob.glob("*.ttf"):
            result[font] = run_set(op.join(self.builddir, font), 'result',
                                   log=self.stdout_pipe)

        if not result:
            return

        l = open(_out_yaml, 'w')
        l.write(yaml.safe_dump(result))
        l.close()

        return yaml.safe_load(open(_out_yaml, 'r'))

    def pyfontaine_process(self):
        self.stdout_pipe.write('pyFontaine TTFs\n', prefix='### ')

        os.chdir(self.builddir)
        director = Director()

        fonts = []
        files = glob.glob('*.ttf')
        for font in files:
            fonts.append(op.join(self.builddir, font))

        self.stdout_pipe.write('fontaine --text %s > sources/fontaine.txt' % ' '.join(fonts),
                               prefix='$ ')
        try:
            fontaine_log = op.join(self.builddir, 'sources', 'fontaine.txt')
            fp = codecs.open(fontaine_log, 'w', 'utf-8')
        except OSError:
            self.stdout_pipe.write("Failed to open fontaine log to write")
            return

        try:
            result = Builder.text_(director.construct_tree(fonts))
            fp.write(result.output)
        except:
            self.stdout_pipe.write(('PyFontaine raised exception.'
                                    ' Check latest version.\n'))
            raise

    def ansiprint(self, message, color):
        self.stdout_pipe.write(message + '\n')

    def generate_metadata_json(self):
        from scripts import genmetadata
        self.stdout_pipe.write('Generate METADATA.json (genmetadata.py)\n',
                               prefix='### ')
        try:
            os.chdir(self.builddir)
            # reassign ansiprint to our own method
            genmetadata.ansiprint = self.ansiprint
            genmetadata.run(self.builddir)
        except Exception, e:
            self.stdout_pipe.write(e.message + '\n', prefix="### Error:")
            raise

    def execute_pyftsubset(self, subset, name, glyphs="", args=""):
        cmd = ("pyftsubset %(out)s.ttf %(glyphs)s"
               " --notdef-outline --name-IDs='*' --hinting")
        if args:
            cmd += " " + args
        cmd = cmd % {'glyphs': glyphs.replace('\n', ' '),
                     'out': op.join(self.builddir, name)}
        run(cmd, cwd=self.builddir, log=self.stdout_pipe)

        shutil.move(op.join(self.builddir, name) + '.ttf.subset',
                    op.join(self.builddir, name) + '.' + subset,
                    log=self.stdout_pipe)

    def subset_process(self):
        self.stdout_pipe.write('Subset TTFs (pyftsubset)\n', prefix='### ')

        for subset in self.config.get('subset', []):
            glyphs = open(SubsetExtension.get_subset_path(subset)).read()

            os.chdir(op.join(self.builddir, 'sources'))
            for name in list(glob.glob("*.ufo")) + list(glob.glob("*.ttx")):
                name = name[:-4]  # cut .ufo|.ttx
                self.execute_pyftsubset(subset, name, glyphs=glyphs)

                # create menu subset
                self.execute_pyftsubset('menu', name,
                                        args='--text="%s"' % op.basename(name))

    def ttfautohint_process(self):
        """
        Run ttfautohint with project command line settings for each
        ttf file in result src folder, outputting them in the _out root,
        or just copy the ttfs there.
        """
        # $ ttfautohint -l 7 -r 28 -G 0 -x 13 -w "" \
        #               -W -c original_font.ttf final_font.ttf
        params = self.config.get('ttfautohint', '')
        if not params:
            return
        self.stdout_pipe.write('Autohint TTFs (ttfautohint)\n', prefix='### ')

        if 'devanagari' in self.config.get('subset', []):
            params += ' -f deva'

        os.chdir(self.builddir)
        for name in glob.glob("*.ttf"):
            name = op.join(self.builddir, name[:-4])  # cut .ttf
            cmd = ("ttfautohint {params} '{name}.ttf' "
                   "'{name}.autohint.ttf'").format(params=params.strip(),
                                                   name=name)
            run(cmd, cwd=self.builddir, log=self.stdout_pipe)
            shutil.move(name + '.autohint.ttf', name + '.ttf',
                        log=self.stdout_pipe)

    def copy_fontlog_txt(self):
        copy_single_file(op.join(self.project_root, 'FONTLOG.txt'),
                         self.builddir, self.stdout_pipe)

    def copy_description_html(self):
        copy_single_file(op.join(self.project_root, 'DESCRIPTION.en_us.html'),
                         self.builddir, self.stdout_pipe)

    def copy_metadata_json(self):
        copy_single_file(op.join(self.project_root, 'METADATA.json'),
                         self.builddir, self.stdout_pipe)

    def copy_txt_files(self):
        if self.config.get('txt_files_copied', None):
            for filename in self.config['txt_files_copied']:
                copy_single_file(op.join(self.project_root, filename),
                                 self.builddir, self.stdout_pipe)

    def copy_license(self):
        # Copy license file
        # TODO: Infer license type from filename
        # TODO: Copy file based on license type
        if self.config.get('license_file', None):
            # Set _in license file name
            licenseFileInFullPath = self.config['license_file']
            licenseFileIn = licenseFileInFullPath.split('/')[-1]
            # List posible OFL and Apache filesnames
            listOfOflFilenames = ['Open Font License.markdown', 'OFL.txt',
                                  'OFL.md']
            listOfApacheFilenames = ['APACHE.txt', 'LICENSE']
            # Canonicalize _out license file name
            if licenseFileIn in listOfOflFilenames:
                licenseFileOut = 'OFL.txt'
            elif licenseFileIn in listOfApacheFilenames:
                licenseFileOut = 'LICENSE.txt'
            else:
                licenseFileOut = licenseFileIn
            # Copy license file
            _in_license = op.join(self.project_root, licenseFileInFullPath)
            _out_license = op.join(self.builddir, licenseFileOut)

            shutil.copy(_in_license, _out_license, log=self.stdout_pipe)
        else:
            self.stdout_pipe.write('License file not copied\n',
                                   prefix='Error: ')

    def upstream_tests(self):
        result = {}
        source_dir = op.join(self.builddir, 'sources')
        self.stdout_pipe.write('Run upstream tests\n', prefix='### ')

        result['/'] = run_set(source_dir, 'upstream-repo')
        for font in self.config.get('process_files', []):
            if font[-4:] in '.ttx':
                result[font] = run_set(op.join(source_dir, font),
                                       'upstream-ttx', log=self.stdout_pipe)
            else:
                result[font] = run_set(op.join(source_dir, font),
                                       'upstream', log=self.stdout_pipe)

        _out_yaml = op.join(source_dir, '.upstream.yaml')

        l = codecs.open(_out_yaml, mode='w', encoding="utf-8")
        l.write(yaml.safe_dump(result))
        l.close()

# register yaml serializer for tests result objects.


def repr_testcase(dumper, data):

    def method_doc(doc):
        if doc is None:
            return "None"
        else:
            import codecs
            doc = u' '.join(doc.split())
            print doc, data._testMethodName
            return codecs.utf_8_encode(doc)[0].strip()

    _ = {
        'methodDoc': method_doc(data._testMethodDoc),
        'tool': data.tool,
        'name': data.name,
        'methodName': data._testMethodName,
        'targets': data.targets,
        'tags': getattr(data, data._testMethodName).tags,
        'err_msg': getattr(data, '_err_msg', '').decode('utf-8',
                                                        'xmlcharrefreplace')
    }
    return dumper.represent_mapping(u'tag:yaml.org,2002:map', _)

yaml.SafeDumper.add_multi_representer(BakeryTestCase, repr_testcase)
