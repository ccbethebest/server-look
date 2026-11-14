# Server Look — quick help

## Connect to servers
Use the Servers icon to open connection settings or add a server tab. Enter an address, SSH port and username, then choose public-key or password authentication. Saved connections can be selected from history. Remembered passwords are encrypted for the current Windows account; moving the app does not move these credentials.

Connect, Refresh and Disconnect apply to the current tab. The Servers menu can connect all open tabs, connect all recent servers, disconnect all servers, or close tabs. Connection status shows progress and failure reasons. Verify an unfamiliar SSH host fingerprint before trusting it.

## Tasks, accelerators and hardware
Tasks and Containers show startup time, PID, parent PID, command and container details. Select a row for details. Task relationships show an operating-system process snapshot, not application-level dependencies. Ending a task or container requires confirmation. An expired selection never silently selects another task.

Check availability checks all connected servers. Green means no accelerator cards are busy, yellow means some are busy, and red means all are busy. Hover over a server tab to see used/total cards; selecting the tab clears its color. NVIDIA GPUs and Ascend NPUs are supported where their management tools are available. A failed check is reported separately from an idle result.

Hardware shows CPU architecture, memory and accelerator information. Disks & mounts shows local and mounted storage capacity and usage. NPU / GPU status preserves the original device-tool output.

## Browse and transfer files
Double-click a folder to enter it inside the app. Use Up, the path field or the folder tree to navigate; local drives can be selected. Open window opens the local folder in Windows Explorer. Remote browsing reuses the SSH connection.

Right-click files or a folder's empty area for new folder, copy, paste, rename, delete, compress or extract. Select multiple items with Ctrl/Shift; Ctrl+A selects all. Delete is permanent and asks for confirmation. Remote read-only mode disables remote modifications, uploads and deletion; downloads and browsing remain available.

Drag between the app's local and remote panes to transfer into the displayed destination folder. Drag local Explorer files into the remote pane to upload. Remote-to-Explorer dragging downloads data before handing it to Explorer; if you released the mouse while waiting, drag again when ready. In-app transfers use the destination pane directly. Transfer status reports completion, cancellation or errors.

## Search
Choose this computer or an open server, then select a folder visually or enter its path. Contains matches a substring; Exact matches the whole name; Wildcard accepts * and ?; Approximate matches characters in order; Regular expression uses a regex. Case-sensitive is optional. Choose files, folders or both and whether to include subfolders.

Results appear in batches, with name, size and modification time. Click a column heading to cycle ascending, descending and original order. Folder sizes can be incomplete under scan limits. Stop cancels a scan. Double-click a result to open its location in that server's or the local file pane and select the result. Search limits prevent scans from blocking indefinitely.

## Directory mapping
Add mapping creates a row with source and destination endpoints and paths. Choose This computer or a connected server for either end. Use the visible source/destination folder buttons to browse; paths can also be edited. Local-to-server, server-to-local and server-to-server mapping are supported.

Select a row and click Map now to map the entire source folder after confirmation. Double-click a mapping to browse both sides, edit paths or drives, and map selected items from the context menu. Without Overwrite, only missing files are copied recursively. With Overwrite, source files replace matching destination files recursively; unrelated destination files are retained.

Prefer direct transfer tries server-to-server transfer first. If unavailable or slower than the configured threshold, a dialog asks whether to use the selected local relay folder. Relay transfers one file at a time and cleans temporary files as it goes; it still needs enough local space for the current file. The current transfer speed is displayed.

Right-click a mapping to save it to history or remove it from the current list. When adding a mapping, select saved entries for connected endpoints. Mapping history opens all saved entries; select one or multiple records to delete, or delete all. Deleting mapping history does not delete actual files.

## Settings and language
Choose Simplified Chinese or English, then Save and apply. Captions, menus, status messages and this help switch immediately; connections and ongoing transfers remain. The choice is saved for the next launch. Filenames, paths, commands, server identities and original device/system output retain their original text.

Settings also controls remote read-only mode, blue/black/white themes, font sizes, button size, navigation placement and window layout. Use the +/− buttons to adjust font sizes; mouse-wheel input does not change settings.

To set a shortcut, click its button and press the actual key combination. Esc cancels recording. Clear disables the shortcut. Duplicate shortcuts are rejected. File-operation shortcuts only apply in file lists. Restore defaults immediately restores language, theme, layout, sizes, read-only choice and shortcuts; saved server connections, passwords and mapping history remain.

## Installation and troubleshooting
The packaged EXE includes its runtime and application code. No Python installation or Internet connection is required for local use; connecting to servers requires network access to those servers. Remote operations need suitable permissions and supported remote commands. If an operation fails, read the displayed reason and check SSH connectivity, authentication, permissions, free space and device tools.
