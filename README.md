# Remote Play Enabler

<img width="764" height="584" alt="image" src="https://github.com/user-attachments/assets/01655054-d22c-4a25-9f30-daacb746a82f" />



## Description
Remote Play Enabler is a Linux and Windows app designed to seamlessly integrate non-Steam games with Steam's Remote Play Together feature. By leveraging RetroArch's Remote Play capabilities, this app automates the process of creating symlinks from your non-Steam game directory directly into the Steam RetroArch folder. It temporarily masks your game as RetroArch, allowing Steam to broadcast it to your friends.

The app features a safe symlink cleanup process, a history tracker to easily switch between previously configured games, and a detailed logging system to keep track of all background actions.

## Requirements

- Steam.
- **RetroArch installed through Steam** (Steam AppID `1118310`).
- On Linux, the Steam RetroArch entry must be configured to run through **Proton**.

In the app's **How To** section there is an `Install RetroArch on Steam` button
that opens `steam://install/1118310` through Steam.

## How to Use

- Go to the Releases page, download the latest version of the app for your system (Linux or Windows) and open it.
- Make sure you have RetroArch installed through Steam. If not, you can click in the button "How To" and install it through there. (If you are on Linux, enable Proton on RetroArch as well).
- Click on "Choose RetroArch Folder..." and select your RetroArch folder.
- Click on "Prepare/Backup RetroArch" so the RetroArch's folder gets empty and backed up.
- Click on "Add Game..." and add any non-steam game you want to play with Remote Play through Steam.
- Select the game you want to play and click on "Enable".
- You can now start RetroArch through the button "Start Game" or through Steam. The non-steam game should open, with Steam's overlay working. Now you can invite your friends through Remote Play Together!

You can view a log of everything the app is doing in the following path:
- Linux: `~/.config/remote-play-enabler/log.txt`
- Windows: `%APPDATA%\RemotePlayEnabler\log.txt`

## Running from source

Install Python 3.11+ and then:

```bash
python -m venv .venv
```

Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Building a standalone single-file application

Builds are platform-specific: create the Windows executable on Windows and the
Linux binary on Linux. PyInstaller is not a cross-compiler.

### Windows

Open PowerShell in the source folder and run:

```powershell
.\build-windows.ps1
```

Result:

`dist\RemotePlayEnabler.exe`

### Linux

Run:

```bash
./build-linux.sh
```

Result:

`dist/RemotePlayEnabler`

Both are single-file builds and include Python, PySide6 and the other runtime
dependencies; end users do not need Python installed.

## Credits and Disclaimer

This app will NOT enable games with DRM to open without proper patching or authorization, so make sure your game opens first before adding it to this app.

AI assistance disclosure: ChatGPT was used extensively during implementation, code review and debugging. I directed the project development and manually built, tested and reviewed each milestone on real hardware.
