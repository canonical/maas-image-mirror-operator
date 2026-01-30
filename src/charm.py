#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Charm for setting up a MAAS simplestreams image mirror with nginx."""

import logging
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


class SimplestreamsMaasMirrorCharm(CharmBase):
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
        
        # # Ensure the web root directory exists (commented out; not sure this is needed)
        # web_root = Path("/var/www/html/maas/images/ephemeral-v3/stable")
        # web_root.mkdir(parents=True, exist_ok=True)
        
        # Reload nginx configuration
        logger.info("Reloading nginx")
        subprocess.check_call(["systemctl", "reload", "nginx"])

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
    main(SimplestreamsMaasMirrorCharm)
