import { app, BrowserWindow } from "electron";

const url = process.env.MCL_GUI_URL || "http://127.0.0.1:8765/";

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1180,
    height: 760,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: "#f5f6f8",
    title: "MCL",
    autoHideMenuBar: true,
  });
  void win.loadURL(url);
}

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
