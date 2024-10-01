# Check Runtimes and System Versions

This project is designed to check and report information about the operating system and various runtime environments installed on a machine, such as Java, Python, Node.js, and .NET Framework (on Windows).

## Project Structure

```plaintext
CheckRuntimes/
│
├── os_info.py
├── runtime_versions.py
├── dotnet_framework.py
├── logger_config.py
└── main.py
```

### Module Descriptions

- **`os_info.py`**: Retrieves operating system information.
- **`runtime_versions.py`**: Handles version checking and retrieval for various runtimes like Java, Python, and Node.js.
- **`dotnet_framework.py`**: Specifically deals with retrieving .NET Framework versions on Windows systems.
- **`logger_config.py`**: Configures logging, allowing for different logging levels.
- **`main.py`**: Entry point to orchestrate the retrieval and logging of system information.

## Requirements

- Python 3.6 or higher

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/bblinder/Splunk/CheckRuntimes.git

2. Navigate into the project directory:
    ```bash
    cd CheckRuntimes
    ```

## Usage

To run the script and get information about your system's versions and runtimes, execute:
```bash
python3 main.py
```

If running the script(s) isn't an option (for security reasons, etc), the same information can be obtained by referencing the below commands.


## Common Commands: Bash vs PowerShell

For users who need to run commands manually or understand the underlying operations, here are some common commands used in this project with their Bash and PowerShell equivalents:

| Operation | Bash (Unix-like systems) | PowerShell (Windows) |
|-----------|--------------------------|----------------------|
| Check Java version | `java -version` | `java -version` |
| Check Python version | `python --version` | `python --version` |
| Check Node.js version | `node --version` | `node --version` |
| Check OS version | `uname -a` | `[System.Environment]::OSVersion.Version` |
| List directory contents | `ls -l` | `Get-ChildItem` or `dir` |
| Create a directory | `mkdir -p new_folder` | `New-Item -ItemType Directory -Name new_folder` |
| Remove a file | `rm file.txt` | `Remove-Item file.txt` |
| Set an environment variable | `export VAR_NAME=value` | `$env:VAR_NAME = "value"` |
| Read an environment variable | `echo $VAR_NAME` | `$env:VAR_NAME` |
| Find a file | `find /path -name filename` | `Get-ChildItem -Path C:\ -Recurse -Filter filename` |
| Check if a file exists | `test -f filename && echo "Exists"` | `if (Test-Path filename) { "Exists" }` |
| Get current directory | `pwd` | `Get-Location` or `pwd` |
| Move/Rename a file | `mv old_name new_name` | `Move-Item -Path old_name -Destination new_name` |
| Copy a file | `cp source destination` | `Copy-Item -Path source -Destination destination` |

Note: Some commands (like checking runtime versions) may be identical in both environments, while others differ significantly.

## .NET Framework Version Check (Windows Only)

To check the installed .NET Framework versions on a Windows system, you can use the following PowerShell command:

```powershell
Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\NET Framework Setup\NDP' -Recurse | Get-ItemProperty -Name version -EA 0 | Where { $_.PSChildName -Match '^(?!S)\p{L}'} | Select PSChildName, version
```

This command is already implemented in the `dotnet_framework.py` module for Windows systems.

**Logging**

The scripts uses Python's built-in logging module to provide detailed logs at various levels (INFO, DEBUG, ERROR). You can configure the logging level in `logger_config.py`.

**Error Handling**

The scripts includes robust error handling mechanisms using try-except blocks to catch potential exceptions during subprocess execution and registry access (on Windows).

**Contributing**

If you wish to contribute to this project, please fork the repository and submit a pull request.

**Use standard Python libraries** to maintain portability and minimize dependencies.
