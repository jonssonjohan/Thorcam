import time
import json
import threading
import time
import datetime

class ConfigurationManager:
    """ConfigurationManager
    
    Keeps track on program settings in configuration json file and update the program whenever
    the settings gets updated if watch_file = True. It also holds functions for get and set keys. Do not use 
    the fileWatcher thread extensively and make sure to call stop() to exit the thread.

    Parameters
    `config_file_path` : str
        Path to json file. 
    `watch_file` : bool
        If true, start a thread that watch the json configuration file. 
    `file_watcher_delay` : float
        Time between each check of configuration file. Adjust this to get the best performance.
    Returns
    any : object
        ConfigurationManager object.
    """
    def __init__(self, config_file_path: str, watch_file = False, file_watcher_delay: float = 2.0):
        self.config_file_path = config_file_path
        self.file_watcher_delay = file_watcher_delay
        self.file_change = False
        self.config: dict = self.load_config()

        if watch_file:
            # Watch for settings change
            self.stop_event = threading.Event()
            self.config_watcher_thread = threading.Thread(target=self.fileWatcher, name='file_watcher')#daemon=True
            self.config_watcher_thread.start()
            print('Start file watcher thread') 
            
    def stop(self):
        """Set stop event for fileWatcher thread"""
        self.stop_event.set()
        print('Stop file watcher thread')

    def join(self):
        #Wait until the thread terminates.
        self.config_watcher_thread.join()
    
    def load_config(self):
        """Load configuration data from the JSON file."""
        try:
            with open(self.config_file_path, "r") as f:
                config: dict = json.load(f)
                return config
        except FileNotFoundError:
            # If the file doesn't exist, create an new config
            return {}

    def get(self, key):
        # type: (str) -> dict
        """Gets the value from a given key."""
        return self.config.get(key)

    def set(self, key, value):
        """Update a configuration key with a new value."""
        self.config[key] = value

    def is_updated(self):
        """Return True if the configuration json file is updated."""
        return self.file_change

    def _save_config(self, config: dict):
        """Save the updated configuration back to the JSON file."""
        with open(self.config_file_path, "w") as f:
            json.dump(config, f, indent=4)

    def save_config(self):
        """Save the updated configuration back to the JSON file."""
        with open(self.config_file_path, "w") as f:
            json.dump(self.config, f, indent=4)

    def fileWatcher(self):
        """Watching for changes in json file and if file is change, reloade the file for the program."""
        f = open(self.config_file_path)
        comandosText = f.read()
        f.close()
        while not self.stop_event.is_set():
            f = open(self.config_file_path)
            content = f.read()
            f.close()
            if content != comandosText:
                print("File was modified! Reloading it...")
                comandosText = content
                self.config = self.load_config()
                self.file_change = True
            time.sleep(self.file_watcher_delay)
            self.file_change = False
