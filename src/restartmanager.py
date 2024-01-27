"""Restart Manager"""
import time
import os
import datetime
from typing import Any

import docker
import schedule
from discord_webhook import DiscordWebhook, DiscordEmbed
from dotenv import load_dotenv
from rcon import Console

from logger import Logger


load_dotenv()

RCON_IP = os.getenv("RCON_IP")
RCON_PORT = os.getenv("RCON_PORT")
RCON_PASSWORD = os.getenv("RCON_PASSWORD")
DOCKER_CONTAINER = os.getenv("DOCKER_CONTAINER")
WEBHOOK = os.getenv("DISCORD_WEBHOOK")
LOG_LEVEL = os.getenv("LOG_LEVEL")
RESTART_TIME = 2 # hours
NOTIFY_TIME = 20 # minutes
MAX_RETRIES = 100
RETRY_DELAY = 3

log = Logger(__name__, LOG_LEVEL)

class RestartManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RestartManager, cls).__new__(cls)
            cls._instance.rcon = None
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.docker = docker.from_env()
            self.container = self.docker.containers.get(DOCKER_CONTAINER)
            self.hours = None
            self.minutes = None
            self.seconds = None
            self._set_new_restart_time()
            self._calculate_restart_time()
            self.initialized = True

    def restart(self):
        self._init_countdown()
        self._command("save")
        self.log_to_discord(log_message="Server restarting...", level="info")
        self.container.restart()
        last_message = b"[S_API FAIL] Tried to access Steam interface SteamNetworkingUtils004 before SteamAPI_Init succeeded."
        for line in self.container.logs(stream=True):
            log.info(line.strip())
            if last_message in line:
                break
        self._set_new_restart_time()
        self._calculate_restart_time()
        self.log_to_discord(log_message="Server restarted!", level="info")
        log.info("Server restarted!")

    def notify_restart(self):
        self._calculate_restart_time()
        proper_hrs = "hr" if self.hours == 1 else "hrs"
        proper_mins = "min" if self.minutes == 1 else "mins"
        self._broadcast(f"server_restart_in_{self.hours}{proper_hrs}_{self.minutes}{proper_mins}")

    def _set_new_restart_time(self):
        self.next_start = datetime.datetime.now() + datetime.timedelta(hours=RESTART_TIME)
        log.debug("new time has been set")

    def _calculate_restart_time(self):
        time_remaining = self.next_start - datetime.datetime.now()
        total_seconds = int(time_remaining.total_seconds())

        self.hours, remainder = divmod(total_seconds, 3600)
        self.minutes, self.seconds = divmod(remainder, 60)

    def _init_countdown(self):
        count = 5
        while count >= 0:
            if count > 0:
                self._broadcast(f"server_restarting_in_{count}_secs")
            else:
                self._broadcast("server_restarting_NOW!")
            count -= 1
            time.sleep(1)
        time.sleep(2)

    def _broadcast(self, message: str) -> Any:
        self._establish_rcon_connection()
        try:
            cmd = self.rcon.command(f"broadcast {message}")
            log.info(cmd)
            return cmd
        #pylint: disable=broad-exception-caught
        except Exception as exc:
            log.error(f"Failed to broadcast message: {exc}")

    def _command(self, command: str) -> Any:
        self._establish_rcon_connection()
        try:
            cmd = self.rcon.command(command=command)
            log.info(cmd)
            return cmd
        #pylint: disable=broad-exception-caught
        except Exception as exc:
            log.error(f"Failed to execute command: {exc}")

    def _is_container_running(self):
        status = self.container.status
        return status == "running"

    def _establish_rcon_connection(self):
        if not self._is_container_running():
            log.error("Container not running. Cannot establish RCON connection.")
            return

        if self.rcon is None or not self._is_rcon_connected():
            self._create_rcon_connection()

    def _is_rcon_connected(self):
        try:
            self.rcon.command("info")
            return True
        #pylint: disable=broad-exception-caught
        except Exception:
            return False

    def _create_rcon_connection(self):
        retries = MAX_RETRIES
        while retries > 0:
            try:
                self.rcon = Console(host=RCON_IP, password=RCON_PASSWORD)
                self.rcon.command("info")
                log.info("RCON connection successfully established.")
                return
            #pylint: disable=broad-exception-caught
            except Exception as exc:
                log.error(f"Failed to establish RCON connection: {exc}")
                retries -= 1
                if retries > 0:
                    log.info(f"Retrying to connect... attempts remaining: {retries}")
                    time.sleep(RETRY_DELAY)
                else:
                    log.error("Max retries reached. Unable to establish RCON connection.")
                    raise

    def log_to_discord(self, log_message: str, level: str):
        color_map = {
            "debug": "FFFFFF",
            "info": "00FF00",
            "error": "FF0000",
            "critical": "800000"
        }
        color = color_map.get(level, "FFFFFF")
        webhook = DiscordWebhook(url=WEBHOOK, username="ny1-vps")
        embed = DiscordEmbed(name="", description=log_message, color=color)
        embed.set_author(name="ny1-vps.pal.nocturnia.xyz")
        embed.set_timestamp()

        webhook.add_embed(embed)
        webhook.execute()

def restart_job():
    manager = RestartManager()
    manager.restart()

def notify_job():
    manager = RestartManager()
    manager.notify_restart()

if __name__ == "__main__":
    schedule.every(RESTART_TIME).hours.do(restart_job)
    schedule.every(NOTIFY_TIME).minutes.do(notify_job)
    log.info("Schedules started")

    while True:
        schedule.run_pending()
        time.sleep(1)
