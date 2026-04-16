from setuptools import setup
from mypyc.build import mypycify

setup(
    name='mypyc_output',
    ext_modules=mypycify(
        ['/home/graham/workspace/experiments/pi-mono/.pi/skills/extract-tables/src/python/models.py'],
        opt_level="3",
        debug_level="1",
        strict_dunder_typing=False,
        log_trace=False,
    ),
)
