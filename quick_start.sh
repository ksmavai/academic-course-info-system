#!/bin/bash

echo "🚀 Discord Note Sharing Bot - Quick Start"
echo "=========================================="

# Check Python version
echo "🐍 Checking Python version..."
python3 --version
if [ $? -ne 0 ]; then
    echo "❌ Python 3 not found. Please install Python 3.8+ first."
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies..."
pip3 install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "❌ Failed to install dependencies."
    exit 1
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "⚙️ Creating .env file from template..."
    cp .env.template .env
    echo "✅ Created .env file. Please edit it with your Discord bot token."
    echo ""
    echo "📝 Next steps:"
    echo "1. Edit .env file: nano .env"
    echo "2. Add your Discord bot token"
    echo "3. Run: python3 discord_note_bot.py"
    echo ""
    echo "📖 For detailed instructions, see DEPLOYMENT_GUIDE.md"
else
    echo "✅ .env file already exists."
    echo "🚀 Starting bot..."
    python3 discord_note_bot.py
fi
