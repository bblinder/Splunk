import sys
import subprocess

class RuntimeFactory:
    def __init__(self):
        self.executors = {
            'java': ['java', '-version'],
            'node': ['node', '-v'],
            'python': lambda: f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'
        }

    def get_version(self, runtime_name):
        command = self.executors.get(runtime_name)
        if callable(command):
            return command()
        elif command:
            return self.execute_command(command)
        return f'{runtime_name} not supported'

    def execute_command(self, command):
        try:
            result = subprocess.run(
                command, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, check=True
            )
            return result.stdout.decode().strip()
        except subprocess.CalledProcessError as e:
            return f'Command failed: {e}'
        except FileNotFoundError:
            return f'{command[0]} not found'
