"""Example: use jadwal as a library in your own Python code.

Run:
    python examples/library_usage.py
"""
from datetime import date

from jadwal import get_next_prayer, get_schedule


def main():
    # Get today's schedule for Jakarta
    schedule = get_schedule(city="jakarta")
    print(f"Prayer times for {schedule.location} on {schedule.date}:")
    for name, time in schedule.as_list():
        print(f"  {name:10s}  {time}")

    # Show the next prayer
    nxt = get_next_prayer(schedule)
    print(f"\nNext prayer: {nxt['name']} at {nxt['time']} ({nxt['human']})")

    # Custom coordinates (e.g., a remote village)
    custom = get_schedule(
        lat=-8.4095,
        lng=115.1889,
        timezone="Asia/Makassar",
        target_date=date(2024, 12, 25),
        method="kemenag",
    )
    print(f"\nCustom location ({custom.location}) on {custom.date}:")
    for name, time in custom.as_list():
        print(f"  {name:10s}  {time}")


if __name__ == "__main__":
    main()
