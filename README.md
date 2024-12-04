# Easy Download Manager (EDM)

Easy Download Manager is a Python-based tool for downloading large files efficiently by splitting them into smaller chunks and downloading them concurrently. It includes features such as retrying failed chunks, dynamic batching, and progress tracking. The project also includes a Chrome extension client for intercepting downloads and a server backend to handle download requests.

## Features

- Concurrent chunk downloads for faster file retrieval
- Dynamic batching to optimize memory usage
- Retry logic for failed chunks with exponential backoff
- Fallback to single file download if all retries fail
- Progress tracking with detailed status updates using logging
- Chrome extension client for intercepting and redirecting downloads
- Server backend to handle download requests and manage downloads
- Possibility of a desktop GUI for managing downloads

## Requirements

- Python 3.7+
- `aiohttp` library
- `humanize` library

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/bozicschucky/easy_download_manager.git
    cd easy_download_manager
    ```

2. Create a virtual environment and activate it:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
    ```

3. Install the required packages:
    ```bash
    pip install aiohttp humanize
    ```

## Usage

### CLI Application

To download a file using the CLI application, run the `edm_cli.py` script with the URL of the file:

```bash
python edm_cli.py <url> <url> <url>
```

### Server Backend
To start the server backend, run the web_server.py script. The server will listen for download requests and manage downloads.

```bash
python web_server.py
```

end a POST request to the /download endpoint with the URL of the file to download:

```bash
curl -X POST -H "Content-Type: application/json" -d '{"url": "http://example.com/file.mp3"}' http://localhost:5500/download
```

### Chrome Extension Client
The Chrome extension client intercepts downloads and redirects them to the EDM server backend. To use the Chrome extension:

Load the extension in Chrome:

Open Chrome and go to chrome://extensions/
Enable Developer mode
Click "Load unpacked" and select the extension folder
Configure the extension to point to your EDM server backend.

### Desktop GUI (Future Possibility)
A desktop GUI for managing downloads is a potential future enhancement. This GUI would provide a user-friendly interface for adding, monitoring, and managing downloads.

Contributing
Contributions are welcome! Please fork the repository and submit a pull request with your changes.

### License
This project is licensed under the MIT License.

