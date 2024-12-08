// background.js
let socket;
let reconnectInterval = 5000; // 5 seconds
let ports = []; // Store connected ports

// Handle port connections
chrome.runtime.onConnect.addListener(function (port) {
  ports.push(port);
  console.log("Port connected:", port.name);

  port.onDisconnect.addListener(function () {
    ports = ports.filter((p) => p !== port);
    console.log("Port disconnected:", port.name);
  });
});

function connectWebSocket() {
  socket = new WebSocket("ws://localhost:5500/ws");

  socket.onopen = function () {
    console.log("WebSocket connection established");
  };

  socket.onmessage = function (event) {
    const message = JSON.parse(event.data);
    console.log("WebSocket message:", message);
    handleWebSocketMessage(message);
  };

  socket.onclose = function (event) {
    console.log(
      `WebSocket closed: ${event.code}. Reconnecting in ${
        reconnectInterval / 1000
      }s...`
    );
    setTimeout(connectWebSocket, reconnectInterval);
  };

  socket.onerror = function (error) {
    console.error("WebSocket error:", error);
    socket.close();
  };
}

function handleWebSocketMessage(message) {
  // Handle messages from the server
  if (
    message.type === "download_update" ||
    message.type === "download_started" ||
    message.type === "download_completed" ||
    message.type === "download_failed" ||
    message.type === "current_downloads"
  ) {
    broadcastDownloadUpdate(message);
  }
}

// Send updates to popup/content scripts
function broadcastDownloadUpdate(update) {
  // Send to all connected ports
  ports.forEach((port) => {
    try {
      port.postMessage(update);
    } catch (error) {
      console.error("Failed to send message:", error);
    }
  });
}

connectWebSocket();

// Existing download interception code
chrome.downloads.onCreated.addListener(async function (downloadItem) {
  try {
    // Cancel Chrome's download
    chrome.downloads.cancel(downloadItem.id);
    console.log({ downloadItem });
    const url = downloadItem.finalUrl || downloadItem.url;

    // Get headers using Fetch API
    const getHeaders = async () => {
      try {
        const response = await fetch(url, {
          method: "HEAD",
          mode: "no-cors",
          credentials: "include",
        });

        return {
          "content-type": response.headers.get("content-type"),
          "content-length": response.headers.get("content-length"),
          "content-disposition": response.headers.get("content-disposition"),
        };
      } catch (error) {
        console.warn("Failed to fetch headers, using fallback values");
        return {};
      }
    };

    // Get headers with retry
    let headers = {};
    for (let i = 0; i < 3; i++) {
      try {
        headers = await getHeaders();
        break;
      } catch (error) {
        if (i === 2) throw error;
        await new Promise((resolve) => setTimeout(resolve, 1000 * (i + 1)));
      }
    }
    const file_name =
      downloadItem.filename || new URL(url).pathname.split("/").pop();
    const file_extension = file_name.split(".").pop();

    const fileDetails = {
      url: url,
      final_url: downloadItem.finalUrl,
      filename:
        downloadItem.filename ||
        new URL(downloadItem.finalUrl).pathname.split("/").pop(),
      fileType: headers["content-type"] || "application/octet-stream",
      fileSize: headers["content-length"] || downloadItem.fileSize || 0,
      referrer: downloadItem.referrer,
      file_extension: file_extension,
    };

    // Parse filename from Content-Disposition if available
    if (headers["content-disposition"]) {
      const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(
        headers["content-disposition"]
      );
      if (matches && matches[1]) {
        fileDetails.filename = matches[1].replace(/['"]/g, "");
      }
    }

    console.log("Download details:", fileDetails);

    // Send to EDM server
    await fetch("http://localhost:5500/download", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(fileDetails),
    });
  } catch (error) {
    console.error("Error:", error);
    // Optionally resume original download on error
    chrome.downloads.resume(downloadItem.id);
  }
});

// Listen for messages from content scripts or popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "getDownloadStatus") {
    // Forward request to WebSocket server
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "getStatus" }));
    }
  } else if (message.type === "pauseDownload") {
    socket.send(
      JSON.stringify({
        type: "pauseDownload",
        downloadId: message.downloadId,
      })
    );
  } else if (message.type === "resumeDownload") {
    socket.send(
      JSON.stringify({
        type: "resumeDownload",
        downloadId: message.downloadId,
      })
    );
  } else if (message.type === "cancelDownload") {
    socket.send(
      JSON.stringify({
        type: "cancelDownload",
        downloadId: message.downloadId,
      })
    );
  }
});
