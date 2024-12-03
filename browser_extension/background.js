chrome.downloads.onCreated.addListener(async function (downloadItem) {
  // Cancel Chrome's download
  chrome.downloads.cancel(downloadItem.id);

  // Erase from download history
  chrome.downloads.erase({ id: downloadItem.id });

  // Send to Python server
  try {
    const response = await fetch("http://localhost:5500/download", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        url: downloadItem.url,
        filename: downloadItem.filename,
      }),
    });

    if (response.ok) {
      console.log("Download request sent to EDM");
    } else {
      console.error("Failed to send download request");
    }
  } catch (error) {
    console.error("Error:", error);
  }
});
