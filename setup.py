#!/usr/bin/env python3
"""
Discord Note Sharing Bot - Deployment Script
Automated setup and deployment helper
"""

import os
import sys
import subprocess
import sqlite3
from pathlib import Path

def print_banner():
    print("""
    ╔══════════════════════════════════════════════╗
    ║         Discord Note Sharing Bot             ║
    ║              Setup Assistant                 ║
    ╚══════════════════════════════════════════════╝
    """)

def check_python_version():
    """Check if Python version is compatible"""
    print("🐍 Checking Python version...")
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required!")
        print(f"   Current version: {sys.version}")
        return False
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} is compatible")
    return True

def install_dependencies():
    """Install required Python packages"""
    print("📦 Installing dependencies...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False

def create_directories():
    """Create necessary directories"""
    print("📁 Creating directories...")
    directories = ['files', 'watermarked', 'logs']

    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"   ✓ Created {directory}/")

    print("✅ Directories created")

def setup_environment():
    """Setup environment variables"""
    print("⚙️  Setting up environment...")

    if Path('.env').exists():
        print("   ℹ️  .env file already exists")
        return True

    if not Path('.env.template').exists():
        print("❌ .env.template not found!")
        return False

    # Copy template
    with open('.env.template', 'r') as template:
        content = template.read()

    print("   📝 Please provide the following configuration:")

    # Get bot token
    while True:
        token = input("   Discord Bot Token: ").strip()
        if token and token != "your_bot_token_here":
            content = content.replace("your_bot_token_here", token)
            break
        print("   ❌ Please enter a valid Discord bot token")

    # Optional settings
    max_size = input("   Max file size in MB (default: 10): ").strip()
    if max_size and max_size.isdigit():
        content = content.replace("MAX_FILE_SIZE_MB=10", f"MAX_FILE_SIZE_MB={max_size}")

    opacity = input("   Watermark opacity 0.1-1.0 (default: 0.3): ").strip()
    if opacity:
        try:
            float(opacity)
            content = content.replace("WATERMARK_OPACITY=0.3", f"WATERMARK_OPACITY={opacity}")
        except ValueError:
            print("   ⚠️  Invalid opacity value, using default")

    log_level = input("   Log level (DEBUG/INFO/WARNING/ERROR, default: INFO): ").strip().upper()
    if log_level in ['DEBUG', 'WARNING', 'ERROR']:
        content = content.replace("LOG_LEVEL=INFO", f"LOG_LEVEL={log_level}")

    # Write .env file
    with open('.env', 'w') as env_file:
        env_file.write(content)

    print("✅ Environment configured")
    return True

def test_database():
    """Test database creation"""
    print("🗄️  Testing database setup...")
    try:
        # Simple database test
        conn = sqlite3.connect('test.db')
        conn.execute('CREATE TABLE test (id INTEGER)')
        conn.close()
        os.remove('test.db')
        print("✅ Database test passed")
        return True
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False

def verify_files():
    """Verify all required files exist"""
    print("🔍 Verifying files...")
    required_files = [
        'discord_note_bot.py',
        'config.py',
        'requirements.txt',
        '.env'
    ]

    missing_files = []
    for file in required_files:
        if not Path(file).exists():
            missing_files.append(file)
        else:
            print(f"   ✓ {file}")

    if missing_files:
        print(f"❌ Missing files: {', '.join(missing_files)}")
        return False

    print("✅ All files present")
    return True

def show_next_steps():
    """Show user what to do next"""
    print("""
    ╔══════════════════════════════════════════════╗
    ║              Setup Complete!                 ║
    ╚══════════════════════════════════════════════╝

    🎉 Your Discord Note Sharing Bot is ready!

    📋 Next Steps:

    1. 🤖 Discord Bot Setup:
       • Go to https://discord.com/developers/applications
       • Create a new application and bot
       • Enable Message Content Intent
       • Copy the bot token to your .env file

    2. 🔗 Invite Bot to Server:
       • Use this permission integer: 274877910016
       • Or visit: https://discord.com/api/oauth2/authorize?client_id=YOUR_BOT_ID&permissions=274877910016&scope=bot%20applications.commands

    3. 🚀 Start the Bot:
       • Run: python discord_note_bot.py
       • Or: python3 discord_note_bot.py
       • Or: python3 run.py

    4. 📖 Usage:
       • /upload - Upload PDF notes
       • /browse - Browse available notes  
       • /download - Download watermarked notes
       • /admin delete - Delete files (admin only)

    📚 For detailed instructions, see setup-guide.md

    🔒 Security Notes:
    • All downloads are watermarked
    • Admin permissions required for management
    • Complete audit trail maintained
    """)

def main():
    """Main setup process"""
    print_banner()

    # Step-by-step setup
    steps = [
        ("Checking Python version", check_python_version),
        ("Installing dependencies", install_dependencies),
        ("Creating directories", create_directories),
        ("Setting up environment", setup_environment),
        ("Testing database", test_database),
        ("Verifying files", verify_files)
    ]

    for step_name, step_func in steps:
        print(f"\n{step_name}...")
        if not step_func():
            print(f"\n❌ Setup failed at: {step_name}")
            print("Please resolve the issue and run setup again.")
            sys.exit(1)

    print("\n" + "="*50)
    show_next_steps()

if __name__ == "__main__":
    main()