#!/bin/bash

# ==============================================================================
# Remote Play Enabler
# A script to link non-Steam games to Steam Remote Play Together via RetroArch.
# ==============================================================================

SETTINGS_FILE="settings.txt"
LOG_FILE="log.txt"

# Terminal Colors for visual flair
CYAN='\033[0;36m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# --- Helper Functions ---

# Log events with timestamps
log() {
    local message="$1"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $message" >> "$LOG_FILE"
}

# Expand tilde (~) to full home directory path
expand_path() {
    local path="$1"
    path="${path/#\~/$HOME}"
    echo "$path"
}

# Safely read a setting from settings.txt
get_setting() {
    local key="$1"
    if [ -f "$SETTINGS_FILE" ]; then
        grep "^${key}=" "$SETTINGS_FILE" | cut -d'=' -f2- | sed 's/^"\(.*\)"$/\1/'
    fi
}

# Safely save a setting to settings.txt
set_setting() {
    local key="$1"
    local value="$2"
    if grep -q "^${key}=" "$SETTINGS_FILE" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=\"${value}\"|" "$SETTINGS_FILE"
    else
        echo "${key}=\"${value}\"" >> "$SETTINGS_FILE"
    fi
}

# Add a game to the history (if not already present)
save_game_to_history() {
    local name="$1"
    local path="$2"
    local exe="$3"
    # Format: GAME|Name|Path|Exe
    local entry="GAME|${name}|${path}|${exe}"
    if ! grep -q -F "$entry" "$SETTINGS_FILE" 2>/dev/null; then
        echo "$entry" >> "$SETTINGS_FILE"
        log "Saved new game to history: $name"
    fi
}

# --- Core Mechanics ---

# Initialize files and start a new log session
init() {
    if [ ! -f "$SETTINGS_FILE" ]; then
        touch "$SETTINGS_FILE"
        log "Created new settings.txt file."
    fi
    
    # Add a paragraph break in the log for a new run
    echo -e "\n--------------------------------------------------" >> "$LOG_FILE"
    log "Session started."
}

# Clean up existing symlinks safely
cleanup_symlinks() {
    local ra_path=$(get_setting "RETROARCH_PATH")
    local active_path=$(get_setting "ACTIVE_GAME_PATH")

    if [ -n "$active_path" ] && [ -d "$active_path" ]; then
        log "Starting symlink cleanup for active game path: $active_path"
        for item in "$active_path"/*; do
            base_item=$(basename "$item")
            if [ -L "$ra_path/$base_item" ]; then
                rm "$ra_path/$base_item"
                log "Removed symlink: $base_item"
            fi
        done
    fi

    # Always clean up retroarch.exe and retroarch_Data symlinks to be safe
    if [ -L "$ra_path/retroarch.exe" ]; then
        rm "$ra_path/retroarch.exe"
        log "Removed symlink: retroarch.exe"
    fi
    if [ -L "$ra_path/retroarch_Data" ]; then
        rm "$ra_path/retroarch_Data"
        log "Removed symlink: retroarch_Data"
    fi

    set_setting "ACTIVE_GAME" ""
    set_setting "ACTIVE_GAME_PATH" ""
    log "Cleanup complete."
}

# Create symlinks from game to RetroArch
apply_symlinks() {
    local game_name="$1"
    local game_path="$2"
    local game_exe="$3"
    local ra_path=$(get_setting "RETROARCH_PATH")

    log "Applying symlinks for $game_name..."
    
    for item in "$game_path"/*; do
        base_item=$(basename "$item")
        
        # If it's the executable, link it as retroarch.exe
        if [ "$base_item" == "$game_exe" ]; then
            ln -sf "$item" "$ra_path/retroarch.exe"
            log "Symlinked executable '$base_item' -> 'retroarch.exe'"
        else
            ln -sf "$item" "$ra_path/$base_item"
            log "Symlinked item: $base_item"
        fi
    done

    set_setting "ACTIVE_GAME" "$game_name"
    set_setting "ACTIVE_GAME_PATH" "$game_path"
    
    echo -e "\n${GREEN}✔ Success! $game_name has been linked to RetroArch.${NC}"
    log "Successfully linked $game_name."
}

# Ask for new game details
setup_new_game() {
    echo -e "\n${CYAN}--- Set Up a New Game ---${NC}"
    
    read -e -p "Enter the name of the game: " game_name
    
    read -e -p "Enter the full path to the game folder: " raw_game_path
    game_path=$(expand_path "$raw_game_path")
    
    if [ ! -d "$game_path" ]; then
        echo -e "${RED}Error: Directory does not exist.${NC}"
        log "Failed setup: Directory $game_path not found."
        return
    fi
    
    read -e -p "Enter the exact name of the executable (e.g., game.exe): " game_exe
    
    if [ ! -f "$game_path/$game_exe" ]; then
        echo -e "${RED}Error: Executable '$game_exe' not found in that folder.${NC}"
        log "Failed setup: Executable $game_exe not found in $game_path."
        return
    fi

    cleanup_symlinks
    apply_symlinks "$game_name" "$game_path" "$game_exe"
    save_game_to_history "$game_name" "$game_path" "$game_exe"
}

# Restore a game from history
restore_game() {
    echo -e "\n${CYAN}--- Restore a Saved Game ---${NC}"
    
    # Read saved games into an array
    mapfile -t saved_games < <(grep "^GAME|" "$SETTINGS_FILE")
    
    if [ ${#saved_games[@]} -eq 0 ]; then
        echo -e "${YELLOW}No games found in history.${NC}"
        return
    fi

    echo "Select a game to link:"
    for i in "${!saved_games[@]}"; do
        name=$(echo "${saved_games[$i]}" | cut -d'|' -f2)
        echo "$((i+1)). $name"
    done
    echo "0. Cancel"

    read -p "Choose an option: " choice
    if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -gt 0 ] && [ "$choice" -le "${#saved_games[@]}" ]; index=$((choice-1)); then
        local selected="${saved_games[$index]}"
        local name=$(echo "$selected" | cut -d'|' -f2)
        local path=$(echo "$selected" | cut -d'|' -f3)
        local exe=$(echo "$selected" | cut -d'|' -f4)

        if [ ! -d "$path" ]; then
            echo -e "${RED}Error: Saved path $path no longer exists.${NC}"
            return
        fi

        cleanup_symlinks
        apply_symlinks "$name" "$path" "$exe"
    else
        echo "Canceled."
    fi
}

# Delete a game from history
delete_saved_game() {
    echo -e "\n${CYAN}--- Delete a Game from History ---${NC}"
    
    mapfile -t saved_games < <(grep "^GAME|" "$SETTINGS_FILE")
    
    if [ ${#saved_games[@]} -eq 0 ]; then
        echo -e "${YELLOW}No games found in history.${NC}"
        return
    fi

    echo "Select a game to permanently remove from settings.txt:"
    for i in "${!saved_games[@]}"; do
        name=$(echo "${saved_games[$i]}" | cut -d'|' -f2)
        echo "$((i+1)). $name"
    done
    echo "0. Cancel"

    read -p "Choose an option: " choice
    if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -gt 0 ] && [ "$choice" -le "${#saved_games[@]}" ]; index=$((choice-1)); then
        local selected="${saved_games[$index]}"
        local name=$(echo "$selected" | cut -d'|' -f2)
        
        sed -i "\|$(echo "$selected" | sed 's/[][\\/*+.^$]/\\&/g')|d" "$SETTINGS_FILE"
        echo -e "${GREEN}✔ $name removed from history.${NC}"
        log "Removed $name from history."
    else
        echo "Canceled."
    fi
}

# Fixes Menu
fixes_menu() {
    echo -e "\n${CYAN}--- Fixes ---${NC}"
    echo "1. Fix: \"There should be 'retroarch_Data' folder next to the executable\""
    echo "0. Back to Main Menu"
    
    read -p "Select an option: " fix_choice
    
    case $fix_choice in
        1)
            fix_unity_data_folder
            ;;
        0)
            return
            ;;
        *)
            echo -e "${RED}Invalid option.${NC}"
            ;;
    esac
}

# Logic to fix the Unity *_Data folder issue
fix_unity_data_folder() {
    local ra_path=$(get_setting "RETROARCH_PATH")
    if [ -z "$ra_path" ]; then
        echo -e "${RED}RetroArch path not configured yet. Set up a game first.${NC}"
        return
    fi

    log "Initiated Fix: Searching for *_Data folder to rename."
    echo -e "\n${YELLOW}Scanning for *_Data symlinks in RetroArch folder...${NC}"
    
    local found_folder=""
    local match_count=0

    # Look for directories or symlinks to directories ending in _Data
    for item in "$ra_path"/*_Data; do
        if [ -d "$item" ] || [ -L "$item" ]; then
            local base_name=$(basename "$item")
            # Ignore if it's literally "*_Data" (no matches) or already fixed
            if [ "$base_name" != "*_Data" ] && [ "$base_name" != "retroarch_Data" ]; then
                found_folder="$base_name"
                match_count=$((match_count + 1))
            fi
        fi
    done

    if [ "$match_count" -eq 1 ]; then
        echo "Detected data folder: $found_folder"
        log "Automatically found data folder: $found_folder"
        
        mv "$ra_path/$found_folder" "$ra_path/retroarch_Data"
        echo -e "${GREEN}✔ Successfully renamed '$found_folder' to 'retroarch_Data'.${NC}"
        log "Renamed symlink $found_folder to retroarch_Data."
    else
        echo -e "${YELLOW}Could not automatically detect a single game Data folder.${NC}"
        log "Automatic detection failed. Match count: $match_count."
        
        read -p "Please enter the exact name of the Data folder manually (e.g., GameName_Data): " manual_folder
        
        if [ -L "$ra_path/$manual_folder" ] || [ -d "$ra_path/$manual_folder" ]; then
            mv "$ra_path/$manual_folder" "$ra_path/retroarch_Data"
            echo -e "${GREEN}✔ Successfully renamed '$manual_folder' to 'retroarch_Data'.${NC}"
            log "Manually renamed symlink $manual_folder to retroarch_Data."
        else
            echo -e "${RED}Error: Folder '$manual_folder' not found in RetroArch directory.${NC}"
            log "Manual fix failed: Folder '$manual_folder' not found."
        fi
    fi
}

# Offer to close the terminal gracefully
prompt_exit() {
    echo -e "\nDo you want to close this script? (y/n)"
    read -n 1 -r ans
    echo ""
    if [[ $ans =~ ^[Yy]$ ]]; then
        log "Session ended by user."
        echo "Goodbye!"
        exit 0
    fi
}

# --- Main Flow ---

init

# Screen Header
clear
echo -e "${CYAN}=================================================${NC}"
echo -e "${GREEN}             🎮 Remote Play Enabler 🎮           ${NC}"
echo -e "${CYAN}=================================================${NC}"
echo "This tool links your non-Steam PC games with Steam"
echo "Remote Play Together by weaving symlink magic into"
echo "your RetroArch installation directory."
echo -e "${CYAN}=================================================${NC}\n"

# First Run / RetroArch Path Check
RA_PATH=$(get_setting "RETROARCH_PATH")

if [ -z "$RA_PATH" ] || [ ! -d "$RA_PATH" ]; then
    log "First run detected. Prompting for RetroArch path."
    echo -e "${YELLOW}⚠️  IMPORTANT FIRST STEP ⚠️${NC}"
    echo "1. Ensure RetroArch is installed via Steam."
    echo "2. Go to RetroArch Properties -> Compatibility."
    echo -e "3. Force the use of ${YELLOW}'Proton Experimental'${NC}.\n"
    
    while true; do
        read -e -p "Enter the full path to your Steam RetroArch folder: " raw_ra_path
        RA_PATH=$(expand_path "$raw_ra_path")
        
        if [ -d "$RA_PATH" ]; then
            echo -e "\n${RED}================== WARNING ==================${NC}"
            echo -e "${RED}ALL files and folders inside your RetroArch"
            echo -e "directory will be DELETED permanently to"
            echo -e "prepare the environment for symlinking.${NC}"
            echo -e "${RED}=============================================${NC}"
            read -p "Are you absolutely sure you want to proceed? (y/n): " confirm
            
            if [[ "$confirm" =~ ^[Yy]$ ]]; then
                log "User confirmed deletion of RetroArch directory contents."
                echo -e "${YELLOW}Deleting contents of $RA_PATH...${NC}"
                
                # Delete all contents inside the folder, hiding errors for unremovable root files if any
                rm -rf "$RA_PATH"/* 2>/dev/null
                
                set_setting "RETROARCH_PATH" "$RA_PATH"
                log "RetroArch path set to: $RA_PATH and contents deleted."
                echo -e "${GREEN}✔ RetroArch path saved and folder cleared!${NC}\n"
                break
            else
                log "User canceled directory deletion."
                echo -e "${YELLOW}Operation canceled. Please provide a different path or exit.${NC}\n"
            fi
        else
            echo -e "${RED}Path not found. Please try again.${NC}"
        fi
    done
fi

# Main Menu Loop
while true; do
    ACTIVE_GAME=$(get_setting "ACTIVE_GAME")
    
    echo -e "\n${CYAN}--- Main Menu ---${NC}"
    if [ -n "$ACTIVE_GAME" ]; then
        echo -e "Current Active Game: ${GREEN}[ $ACTIVE_GAME ]${NC}"
    else
        echo -e "Current Active Game: ${YELLOW}[ None ]${NC}"
    fi
    echo ""
    echo "1. Set up a new game"
    echo "2. Restore a previously saved game"
    echo "3. Clear current active symlinks"
    echo "4. Delete a game from history"
    echo "5. Fixes"
    echo "6. Exit"
    
    read -p "Select an option [1-6]: " menu_choice
    
    case $menu_choice in
        1)
            setup_new_game
            prompt_exit
            ;;
        2)
            restore_game
            prompt_exit
            ;;
        3)
            if [ -n "$ACTIVE_GAME" ]; then
                cleanup_symlinks
                echo -e "${GREEN}✔ Symlinks cleared.${NC}"
            else
                echo -e "${YELLOW}No active game to clear.${NC}"
            fi
            ;;
        4)
            delete_saved_game
            ;;
        5)
            fixes_menu
            ;;
        6)
            log "Session ended."
            echo "Goodbye!"
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid option.${NC}"
            ;;
    esac
done
