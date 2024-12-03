from setuptools import setup, find_packages

setup(
    name="easy_download_manager",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        'aiohttp',
        'rich',
        'aiofiles',
        'asyncio',
        'humanize',
    ]
)
