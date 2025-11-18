from setuptools import setup, find_packages

setup(
    name="sports-betting-edge",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "aiohttp>=3.9.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "sqlalchemy>=2.0.0",
        "streamlit>=1.28.0",
        "plotly>=5.18.0",
        "python-telegram-bot>=20.0",
        "beautifulsoup4>=4.12.0",
        "pyyaml>=6.0",
        "scipy>=1.11.0",
    ],
    python_requires=">=3.9",
    author="Sports Betting Edge Toolkit",
    description="Comprehensive sports betting analytics suite",
    entry_points={
        "console_scripts": [
            "betting-edge=run:main",
        ],
    },
)
