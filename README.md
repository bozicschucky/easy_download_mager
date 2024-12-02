# Easy Download Manager (EDM)

Easy Download Manager is a Python-based tool for downloading large files efficiently by splitting them into smaller chunks and downloading them concurrently. It includes features such as retrying failed chunks, dynamic batching, and progress tracking.

## Features

- Concurrent chunk downloads for faster file retrieval
- Dynamic batching to optimize memory usage
- Retry logic for failed chunks with exponential backoff
- Fallback to single chunk download if all retries fail
- Progress tracking with detailed status updates

## Requirements

- Python 3.7+
- `aiohttp` library
- `rich` library
- `humanize` library

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/yourusername/easy_download_manager.git
    cd easy_download_manager
    ```

2. Create a virtual environment and activate it:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
    ```

3. Install the required packages:
    ```bash
    pip install aiohttp rich humanize
    ```

## Usage

To download a file, run the `cli_gui.py` script with the URL of the file and the desired output file name:

```bash
python cli_gui.py <url> <output_file>


python cli_gui.py https://example.com/largefile.zip largefile.zip

Project Structure
- cli_gui.py: Command-line interface for the download manager.
- utils.py: Core logic for downloading files, handling retries, and merging chunks.

# Example Usage
```bash

import argparse
import asyncio
from rich.progress import Progress
from utils import download_file

def main():
    parser = argparse.ArgumentParser(
        description="Download a file with progress display."
    )
    parser.add_argument("url", help="The URL of the file to download")
    parser.add_argument("output_file", help="The output file name")

    args = parser.parse_args()

    with Progress() as progress:
        asyncio.run(download_file(args.url, args.output_file, progress))

if __name__ == "__main__":
    main()

```

Contributing
Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

License
This project is licensed under the MIT License. See the LICENSE file for details.
