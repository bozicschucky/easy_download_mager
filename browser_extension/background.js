// background.js
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

    const fileDetails = {
      url: url,
      final_url: downloadItem.finalUrl,
      filename:
        downloadItem.filename ||
        new URL(downloadItem.finalUrl).pathname.split("/").pop(),
      fileType: headers["content-type"] || "application/octet-stream",
      fileSize: headers["content-length"] || downloadItem.fileSize || 0,
      referrer: downloadItem.referrer,
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
