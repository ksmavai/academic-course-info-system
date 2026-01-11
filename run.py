#!/usr/bin/env python3
"""
Discord Note Sharing Bot - Run Script
Simple launcher with error handling
"""

import sys
import os
from pathlib import Path

def check_setup():
    """Check if bot is properly set up"""
    required_files = ['.env', 'discord_note_bot.py', 'config.py']
    missing = [f for f in required_files if not Path(f).exists()]

    if missing:
        print("❌ Setup incomplete!")
        print(f"Missing files: {', '.join(missing)}")
        print("\nRun 'python setup.py' to complete setup.")
        return False
    return True

def main():
    print("🤖 Starting Discord Note Sharing Bot...")

    if not check_setup():
        sys.exit(1)

    try:
        from discord_note_bot import bot, BotConfig
        bot.run(BotConfig.TOKEN)
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("\nTry running: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
        print("\nCheck your configuration and logs for details.")
        sys.exit(1)

if __name__ == "__main__":
    main()