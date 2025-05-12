# Setting up systemd Service and Timer

This guide explains how to set up a systemd service and timer to run the calendar event aggregator. We'll use a user-specific service that doesn't require root privileges.

## Prerequisites

- Linux system with systemd
- Python and required dependencies installed
- Working `.env` file with all credentials

## Service Configuration

1. Create a service file at `~/.config/systemd/user/calendar-sync.service`:

```ini
[Unit]
Description=Calendar Event Aggregator Service
After=network.target

[Service]
Type=simple
ExecStart=python %h/path/to/calendar-aggregator/main.py
WorkingDirectory=%h/path/to/calendar-aggregator
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

Replace `/path/to/calendar-aggregator` with the actual path to your project directory relative to your home directory.

2. Create a timer file at `~/.config/systemd/user/calendar-sync.timer`:

```ini
[Unit]
Description=Run Calendar Event Aggregator twice daily

[Timer]
OnCalendar=*-*-* 06:00:00
OnCalendar=*-*-* 18:00:00
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
```

This timer will run the service at:
- 6:00 AM (with up to 5 minutes random delay)
- 6:00 PM (with up to 5 minutes random delay)

## Setting up the Service

1. Reload systemd to recognize the new service:
   ```bash
   systemctl --user daemon-reload
   ```

2. Enable and start the timer:
   ```bash
   systemctl --user enable calendar-sync.timer
   systemctl --user start calendar-sync.timer
   ```

3. Verify the timer is active:
   ```bash
   systemctl --user status calendar-sync.timer
   ```

4. Check the next run time:
   ```bash
   systemctl --user list-timers calendar-sync.timer
   ```

## Logs and Debugging

1. View service logs:
   ```bash
   journalctl --user -u calendar-sync.service
   ```

2. View timer logs:
   ```bash
   journalctl --user -u calendar-sync.timer
   ```

3. Follow logs in real-time:
   ```bash
   journalctl --user -u calendar-sync.service -f
   ```

## Common Commands

- Start service manually:
   ```bash
   systemctl --user start calendar-sync.service
   ```

- Stop service:
   ```bash
   systemctl --user stop calendar-sync.service
   ```

- Disable timer:
   ```bash
   systemctl --user disable calendar-sync.timer
   ```

- Check service status:
   ```bash
   systemctl --user status calendar-sync.service
   ```

## Troubleshooting

1. If the service fails to start:
   - Check the service logs
   - Verify the paths in the service file
   - Ensure the `.env` file exists and has correct permissions

2. If the timer doesn't trigger:
   - Verify the timer is enabled and active
   - Check system time and timezone
   - Look for errors in the timer logs

3. Permission issues:
   - Ensure your user has read access to the project directory
   - Check that the `.env` file is readable
   - Verify Python and dependencies are accessible

## Security Considerations

1. File permissions:
   ```bash
   # Set proper permissions for the project directory
   chmod 700 ~/path/to/calendar-aggregator
   
   # Set proper permissions for the .env file
   chmod 600 ~/path/to/calendar-aggregator/.env
   ```

2. Log rotation:
   - Configure log rotation to prevent disk space issues
   - Set appropriate log retention periods
   - Monitor log file sizes

## Notes

- Using user-specific services is more secure as it doesn't require root privileges
- The service will only run when the user is logged in
- To ensure the service runs even when the user is not logged in, you may need to enable lingering:
   ```bash
   loginctl enable-linger $USER
   ``` 