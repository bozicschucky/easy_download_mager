// popup.js
let port;
const downloadList = {
  downloading: {},
  completed: {},
  failed: {},
};

function formatFileSize(bytes) {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}
function addDownloadToList(download, status) {
  console.log("Adding download to list:", download, status);
  const listElement = document.getElementById(`${status}-list`);
  if (!listElement) {
    console.error("List element not found:", status);
    return;
  }

  const row = document.createElement("tr");
  row.id = `download-${download.id}`;

  const nameCell = document.createElement("td");
  nameCell.className = "file-name";
  nameCell.textContent = download.filename || "Unknown";

  const sizeCell = document.createElement("td");
  sizeCell.textContent = formatFileSize(download.fileSize || 0);

  const typeCell = document.createElement("td");
  typeCell.textContent = download.fileType || "Unknown";

  const lastCell = document.createElement("td");
  if (status === "downloading") {
    lastCell.textContent = `${download.progress || 0}%`;
  } else if (status === "completed") {
    lastCell.textContent = download.outputDir || "Downloads";
  } else if (status === "failed") {
    lastCell.textContent = download.error || "Unknown error";
  }

  row.appendChild(nameCell);
  row.appendChild(sizeCell);
  row.appendChild(typeCell);
  row.appendChild(lastCell);

  listElement.appendChild(row);

  downloadList[status][download.id] = {
    row,
    lastCell,
    download,
  };

  saveDownloadHistory();
}

function updateDownloadProgress(download) {
  const downloadUI = downloadList.downloading[download.id];
  if (downloadUI) {
    downloadUI.lastCell.textContent = `${download.progress}%`;
  } else {
    addDownloadToList(download, "downloading");
  }
}

function markDownloadCompleted(download) {
  const downloadUI = downloadList.downloading[download.id];
  if (downloadUI) {
    delete downloadList.downloading[download.id];
    downloadUI.row.remove();
    addDownloadToList(download, "completed");
  }
}

function handleDownloadFailure(download, error) {
  const downloadUI = downloadList.downloading[download.id];
  if (downloadUI) {
    delete downloadList.downloading[download.id];
    downloadUI.row.remove();
    download.error = error;
    addDownloadToList(download, "failed");
  }
}

function loadCurrentDownloads(downloads) {
  downloads.forEach((download) => {
    if (download.status === "downloading") {
      addDownloadToList(download, "downloading");
      updateDownloadProgress(download);
    } else if (download.status === "completed") {
      addDownloadToList(download, "completed");
    } else if (download.status === "failed") {
      addDownloadToList(download, "failed");
    }
  });
}

function saveDownloadHistory() {
  const history = {
    completed: Object.values(downloadList.completed).map(
      (item) => item.download
    ),
    failed: Object.values(downloadList.failed).map((item) => item.download),
  };
  chrome.storage.local.set({ downloadHistory: history });
}

function loadDownloadHistory() {
  chrome.storage.local.get(["downloadHistory"], (result) => {
    const history = result.downloadHistory || { completed: [], failed: [] };
    history.completed.forEach((download) =>
      addDownloadToList(download, "completed")
    );
    history.failed.forEach((download) => addDownloadToList(download, "failed"));
  });
}

function handleWebSocketMessage(message) {
  try {
    console.log("Processing message:", message);

    // Get filename from download_id by removing timestamp
    const filename = message.download_id
      ? message.download_id.split("_")[0]
      : "";

    const download = {
      id: message.download_id,
      filename: filename,
      progress: message.progress || 0,
      status: message.status,
      // Add default values for table display
      fileSize: message.fileSize || 0,
      fileType: message.fileType || "Unknown",
      outputDir: message.outputDir || "Downloads",
      error: message.error,
    };

    switch (message.type) {
      case "download_added":
        console.log("Adding new download:", download);
        addDownloadToList(download, "downloading");
        break;

      case "download_update":
        console.log("Updating download:", download);
        if (message.status === "downloading") {
          if (!downloadList.downloading[download.id]) {
            addDownloadToList(download, "downloading");
          }
          updateDownloadProgress(download);
        } else if (message.status === "completed") {
          markDownloadCompleted(download);
        } else if (message.status === "failed") {
          handleDownloadFailure(download, message.error);
        }
        break;

      case "current_downloads":
        console.log("Loading current downloads:", message.downloads);
        loadCurrentDownloads(message.downloads);
        break;
    }
  } catch (error) {
    console.error("Error handling message:", error, message);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadDownloadHistory();

  port = chrome.runtime.connect({ name: "popup" });

  port.onMessage.addListener((message) => {
    console.log("Received message:", message);
    handleWebSocketMessage(message);
  });

  port.onDisconnect.addListener(() => {
    console.log("Disconnected from background script");
    port = null;
  });

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document
        .querySelectorAll(".tab")
        .forEach((t) => t.classList.remove("active"));
      document
        .querySelectorAll(".tab-content")
        .forEach((tc) => tc.classList.remove("active"));
      tab.classList.add("active");
      document
        .getElementById(tab.getAttribute("data-tab"))
        .classList.add("active");
    });
  });
});
