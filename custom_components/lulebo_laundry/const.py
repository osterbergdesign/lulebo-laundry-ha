DOMAIN = "lulebo_laundry"

# Network
REQUEST_TIMEOUT = 30  # seconds, applied to every HTTP request

# Slot number -> (start, end) as "HH:MM" strings.
# Used by the sensor for the human-readable list and by the calendar
# to build timed events.
SLOT_TIMES = {
    "0": ("07:00", "10:30"),
    "1": ("10:30", "14:00"),
    "2": ("14:00", "17:30"),
    "3": ("17:30", "21:00"),
}

# Convenience: "07:00 - 10:30" labels used by the sensor attributes.
SLOT_LABELS = {slot: f"{start} - {end}" for slot, (start, end) in SLOT_TIMES.items()}
