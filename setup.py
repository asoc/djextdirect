from setuptools import setup, find_packages

from djextdirect import VERSION

setup(
    name='djextdirect',
    version='%d.%d' % VERSION,
    description='Ext.Direct server-side and client-side implementation for Django',
    author='Alex Honeywell',
    author_email='alex.honeywell@gmail.com',
    url='https://github.com/asoc/djextdirect',
    download_url='https://github.com/asoc/djextdirect/archive/master.zip',
    packages=find_packages(),
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Utilities',
    ],
)

