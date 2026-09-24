from setuptools import setup, find_packages

setup(
    name="arma-layer",
    version="0.1.0",
    description="ARMA: Autonomous Reliability & Metacognitive Architecture for Coding Agents",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="ARMA Contributors",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "requests>=2.28.0",
        "numpy>=1.20.0",
        "pydantic>=1.10.0",
    ],
    entry_points={
        "console_scripts": [
            "arma=layer.cli:main",
            "arma-veto=layer.test_diff_interrogator:main_cli",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
