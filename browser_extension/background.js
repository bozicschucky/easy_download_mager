// Intercept download events in Chrome
chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
  const downloadUrl = item.url;
  const fileName = item.filename;

  // Send the intercepted URL to the desktop application
  const ws = new WebSocket("ws://localhost:8765"); // Connect to desktop app
  ws.onopen = () => {
    ws.send(JSON.stringify({ url: downloadUrl, name: fileName })); // Send URL and file metadata
    ws.close();
  };

  // Cancel the download in the browser
  chrome.downloads.cancel(item.id);
});
