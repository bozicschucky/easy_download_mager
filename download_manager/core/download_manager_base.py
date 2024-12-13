# download_manager_base.py
from abc import ABC, abstractmethod


class DownloadManagerBase(ABC):
    @abstractmethod
    async def add_download(self, url, output_file, output_dir):
        pass

    @abstractmethod
    async def run(self):
        pass
