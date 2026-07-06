# Remote Play Enabler

## Description
Remote Play Enabler is a Linux bash script designed to seamlessly integrate non-Steam games with Steam's Remote Play Together feature. By leveraging RetroArch's Remote Play capabilities, this script automates the process of creating symlinks from your non-Steam game directory directly into the Steam RetroArch folder. It temporarily masks your game's executable as retroarch.exe, allowing Steam to broadcast it to your friends.

The script features a safe symlink cleanup process, a history tracker to easily switch between previously configured games, and a detailed logging system to keep track of all background actions.

## Requirements

Before running the script, ensure your system meets the following criteria:

1. A Linux-based operating system.
2. Bash shell environment.
3. Steam installed and running.
4. RetroArch installed via Steam.
5. Proton Experimental enabled for RetroArch. (To do this: Right-click RetroArch in your Steam Library > Properties > Compatibility > Force the use of a specific Steam Play compatibility tool > Select "Proton Experimental").

## How to Use

1. Download the Script:
   - Save the remote_play_enabler.sh file to a directory of your choice.

2. Make it Executable:
   - Open your terminal, navigate to the directory where you saved the file, and run the following command to grant execution permissions:

```
chmod +x remote_play_enabler.sh
```

3. Run the Script:
   - Execute the script using the terminal:

```
./remote_play_enabler.sh
```

4. First Run Setup:
   - The script will ask for the full path to your Steam RetroArch folder. (You can use ~ for your home folder and the TAB key to auto-complete paths).
   - This path will be saved in a settings.txt file so you only have to do this once.

5. Linking a Game:
   - Select the option to set up a new game.
   - Provide the game's name, the full path to its folder, and the exact name of its executable file (e.g., game.exe).
   - The script will generate the necessary symlinks.
   - You can now launch RetroArch on Steam, and it will launch your non-Steam game with Remote Play Together enabled.

6. Managing Games:
   - The script automatically saves configured games to your history.
   - Relaunch the script to swap out the active game, restore a previous configuration, clear current symlinks, or permanently delete a game from your history.

7. Fixing problems:
   - The script have an option to fix possible problems you could have with this method.
   - As i keep using this script and find new problems and fixes, i'll be adding those fixes to this option so the script can handle it for you.

## Credits and Disclaimer

Concept and Logic: Created and directed by me.
Development Assistance: The code was generated and refined with the assistance of an AI (Google Gemini).
