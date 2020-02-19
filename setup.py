#!/usr/bin/env python

from setuptools import setup

setup(
    name="jointab",
    version="0.0.1",
    description="Join data using shared columns between two tabs",
    author="Adam Hooper",
    author_email="adam@adamhooper.com",
    url="https://github.com/CJWorkbench/jointab",
    packages=[""],
    py_modules=["jointab"],
    install_requires=["pandas==0.25.0", "cjwmodule>=1.4.0"],
)
