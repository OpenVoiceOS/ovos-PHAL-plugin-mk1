#!/usr/bin/env python3
from os.path import join, dirname

from setuptools import setup


def get_version():
    """ Find the version of this skill"""
    version_file = join(dirname(__file__), 'ovos_PHAL_plugin_mk1/version.py')
    major, minor, build, alpha = (None, None, None, None)
    with open(version_file) as f:
        for line in f:
            if 'VERSION_MAJOR' in line:
                major = line.split('=')[1].strip()
            elif 'VERSION_MINOR' in line:
                minor = line.split('=')[1].strip()
            elif 'VERSION_BUILD' in line:
                build = line.split('=')[1].strip()
            elif 'VERSION_ALPHA' in line:
                alpha = line.split('=')[1].strip()

            if ((major and minor and build and alpha) or
                    '# END_VERSION_BLOCK' in line):
                break
    version = f"{major}.{minor}.{build}"
    if int(alpha):
        version += f"a{alpha}"
    return version


PLUGIN_ENTRY_POINT = 'ovos-phal-mk1=ovos_PHAL_plugin_mk1:MycroftMark1'
setup(
    name='ovos-PHAL-plugin-mk1',
    version=get_version(),
    description='A PHAL plugin for mycroft',
    url='https://github.com/OpenVoiceOS/ovos-PHAL-plugin-mk1',
    author='JarbasAi',
    author_email='jarbasai@mailfence.com',
    license='Apache-2.0',
    packages=['ovos_PHAL_plugin_mk1'],
    install_requires=["ovos-plugin-manager>=0.0.24",
                      "ovos-mark1-utils>=0.0.0a2",
                      "ovos-utils>=0.0.38",
                      "pyserial~=3.0"],
    zip_safe=True,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Text Processing :: Linguistic',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    entry_points={'ovos.plugin.phal': PLUGIN_ENTRY_POINT}
)
