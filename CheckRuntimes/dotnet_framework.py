try:
    import winreg as reg

    def get_dotnet_versions():
        try:
            net_versions = []
            path = r"SOFTWARE\Microsoft\NET Framework Setup\NDP"

            def check_versions(key):
                i = 0
                while True:
                    try:
                        subkey_name = reg.EnumKey(key, i)
                        subkey_path = f"{path}\\{subkey_name}"
                        with reg.OpenKey(reg.HKEY_LOCAL_MACHINE, subkey_path) as subkey:
                            try:
                                version, _ = reg.QueryValueEx(subkey, "Version")
                                net_versions.append((subkey_name, version))
                            except FileNotFoundError:
                                pass
                        i += 1
                    except OSError:
                        break

            with reg.OpenKey(reg.HKEY_LOCAL_MACHINE, path) as main_key:
                check_versions(main_key)

            return net_versions

        except OSError as e:
            return f"Error accessing registry: {e}"

except ImportError:
    def get_dotnet_versions():
        return "winreg module not available on this platform"