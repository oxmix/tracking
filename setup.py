from setuptools import setup

setup(
    name='Tracking',
    version='0.2',
    url='oxmix.net',
    license='',
    author='Oxmix',
    author_email='oxmix@me.com',
    description='For Autofon hardware',
    install_requires=[
        'redis',
        'setproctitle'
    ]
)
