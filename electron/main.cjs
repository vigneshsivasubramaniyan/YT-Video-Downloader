const { app, BrowserWindow, dialog, shell } = require('electron');
const { spawn } = require('node:child_process');
const path = require('node:path');
const http = require('node:http');

const HOST = '127.0.0.1';
const PORT = 48201;
const BASE = app.getAppPath();
let backend = null;
let mainWindow = null;
let stopping = false;

function healthCheck() {
  return new Promise((resolve) => {
    const req = http.get(`http://${HOST}:${PORT}/api/health`, (res) => {
      res.resume();
      resolve(res.statusCode === 200);
    });
    req.setTimeout(700, () => { req.destroy(); resolve(false); });
    req.on('error', () => resolve(false));
  });
}

function wait(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }

async function startBackend() {
  if (await healthCheck()) return; // Reuse a helper already running on this port.

  // Prefer the project's virtual environment. `npm start` does not inherit
  // activation from a separate PowerShell session.
  const fs = require('node:fs');
  const venvPython = process.platform === 'win32'
    ? path.join(BASE, '.venv', 'Scripts', 'python.exe')
    : path.join(BASE, '.venv', 'bin', 'python');
  const python = process.env.FILMCRAFT_PYTHON ||
    (fs.existsSync(venvPython) ? venvPython : 'python');
  backend = spawn(python, ['-m', 'uvicorn', 'app:app', '--host', HOST, '--port', String(PORT)], {
    cwd: BASE,
    windowsHide: true,
    stdio: 'ignore',
    env: { ...process.env, DOWNLOAD_DIR: path.join(app.getPath('videos'), 'FilmCraftExports') }
  });
  backend.on('error', () => {});

  for (let i = 0; i < 60; i++) {
    if (await healthCheck()) return;
    if (backend.exitCode !== null) break;
    await wait(500);
  }
  throw new Error('Could not start the local service. Install Python 3.11+, then run: pip install -r requirements.txt. Install FFmpeg and ensure ffmpeg.exe is on PATH.');
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1120,
    height: 780,
    minWidth: 760,
    minHeight: 600,
    backgroundColor: '#1e1e1e',
    title: 'FilmCraft YouTube Export Panel',
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://127.0.0.1:48201/api/files/')) return { action: 'allow' };
    if (url.startsWith('https://')) shell.openExternal(url);
    return { action: 'deny' };
  });
  await mainWindow.loadURL(`http://${HOST}:${PORT}`);
}

app.whenReady().then(async () => {
  try {
    await startBackend();
    await createWindow();
  } catch (error) {
    await dialog.showMessageBox({ type: 'error', title: 'FilmCraft Export Panel', message: 'Local export service could not start', detail: error.message });
    app.quit();
  }
});

app.on('before-quit', () => {
  stopping = true;
  if (backend && backend.exitCode === null) backend.kill();
});
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
app.on('activate', async () => { if (BrowserWindow.getAllWindows().length === 0 && !stopping) await createWindow(); });
