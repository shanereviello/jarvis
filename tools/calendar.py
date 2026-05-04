import subprocess

def create_calendar_event(title, datetime_str):
    script = f'''
    tell application "Calendar"
        tell calendar "Jarvis"
            set startDate to date "{datetime_str}"
            set endDate to startDate + (60 * minutes)
            make new event with properties {{summary:"{title}", start date:startDate, end date:endDate}}
        end tell
    end tell
    '''

    result = subprocess.run(
    ["osascript", "-e", script],
    capture_output=True,
    text=True
)

    if result.returncode != 0:
        return f"AppleScript error: {result.stderr}"

    return f"Event '{title}' scheduled for {datetime_str}"