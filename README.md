# FilmCraft YouTube Export Panel (Windows)

A Windows desktop companion for downloading and trimming YouTube videos you own or are authorized to use, then importing the resulting media into the currently running FilmCraft project.

## Important compatibility note

The `storytold/filmcraft` repository currently documents **no third-party plugin system**. This project is therefore not an in-process/native FilmCraft plugin. It is a desktop companion that uses FilmCraft's documented `filmcraft-cli --bridge ... import <file>` workflow to import downloaded media into the active project. It does not automatically place the media on the timeline.

Repository references:
- https://github.com/storytold/filmcraft
- https://github.com/storytold/filmcraft/blob/main/docs/control-protocol.md
- https://github.com/storytold/filmcraft/blob/main/docs/agents.md

## Features

- Real metadata lookup for a pasted YouTube URL
- Start/end trim range (`MM:SS` or `HH:MM:SS`)
- MP4, WebM, and MP3 export choices
- Maximum resolution selection
- Real download job progress and errors from `yt-dlp`
- Export file link
- **Import into active FilmCraft project** using the FilmCraft CLI control bridge

## Requirements

- Windows 10/11 x64
- Node.js 20 or newer
- Python 3.11 or newer
- FFmpeg installed and available on `PATH`
- FilmCraft installed with both `filmcraft.exe` and `filmcraft-cli.exe`
- Internet access for metadata and downloads

Install Python dependencies and Electron once:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
npm install
```

## Recommended launch (authenticated FilmCraft bridge)

Close any already-running FilmCraft instance first. From this project directory, run PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\Start-FilmCraft-Downloader.ps1
```

The script generates a fresh random 64-character token, sets it only in the current process environment, starts FilmCraft with `--control 9876`, then starts the companion. The companion passes that token to `filmcraft-cli`; do not paste the token into source files, logs, or shared configuration.

If FilmCraft is installed elsewhere:

```powershell
.\scripts\Start-FilmCraft-Downloader.ps1 `
  -FilmCraftExe 'D:\Apps\FilmCraft\filmcraft.exe' `
  -FilmCraftCli 'D:\Apps\FilmCraft\filmcraft-cli.exe'
```

Keep the PowerShell window open while using the panel. Do not expose the control port to the network; FilmCraft's control protocol is intended for loopback use.

## Use

1. Paste a YouTube URL and select **Search**.
2. Optionally enable trim and set the start/end times.
3. Select output format and maximum resolution.
4. Select **Download / Export** and wait for progress to reach 100%.
5. Select **Import into active FilmCraft project**.
6. Check FilmCraft's project/media bin for the imported file. Timeline placement is a separate editing action.

The download output directory defaults to `%USERPROFILE%\Videos\FilmCraftExports`. Electron prefers the project `.venv` Python automatically, so it uses the environment where you installed `requirements.txt`.

## Run the panel without the launcher

```powershell
.\.venv\Scripts\Activate.ps1
$env:FILMCRAFT_CLI_PATH = 'C:\Program Files\FilmCraft\filmcraft-cli.exe'
npm start
```

This mode can download/export, but FilmCraft import requires a running FilmCraft instance started with `--control`, and the companion process must inherit the same `FILMCRAFT_CONTROL_TOKEN` as that instance. The launcher configures this safely for you.

## Build an installer

```powershell
npm run dist:win
```

Note: the current Electron packaging configuration is a developer build, not a fully self-contained installer. Python, its dependencies, and FFmpeg must be installed on the target PC. Verify packaging on a clean Windows machine before distributing it.

## Troubleshooting

- **Panel says local export service could not start:** ensure `.venv\Scripts\python.exe` exists and run `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` from the project folder, then restart. The desktop app prefers the project virtual environment automatically.
- **Metadata/download fails:** update `yt-dlp` (`.\.venv\Scripts\python.exe -m pip install -U yt-dlp`), check network access, and verify you have permission to download the video.
- **Trim/MP3/merge fails:** verify `ffmpeg -version` and `ffprobe -version` work in the same PowerShell session.
- **FilmCraft import says CLI missing:** pass the actual path to `filmcraft-cli.exe` to the launcher.
- **Authentication/control error:** close FilmCraft and relaunch using the PowerShell script. Do not reuse a stale token from another session.
- **Port 9876 in use:** close the other FilmCraft control-enabled instance or choose a different port with `-ControlPort`; the launcher uses the same port for its bridge configuration.

## Rights and safety

Use only videos you own or are authorized to download. Follow YouTube's terms and applicable copyright rules. This tool does not bypass DRM or access controls.
