#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Charm for setting up a MAAS simplestreams image mirror with nginx."""

import logging
import re
import subprocess
import tempfile
from pathlib import Path

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, BlockedStatus

logger = logging.getLogger(__name__)

NGINX_SITE_CONFIG = """server {
    listen 80;
    root /var/www/html;
    location / {
        autoindex on;
    }
}
"""

OPEN_PORTS = [80]


class MaasImageMirrorCharm(CharmBase):
    """Charm for MAAS simplestreams image mirror."""

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.start, self._on_start)

    def _on_install(self, event):
        """Handle the install event."""
        self.unit.status = MaintenanceStatus("Installing packages")
        
        try:
            # Update apt cache
            logger.info("Updating apt cache")
            subprocess.check_call(["apt-get", "update"])
            
            # Install required packages
            logger.info("Installing nginx and simplestreams")
            subprocess.check_call([
                "apt-get", "install", "-y",
                "nginx",
                "simplestreams"
            ])
            
            # Configure nginx
            self._configure_nginx()
            
            # Run bootstrap sync if enabled
            bootstrap_sync = self.config.get("bootstrap-sync", True)
            cron_jobs = self.config.get("cron-jobs", "").strip()
            if bootstrap_sync and cron_jobs:
                self.unit.status = MaintenanceStatus("Running bootstrap sync")
                self._run_bootstrap_sync(cron_jobs)
            
            # Set up cron jobs
            self._configure_cron()
            
            self.unit.status = MaintenanceStatus("Installation complete")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install packages: {e}")
            self.unit.status = BlockedStatus(f"Installation failed: {e}")
            return

    def _configure_nginx(self):
        """Configure nginx web server."""
        logger.info("Configuring nginx")
        
        # Create the image-mirror site configuration
        site_config_path = Path("/etc/nginx/sites-available/image-mirror")
        site_config_path.write_text(NGINX_SITE_CONFIG)
        
        # Disable default site
        default_enabled = Path("/etc/nginx/sites-enabled/default")
        if default_enabled.exists():
            logger.info("Disabling default nginx site")
            default_enabled.unlink()
        
        # Enable image-mirror site
        site_enabled = Path("/etc/nginx/sites-enabled/image-mirror")
        if not site_enabled.exists():
            logger.info("Enabling image-mirror site")
            site_enabled.symlink_to(site_config_path)
        
        # Reload nginx configuration
        logger.info("Reloading nginx")
        subprocess.check_call(["systemctl", "reload", "nginx"])

    def _parse_cron_commands(self, cron_jobs):
        """Extract commands from cron job entries.
        
        Args:
            cron_jobs: String containing cron job entries
            
        Returns:
            List of command strings extracted from the cron entries
        """
        commands = []
        for line in cron_jobs.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Cron format: minute hour day-of-month month day-of-week command
            # Split on whitespace, then grab the final portion to execute
            parts = line.split(None, 5)
            if len(parts) >= 6:
                command = parts[5]
                commands.append(command)
            else:
                logger.warning(f"Skipping invalid cron entry: {line}")
        
        return commands
    
    def _run_bootstrap_sync(self, cron_jobs):
        """Run configured cron job commands sequentially.
        
        Args:
            cron_jobs: String containing cron job entries
        """
        commands = self._parse_cron_commands(cron_jobs)
        
        if not commands:
            logger.info("No commands to run for bootstrap sync")
            return
        
        logger.info(f"Running bootstrap sync for {len(commands)} command(s)")
        
        for idx, command in enumerate(commands, 1):
            logger.info(f"Running bootstrap command {idx}/{len(commands)}: {command}")
            try:
                # Run the command using shell to properly handle arguments
                subprocess.check_call(command, shell=True)
                logger.info(f"Bootstrap command {idx} completed successfully")
            except subprocess.CalledProcessError as e:
                logger.error(f"Bootstrap command {idx} failed with exit code {e.returncode}")
                # Continue with remaining commands even if one fails
    
    def _configure_cron(self):
        """Configure cron jobs for root user."""
        cron_jobs = self.config.get("cron-jobs", "").strip()
        
        if not cron_jobs:
            logger.info("No cron jobs configured")
            return
        
        logger.info("Configuring cron jobs")
        
        # Create a temporary file with the cron jobs
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.cron') as f:
            f.write(cron_jobs)
            f.write("\n")  # Ensure newline at end
            temp_path = f.name
        
        try:
            # Install the crontab for root
            subprocess.check_call(["crontab", "-u", "root", temp_path])
            logger.info("Cron jobs installed successfully")
        finally:
            # Clean up temporary file
            Path(temp_path).unlink(missing_ok=True)

    def _on_config_changed(self, event):
        """Handle configuration changes."""
        self.unit.status = MaintenanceStatus("Updating configuration")
        
        try:
            # Reconfigure cron jobs when config changes
            self._configure_cron()
            # Declare our open ports (currently hardcoded)
            self.unit.set_ports(*OPEN_PORTS)
            self.unit.status = ActiveStatus("Ready")
        except Exception as e:
            logger.error(f"Failed to update configuration: {e}")
            self.unit.status = BlockedStatus(f"Configuration failed: {e}")

    def _on_start(self, event):
        """Handle the start event."""
        try:
            # Ensure nginx is running
            subprocess.check_call(["systemctl", "start", "nginx"])
            subprocess.check_call(["systemctl", "enable", "nginx"])
            self.unit.status = ActiveStatus("Ready")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start nginx: {e}")
            self.unit.status = BlockedStatus(f"Failed to start nginx: {e}")


if __name__ == "__main__":
    main(MaasImageMirrorCharm)
