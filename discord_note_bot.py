import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import asyncio
import os
import uuid
import logging
import hashlib
import time
from pathlib import Path
from typing import Optional, List, Dict, Tuple
import aiosqlite
from datetime import datetime, timedelta
from collections import defaultdict
import json
import shutil
import tempfile

# PDF Libraries
import io
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import Color
import math

# Configuration
from config import BotConfig

# Validate configuration
try:
    validation_errors = BotConfig.validate_all()
    if validation_errors:
        print("❌ Configuration validation failed:")
        for error in validation_errors:
            print(f"   - {error}")
        exit(1)
except Exception as e:
    print(f"❌ Configuration error: {e}")
    exit(1)

# Configure logging with structured format
class StructuredFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        return json.dumps(log_data)

# Setup logging
logging.basicConfig(
    level=getattr(logging, BotConfig.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{BotConfig.LOGS_DIR}/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Rate limiting storage
rate_limits: Dict[int, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

class RateLimiter:
    """Rate limiting utility"""
    
    @staticmethod
    def check_rate_limit(user_id: int, action: str, limit: int, window: int = 3600) -> bool:
        """Check if user is within rate limits"""
        if not BotConfig.ENABLE_RATE_LIMITING:
            return True
            
        now = time.time()
        user_actions = rate_limits[user_id][action]
        
        # Remove old entries outside the window
        user_actions[:] = [t for t in user_actions if now - t < window]
        
        # Check if under limit
        if len(user_actions) >= limit:
            return False
            
        # Add current action
        user_actions.append(now)
        return True
    
    @staticmethod
    def get_remaining_actions(user_id: int, action: str, limit: int, window: int = 3600) -> int:
        """Get remaining actions for user"""
        now = time.time()
        user_actions = rate_limits[user_id][action]
        user_actions[:] = [t for t in user_actions if now - t < window]
        return max(0, limit - len(user_actions))

class NoteSharingBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            description="Private Note Sharing Bot with PDF Watermarking"
        )

        # Create necessary directories
        self.setup_directories()

    def setup_directories(self):
        """Create necessary directories for file storage"""
        directories = [
            BotConfig.FILES_DIR, 
            BotConfig.WATERMARKED_DIR, 
            BotConfig.LOGS_DIR,
            BotConfig.BACKUP_DIR
        ]
        
        for directory in directories:
            Path(directory).mkdir(exist_ok=True)
            logger.info(f"Created/verified directory: {directory}")

    async def setup_hook(self):
        """Initialize database, load cogs, and sync commands"""
        await self.init_database()
        
        # Load extensions
        try:
            await self.load_extension("cogs.ai_chat")
            logger.info("Loaded extension: cogs.ai_chat")
        except Exception as e:
            logger.error(f"Failed to load extension cogs.ai_chat: {e}")

        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
        
        # Start background tasks
        self.cleanup_temp_files.start()
        self.backup_database.start()
        self.cleanup_old_logs.start()

    async def init_database(self):
        """Initialize SQLite database with required tables and indexes"""
        async with aiosqlite.connect(BotConfig.DATABASE_NAME) as db:
            # Enable foreign keys
            await db.execute("PRAGMA foreign_keys = ON")
            
            # Files table with enhanced schema
            await db.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id TEXT PRIMARY KEY,
                    original_filename TEXT NOT NULL,
                    course_code TEXT NOT NULL,
                    lecture_number TEXT NOT NULL CHECK (length(lecture_number) <= 10),
                    note_taker TEXT NOT NULL CHECK (length(note_taker) <= 30),
                    uploader_id INTEGER NOT NULL,
                    uploader_username TEXT NOT NULL,
                    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    file_size INTEGER NOT NULL CHECK (file_size > 0),
                    file_path TEXT NOT NULL,
                    file_hash TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    download_count INTEGER DEFAULT 0,
                    last_downloaded TIMESTAMP
                )
            """)

            # Download logs table with enhanced tracking
            await db.execute("""
                CREATE TABLE IF NOT EXISTS download_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id TEXT NOT NULL,
                    downloader_id INTEGER NOT NULL,
                    downloader_username TEXT NOT NULL,
                    download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ip_hash TEXT,
                    user_agent_hash TEXT,
                    download_source TEXT DEFAULT 'bot',
                    FOREIGN KEY (file_id) REFERENCES files (id) ON DELETE CASCADE
                )
            """)

            # Admin actions log table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER NOT NULL,
                    admin_username TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_file_id TEXT,
                    action_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    details TEXT,
                    ip_hash TEXT
                )
            """)

            # Rate limiting table for persistent rate limiting
            await db.execute("""
                CREATE TABLE IF NOT EXISTS rate_limits (
                    user_id INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    action_count INTEGER DEFAULT 1,
                    window_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, action_type, window_start)
                )
            """)

            # Create indexes for better performance
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_files_course ON files(course_code)",
                "CREATE INDEX IF NOT EXISTS idx_files_uploader ON files(uploader_id)",
                "CREATE INDEX IF NOT EXISTS idx_files_active ON files(is_active)",
                "CREATE INDEX IF NOT EXISTS idx_files_upload_date ON files(upload_date)",
                "CREATE INDEX IF NOT EXISTS idx_downloads_date ON download_logs(download_date)",
                "CREATE INDEX IF NOT EXISTS idx_downloads_file ON download_logs(file_id)",
                "CREATE INDEX IF NOT EXISTS idx_downloads_user ON download_logs(downloader_id)",
                "CREATE INDEX IF NOT EXISTS idx_admin_logs_date ON admin_logs(action_date)",
                "CREATE INDEX IF NOT EXISTS idx_admin_logs_admin ON admin_logs(admin_id)",
                "CREATE INDEX IF NOT EXISTS idx_rate_limits_user ON rate_limits(user_id)"
            ]
            
            for index_sql in indexes:
                await db.execute(index_sql)

            await db.commit()
            logger.info("Database initialized successfully with indexes")

            # Create table for course reviews (for migrated commands)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS course_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    course_code TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    review TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )
            await db.commit()

    @tasks.loop(hours=1)
    async def cleanup_temp_files(self):
        """Clean up temporary files"""
        if not BotConfig.CLEANUP_TEMP_FILES:
            return
            
        temp_dir = Path(BotConfig.WATERMARKED_DIR)
        if temp_dir.exists():
            for file in temp_dir.glob("*.pdf"):
                # Delete files older than 1 hour
                if file.stat().st_mtime < time.time() - 3600:
                    try:
                        file.unlink()
                        logger.info(f"Cleaned up temp file: {file.name}")
                    except Exception as e:
                        logger.warning(f"Could not delete temp file {file.name}: {e}")

    @cleanup_temp_files.before_loop
    async def before_cleanup_temp_files(self):
        await self.wait_until_ready()

    @tasks.loop(hours=BotConfig.DATABASE_BACKUP_INTERVAL_HOURS)
    async def backup_database(self):
        """Backup database regularly"""
        try:
            backup_dir = Path(BotConfig.BACKUP_DIR)
            backup_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"database_backup_{timestamp}.db"
            
            shutil.copy2(BotConfig.DATABASE_NAME, backup_path)
            logger.info(f"Database backup created: {backup_path}")
            
            # Keep only last 7 backups
            backups = sorted(backup_dir.glob("database_backup_*.db"))
            for old_backup in backups[:-7]:
                old_backup.unlink()
                logger.info(f"Removed old backup: {old_backup.name}")
                
        except Exception as e:
            logger.error(f"Database backup failed: {e}")

    @backup_database.before_loop
    async def before_backup_database(self):
        await self.wait_until_ready()

    @tasks.loop(hours=24)
    async def cleanup_old_logs(self):
        """Clean up old log entries"""
        try:
            async with aiosqlite.connect(BotConfig.DATABASE_NAME) as db:
                # Clean up download logs older than configured days
                cutoff_date = datetime.now() - timedelta(days=BotConfig.DATABASE_CLEANUP_DAYS)
                await db.execute(
                    "DELETE FROM download_logs WHERE download_date < ?",
                    (cutoff_date.isoformat(),)
                )
                await db.execute(
                    "DELETE FROM admin_logs WHERE action_date < ?",
                    (cutoff_date.isoformat(),)
                )
                await db.commit()
                logger.info(f"Cleaned up logs older than {BotConfig.DATABASE_CLEANUP_DAYS} days")
        except Exception as e:
            logger.error(f"Log cleanup failed: {e}")

    @cleanup_old_logs.before_loop
    async def before_cleanup_old_logs(self):
        await self.wait_until_ready()

    def generate_watermark_pdf(self, text: str, page_width: float, page_height: float, download_id: str = None) -> io.BytesIO:
        """Generate an enhanced watermark PDF with multiple security layers"""
        packet = io.BytesIO()

        # Create canvas
        c = canvas.Canvas(packet, pagesize=(page_width, page_height))

        # Get watermark color from config
        watermark_color = BotConfig.get_watermark_color()

        # Set transparency
        c.setFillAlpha(BotConfig.WATERMARK_OPACITY)

        # Set font for diagonal watermark
        c.setFont("Helvetica-Bold", BotConfig.WATERMARK_FONT_SIZE)

        # Calculate diagonal angle and position
        diagonal_angle = math.atan2(page_height, page_width) * 180 / math.pi

        # Multiple watermarks across the page (enhanced grid)
        step_x = page_width / 4  # More dense coverage
        step_y = page_height / 5

        for x_offset in range(0, int(page_width), int(step_x)):
            for y_offset in range(0, int(page_height), int(step_y)):
                c.saveState()
                c.translate(x_offset + step_x/2, y_offset + step_y/2)
                c.rotate(diagonal_angle)
                c.setFillColor(Color(watermark_color[0], watermark_color[1], watermark_color[2], alpha=BotConfig.WATERMARK_OPACITY))
                
                # Add multiple watermark text variations
                watermark_texts = [
                    text,
                    f"{text} - {datetime.now().strftime('%Y%m%d')}",
                    f"Downloaded: {text}"
                ]
                
                for i, wm_text in enumerate(watermark_texts):
                    c.drawCentredString(0, 10 + (i * 15), wm_text)
                
                c.restoreState()

        # Add corner watermarks with enhanced information
        c.saveState()
        c.setFont("Helvetica", BotConfig.WATERMARK_SMALL_FONT_SIZE)
        c.setFillAlpha(0.6)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Bottom left corner
        c.drawString(30, 30, f"Downloaded by: {text}")
        c.drawString(30, 15, f"Date: {timestamp}")
        
        # Top right corner (if there's space)
        if page_width > 200:
            c.drawString(page_width - 200, page_height - 20, f"ID: {download_id[:8] if download_id else 'N/A'}")
        
        # Add invisible watermark for tamper detection
        if download_id:
            c.setFillAlpha(0.1)  # Very transparent
            c.setFont("Helvetica", 8)
            c.drawString(page_width - 100, 10, f"SEC:{hashlib.md5(download_id.encode()).hexdigest()[:8]}")
        
        c.restoreState()

        c.save()
        packet.seek(0)
        return packet

    async def apply_watermark_to_pdf(self, original_pdf_path: str, downloader_username: str) -> io.BytesIO:
        """Apply watermark to all pages of a PDF"""
        try:
            # Read original PDF
            with open(original_pdf_path, 'rb') as file:
                pdf_reader = PdfReader(file)
                pdf_writer = PdfWriter()

                total_pages = len(pdf_reader.pages)
                logger.info(f"Applying watermark to {total_pages} pages for user {downloader_username}")

                for page_num, page in enumerate(pdf_reader.pages):
                    # Get page dimensions
                    page_width = float(page.mediabox.width)
                    page_height = float(page.mediabox.height)

                    # Generate watermark for this page
                    watermark_packet = self.generate_watermark_pdf(
                        downloader_username, page_width, page_height
                    )

                    # Create watermark page
                    watermark_pdf = PdfReader(watermark_packet)
                    watermark_page = watermark_pdf.pages[0]

                    # Merge watermark with original page
                    page.merge_page(watermark_page)
                    pdf_writer.add_page(page)

                # Write to BytesIO
                output = io.BytesIO()
                pdf_writer.write(output)
                output.seek(0)
                return output

        except Exception as e:
            logger.error(f"Error applying watermark: {e}")
            raise

    def sanitize_filename(self, text: str, max_length: int = 50) -> str:
        """Sanitize text for use in filenames"""
        # Keep only alphanumeric characters, hyphens, and underscores
        sanitized = "".join(c for c in text if c.isalnum() or c in "-_")
        return sanitized[:max_length]

# Initialize bot instance
bot = NoteSharingBot()

# Enhanced input validation
def validate_upload_inputs(course_code: str, lecture_number: str, note_taker: str) -> List[str]:
    """Validate upload inputs and return list of errors"""
    errors = []
    
    if not BotConfig.validate_input('course_code', course_code):
        errors.append("Course code must be in format like SYSC2006 (3-4 letters + 4 numbers)")
    
    if not BotConfig.validate_input('lecture_number', lecture_number):
        errors.append("Lecture number can only contain letters, numbers, hyphens, and underscores (max 10 chars)")
    
    if not BotConfig.validate_input('note_taker', note_taker):
        errors.append("Note taker can only contain letters, numbers, hyphens, and underscores (max 30 chars)")
    
    return errors

# File upload command with enhanced validation
@bot.tree.command(name="upload", description="Upload a PDF note file with enhanced security")
@app_commands.describe(
    file="PDF file to upload",
    course_code="Course code (e.g., SYSC2006)",
    lecture_number="Lecture number (e.g., L1, Lec01)",
    note_taker="Note taker identifier (username or pseudo)"
)
async def upload_file(
    interaction: discord.Interaction,
    file: discord.Attachment,
    course_code: str,
    lecture_number: str,
    note_taker: str
):
    try:
        await interaction.response.defer()
    except (discord.NotFound, discord.HTTPException):
        # If already acknowledged or interaction expired, use followup
        pass

    try:
        # Rate limiting check
        if not RateLimiter.check_rate_limit(interaction.user.id, 'upload', BotConfig.MAX_UPLOADS_PER_HOUR):
            remaining = RateLimiter.get_remaining_actions(interaction.user.id, 'upload', BotConfig.MAX_UPLOADS_PER_HOUR)
            await interaction.followup.send(
                f"❌ Rate limit exceeded! You can upload {BotConfig.MAX_UPLOADS_PER_HOUR} files per hour. "
                f"Try again in {remaining} minutes.", 
                ephemeral=True
            )
            return

        # Validate file type
        if not any(file.filename.lower().endswith(ext) for ext in BotConfig.ALLOWED_EXTENSIONS):
            await interaction.followup.send(
                f"❌ Only {', '.join(BotConfig.ALLOWED_EXTENSIONS)} files are allowed!", 
                ephemeral=True
            )
            return

        # Validate file size
        if file.size > BotConfig.MAX_FILE_SIZE:
            max_mb = BotConfig.MAX_FILE_SIZE / (1024 * 1024)
            await interaction.followup.send(
                f"❌ File size must be under {max_mb}MB!", 
                ephemeral=True
            )
            return

        # Enhanced input validation
        validation_errors = validate_upload_inputs(course_code, lecture_number, note_taker)
        if validation_errors:
            error_msg = "❌ Validation errors:\n" + "\n".join(f"• {error}" for error in validation_errors)
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        # Check user file limit
        async with aiosqlite.connect(BotConfig.DATABASE_NAME) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM files WHERE uploader_id = ? AND is_active = 1", 
                (interaction.user.id,)
            ) as cursor:
                user_file_count = (await cursor.fetchone())[0]
        
        if user_file_count >= BotConfig.MAX_FILES_PER_USER:
            await interaction.followup.send(
                f"❌ You have reached the maximum limit of {BotConfig.MAX_FILES_PER_USER} files per user!", 
                ephemeral=True
            )
            return

        # Generate unique file ID
        file_id = str(uuid.uuid4())

        # Create new filename with sanitization
        safe_course = bot.sanitize_filename(course_code, 20)
        safe_lecture = bot.sanitize_filename(lecture_number, 10)
        safe_taker = bot.sanitize_filename(note_taker, 20)

        new_filename = f"{safe_course}-{safe_lecture}-{safe_taker}.pdf"
        file_path = f"{BotConfig.FILES_DIR}/{file_id}.pdf"

        # Download and save file
        await file.save(file_path)

        # Calculate file hash for integrity checking
        file_hash = None
        try:
            with open(file_path, 'rb') as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
        except Exception as e:
            logger.warning(f"Could not calculate file hash for {file_id}: {e}")

        # Store in database with enhanced tracking
        async with aiosqlite.connect(BotConfig.DATABASE_NAME) as db:
            await db.execute("""
                INSERT INTO files 
                (id, original_filename, course_code, lecture_number, note_taker, 
                 uploader_id, uploader_username, file_size, file_path, file_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_id, file.filename, course_code, lecture_number, 
                note_taker, interaction.user.id, interaction.user.name, file.size, file_path, file_hash
            ))
            await db.commit()

        # Success message
        embed = discord.Embed(
            title="✅ File Uploaded Successfully",
            color=discord.Color.green(),
            description=f"**File:** {new_filename}\n**Course:** {course_code}\n**Lecture:** {lecture_number}\n**Note Taker:** {note_taker}"
        )
        embed.add_field(name="File Size", value=f"{file.size / 1024:.1f} KB", inline=True)
        embed.add_field(name="Uploader", value=interaction.user.mention, inline=True)
        embed.set_footer(text=f"File ID: {file_id[:8]} | Use this ID to download")

        await interaction.followup.send(embed=embed)
        logger.info(f"File uploaded: {new_filename} by {interaction.user} ({interaction.user.id})")

    except Exception as e:
        logger.error(f"Upload error for user {interaction.user}: {e}")
        await interaction.followup.send("❌ An error occurred during upload. Please try again.", ephemeral=True)

# Browse files command with pagination
class BrowseView(discord.ui.View):
    def __init__(self, files: List, per_page: int = 5):
        super().__init__(timeout=300)
        self.files = files
        self.per_page = per_page
        self.current_page = 0
        self.max_page = (len(files) - 1) // per_page

    def get_embed(self):
        start_idx = self.current_page * self.per_page
        end_idx = start_idx + self.per_page
        current_files = self.files[start_idx:end_idx]

        embed = discord.Embed(
            title="📚 Available Notes",
            color=discord.Color.blue(),
            description=f"Page {self.current_page + 1}/{self.max_page + 1} | Total: {len(self.files)} files"
        )

        for file_data in current_files:
            file_id, original_name, course, lecture, taker, uploader_id, uploader_name, upload_date, size, path, file_hash, is_active, download_count, last_downloaded = file_data

            size_kb = size / 1024 if size else 0
            upload_date_formatted = upload_date[:10] if upload_date else "Unknown"

            embed.add_field(
                name=f"{course}-{lecture}-{taker}",
                value=f"📄 **ID:** `{file_id[:8]}`\n👤 **Taker:** {taker}\n📤 **Uploader:** {uploader_name}\n📅 **Date:** {upload_date_formatted}\n📊 **Size:** {size_kb:.1f} KB",
                inline=True
            )

        # Update button states
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == self.max_page

        return embed

    @discord.ui.button(label='◀️ Previous', style=discord.ButtonStyle.primary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label='Next ▶️', style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.max_page:
            self.current_page += 1
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

@bot.tree.command(name="browse", description="Browse available notes")
@app_commands.describe(
    course_code="Filter by course code (optional)",
    note_taker="Filter by note taker (optional)"
)
async def browse_files(
    interaction: discord.Interaction,
    course_code: Optional[str] = None,
    note_taker: Optional[str] = None
):
    try:
        await interaction.response.defer()
    except (discord.NotFound, discord.HTTPException):
        # If already acknowledged or interaction expired, use followup
        pass

    try:
        # Build query
        query = "SELECT * FROM files WHERE is_active = 1"
        params = []

        if course_code:
            query += " AND course_code LIKE ?"
            params.append(f"%{course_code}%")

        if note_taker:
            query += " AND note_taker LIKE ?"
            params.append(f"%{note_taker}%")

        query += " ORDER BY course_code, lecture_number, upload_date DESC"

        async with aiosqlite.connect(BotConfig.DATABASE_NAME) as db:
            async with db.execute(query, params) as cursor:
                files = await cursor.fetchall()

        if not files:
            await interaction.followup.send("📝 No files found matching your criteria.")
            return

        # Use pagination view
        view = BrowseView(files)
        embed = view.get_embed()

        await interaction.followup.send(embed=embed, view=view)

    except Exception as e:
        logger.error(f"Browse error for user {interaction.user}: {e}")
        await interaction.followup.send("❌ An error occurred while browsing files.", ephemeral=True)

# Download file command with enhanced security and rate limiting
@bot.tree.command(name="download", description="Download a note file with enhanced watermarking")
@app_commands.describe(file_id="File ID to download (first 8 characters sufficient)")
async def download_file(interaction: discord.Interaction, file_id: str):
    try:
        await interaction.response.defer(ephemeral=True)
    except (discord.NotFound, discord.HTTPException):
        # If already acknowledged or interaction expired, use followup
        pass

    try:
        # Rate limiting check
        if not RateLimiter.check_rate_limit(interaction.user.id, 'download', BotConfig.MAX_DOWNLOADS_PER_HOUR):
            remaining = RateLimiter.get_remaining_actions(interaction.user.id, 'download', BotConfig.MAX_DOWNLOADS_PER_HOUR)
            await interaction.followup.send(
                f"❌ Rate limit exceeded! You can download {BotConfig.MAX_DOWNLOADS_PER_HOUR} files per hour. "
                f"Try again in {remaining} minutes.", 
                ephemeral=True
            )
            return

        # Enhanced file ID validation
        if not BotConfig.validate_input('file_id', file_id):
            await interaction.followup.send(
                "❌ Invalid file ID format! Use only letters, numbers, and hyphens.", 
                ephemeral=True
            )
            return

        # Find file by partial ID
        async with aiosqlite.connect(BotConfig.DATABASE_NAME) as db:
            async with db.execute(
                "SELECT * FROM files WHERE id LIKE ? AND is_active = 1", 
                (f"{file_id}%",)
            ) as cursor:
                files = await cursor.fetchall()

        if not files:
            await interaction.followup.send("❌ File not found! Please check the file ID.", ephemeral=True)
            return

        if len(files) > 1:
            file_list = "\n".join([f"`{f[0][:8]}` - {f[2]}-{f[3]}-{f[4]}" for f in files[:5]])
            await interaction.followup.send(
                f"❌ Multiple files found with that ID. Please be more specific:\n{file_list}",
                ephemeral=True
            )
            return

        file_data = files[0]
        # Handle the correct schema with all 14 fields
        full_file_id, original_name, course, lecture, taker, uploader_id, uploader_name, upload_date, size, file_path, file_hash, is_active, download_count, last_downloaded = file_data

        # Check if file exists
        if not os.path.exists(file_path):
            await interaction.followup.send("❌ File not found on server! Please contact an administrator.", ephemeral=True)
            return

        # Verify file integrity if hash exists
        if file_hash:
            try:
                with open(file_path, 'rb') as f:
                    current_hash = hashlib.sha256(f.read()).hexdigest()
                if current_hash != file_hash:
                    logger.warning(f"File integrity check failed for {full_file_id}")
                    await interaction.followup.send("❌ File integrity check failed. Please contact an administrator.", ephemeral=True)
                    return
            except Exception as e:
                logger.warning(f"Could not verify file hash for {full_file_id}: {e}")

        # Apply enhanced watermark
        try:
            watermarked_pdf = await bot.apply_watermark_to_pdf(file_path, interaction.user.name)
        except Exception as e:
            logger.error(f"Watermark error for {full_file_id}: {e}")
            await interaction.followup.send("❌ Error processing file. Please try again.", ephemeral=True)
            return

        # Create final filename
        safe_course = bot.sanitize_filename(course, 20)
        safe_lecture = bot.sanitize_filename(lecture, 10)
        safe_taker = bot.sanitize_filename(taker, 20)
        final_filename = f"{safe_course}-{safe_lecture}-{safe_taker}_watermarked.pdf"

        # Enhanced download logging
        async with aiosqlite.connect(BotConfig.DATABASE_NAME) as db:
            # Log download
            await db.execute("""
                INSERT INTO download_logs (file_id, downloader_id, downloader_username, download_source)
                VALUES (?, ?, ?, ?)
            """, (full_file_id, interaction.user.id, interaction.user.name, 'bot'))
            
            # Update download count and last downloaded timestamp
            await db.execute("""
                UPDATE files SET download_count = download_count + 1, last_downloaded = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (full_file_id,))
            
            await db.commit()

        # Send file
        discord_file = discord.File(
            watermarked_pdf, 
            filename=final_filename,
            description="Watermarked PDF note"
        )

        embed = discord.Embed(
            title="📥 Download Ready",
            color=discord.Color.green(),
            description=f"**File:** {final_filename}\n**Course:** {course}\n**Lecture:** {lecture}\n**Note Taker:** {taker}"
        )
        embed.add_field(name="Original Uploader", value=uploader_name, inline=True)
        embed.add_field(name="Upload Date", value=upload_date[:10], inline=True)
        embed.add_field(name="Download Count", value=str(download_count + 1), inline=True)
        embed.set_footer(text="⚠️ This file has been watermarked with your username and download timestamp.")

        await interaction.followup.send(embed=embed, file=discord_file, ephemeral=True)
        logger.info(f"File downloaded: {final_filename} by {interaction.user} ({interaction.user.id})")

    except Exception as e:
        logger.error(f"Download error for user {interaction.user}: {e}")
        await interaction.followup.send("❌ An error occurred during download. Please try again.", ephemeral=True)

# Search command
@bot.tree.command(name="search", description="Search for notes by keyword")
@app_commands.describe(keyword="Search keyword (searches course code, lecture number, and note taker)")
async def search_files(interaction: discord.Interaction, keyword: str):
    await interaction.response.defer()

    try:
        search_term = f"%{keyword}%"

        async with aiosqlite.connect(BotConfig.DATABASE_NAME) as db:
            async with db.execute("""
                SELECT * FROM files 
                WHERE is_active = 1 AND (
                    course_code LIKE ? OR 
                    lecture_number LIKE ? OR 
                    note_taker LIKE ? OR
                    original_filename LIKE ?
                )
                ORDER BY course_code, lecture_number
            """, (search_term, search_term, search_term, search_term)) as cursor:
                files = await cursor.fetchall()

        if not files:
            await interaction.followup.send(f"🔍 No files found for keyword: **{keyword}**")
            return

        # Use pagination view for search results
        view = BrowseView(files)
        embed = view.get_embed()
        embed.title = f"🔍 Search Results for: {keyword}"

        await interaction.followup.send(embed=embed, view=view)

    except Exception as e:
        logger.error(f"Search error for user {interaction.user}: {e}")
        await interaction.followup.send("❌ An error occurred during search.", ephemeral=True)

# Admin commands group with enhanced functionality
class AdminCommands(commands.GroupCog, name="admin"):
    def __init__(self, bot):
        self.bot = bot
        # Properly initialize GroupCog so the group registers and is visible
        try:
            super().__init__(
                group_name="admin",
                description="Administrator commands",
                guild_only=True,
                default_permissions=discord.Permissions(administrator=True),
            )
        except Exception:
            # Fallback for older discord.py where kwargs might differ
            super().__init__()

    def is_admin(self, interaction: discord.Interaction) -> bool:
        """Check if user has admin permissions"""
        return interaction.user.guild_permissions.administrator

    async def log_admin_action(self, admin_id: int, admin_username: str, action: str, target_file_id: str = None, details: str = None):
        """Log admin actions"""
        async with aiosqlite.connect(BotConfig.DATABASE_NAME) as db:
            await db.execute("""
                INSERT INTO admin_logs (admin_id, admin_username, action, target_file_id, details)
                VALUES (?, ?, ?, ?, ?)
            """, (admin_id, admin_username, action, target_file_id, details))
            await db.commit()

    @app_commands.command(name="delete", description="Delete a file (Admin only)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @app_commands.describe(file_id="File ID to delete")
    async def delete_file(self, interaction: discord.Interaction, file_id: str):
        if not self.is_admin(interaction):
            await interaction.response.send_message("❌ Admin permissions required!", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            clean_file_id = "".join(c for c in file_id if c.isalnum() or c == "-")[:36]

            async with aiosqlite.connect(BotConfig.DATABASE_NAME) as db:
                # Get file info
                async with db.execute(
                    "SELECT * FROM files WHERE id LIKE ? AND is_active = 1", 
                    (f"{clean_file_id}%",)
                ) as cursor:
                    files = await cursor.fetchall()

                if not files:
                    await interaction.followup.send("❌ File not found!", ephemeral=True)
                    return

                if len(files) > 1:
                    file_list = "\n".join([f"`{f[0][:8]}` - {f[2]}-{f[3]}-{f[4]}" for f in files[:5]])
                    await interaction.followup.send(
                        f"❌ Multiple files found. Please be more specific:\n{file_list}",
                        ephemeral=True
                    )
                    return

                file_data = files[0]
                # Align with current schema (14 columns)
                (
                    full_file_id,
                    original_name,
                    course,
                    lecture,
                    taker,
                    uploader_id,
                    uploader_name,
                    upload_date,
                    size,
                    file_path,
                    file_hash,
                    is_active,
                    download_count,
                    last_downloaded,
                ) = file_data

                # Soft delete (mark as inactive)
                await db.execute("UPDATE files SET is_active = 0 WHERE id = ?", (full_file_id,))
                await db.commit()

                # Log admin action
                await self.log_admin_action(
                    interaction.user.id, 
                    interaction.user.name, 
                    "DELETE_FILE", 
                    full_file_id,
                    f"Deleted {course}-{lecture}-{taker}"
                )

                embed = discord.Embed(
                    title="✅ File Deleted",
                    color=discord.Color.red(),
                    description=f"**File:** {course}-{lecture}-{taker}\n**Uploader:** {uploader_name}\n**Upload Date:** {upload_date[:10]}"
                )
                embed.set_footer(text=f"Action performed by {interaction.user.name}")

                await interaction.followup.send(embed=embed)
                logger.info(f"File soft-deleted by admin {interaction.user}: {full_file_id}")

        except Exception as e:
            logger.error(f"Delete error by admin {interaction.user}: {e}")
            await interaction.followup.send("❌ An error occurred during deletion.", ephemeral=True)

    @app_commands.command(name="logs", description="View download logs (Admin only)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @app_commands.describe(file_id="File ID to view logs for (optional)", limit="Number of logs to show (1-50)")
    async def view_logs(self, interaction: discord.Interaction, file_id: Optional[str] = None, limit: Optional[int] = 20):
        if not self.is_admin(interaction):
            await interaction.response.send_message("❌ Admin permissions required!", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            # Validate limit
            limit = max(1, min(limit or 20, 50))

            query = """
                SELECT dl.*, f.course_code, f.lecture_number, f.note_taker, f.uploader_username
                FROM download_logs dl
                JOIN files f ON dl.file_id = f.id
            """
            params = []

            if file_id:
                clean_file_id = "".join(c for c in file_id if c.isalnum() or c == "-")[:36]
                query += " WHERE f.id LIKE ?"
                params.append(f"{clean_file_id}%")

            query += f" ORDER BY dl.download_date DESC LIMIT {limit}"

            async with aiosqlite.connect(BotConfig.DATABASE_NAME) as db:
                async with db.execute(query, params) as cursor:
                    logs = await cursor.fetchall()

            if not logs:
                await interaction.followup.send("📋 No download logs found.")
                return

            embed = discord.Embed(
                title="📋 Download Logs",
                color=discord.Color.orange(),
                description=f"Recent downloads ({len(logs)} entries)"
            )

            for log in logs[:15]:  # Show max 15 in embed
                log_id, file_id_log, downloader_id, username, download_date, ip_hash, course, lecture, taker, uploader = log
                embed.add_field(
                    name=f"{course}-{lecture}-{taker}",
                    value=f"👤 **Downloaded by:** {username}\n📤 **Uploader:** {uploader}\n📅 **Date:** {download_date[:16]}\n🆔 **File ID:** `{file_id_log[:8]}`",
                    inline=True
                )

            if len(logs) > 15:
                embed.set_footer(text=f"Showing 15 of {len(logs)} logs")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Logs error by admin {interaction.user}: {e}")
            await interaction.followup.send("❌ An error occurred while fetching logs.", ephemeral=True)

    @app_commands.command(name="stats", description="View bot statistics (Admin only)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def view_stats(self, interaction: discord.Interaction):
        if not self.is_admin(interaction):
            await interaction.response.send_message("❌ Admin permissions required!", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            async with aiosqlite.connect(BotConfig.DATABASE_NAME) as db:
                # Get file statistics
                async with db.execute("SELECT COUNT(*) FROM files WHERE is_active = 1") as cursor:
                    active_files = (await cursor.fetchone())[0]

                async with db.execute("SELECT COUNT(*) FROM files WHERE is_active = 0") as cursor:
                    deleted_files = (await cursor.fetchone())[0]

                async with db.execute("SELECT COUNT(*) FROM download_logs") as cursor:
                    total_downloads = (await cursor.fetchone())[0]

                # Get top uploaders
                async with db.execute("""
                    SELECT uploader_username, COUNT(*) as upload_count 
                    FROM files WHERE is_active = 1 
                    GROUP BY uploader_username 
                    ORDER BY upload_count DESC 
                    LIMIT 5
                """) as cursor:
                    top_uploaders = await cursor.fetchall()

                # Get top downloaded files
                async with db.execute("""
                    SELECT f.course_code, f.lecture_number, f.note_taker, COUNT(dl.id) as download_count
                    FROM files f
                    LEFT JOIN download_logs dl ON f.id = dl.file_id
                    WHERE f.is_active = 1
                    GROUP BY f.id
                    ORDER BY download_count DESC
                    LIMIT 5
                """) as cursor:
                    top_files = await cursor.fetchall()

            embed = discord.Embed(
                title="📊 Bot Statistics",
                color=discord.Color.gold(),
                description="Current server statistics"
            )

            embed.add_field(
                name="📁 Files",
                value=f"**Active:** {active_files}\n**Deleted:** {deleted_files}\n**Total:** {active_files + deleted_files}",
                inline=True
            )

            embed.add_field(
                name="📥 Downloads",
                value=f"**Total:** {total_downloads}\n**Avg per file:** {total_downloads / max(active_files, 1):.1f}",
                inline=True
            )

            embed.add_field(
                name="👥 Users",
                value=f"**Active uploaders:** {len(top_uploaders)}",
                inline=True
            )

            if top_uploaders:
                uploader_text = "\n".join([f"{name}: {count}" for name, count in top_uploaders])
                embed.add_field(
                    name="🏆 Top Uploaders",
                    value=uploader_text,
                    inline=True
                )

            if top_files:
                files_text = "\n".join([f"{course}-{lecture}: {count} downloads" for course, lecture, taker, count in top_files])
                embed.add_field(
                    name="📈 Most Downloaded",
                    value=files_text,
                    inline=True
                )

            embed.set_footer(text=f"Generated for {interaction.user.name}")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Stats error by admin {interaction.user}: {e}")
            await interaction.followup.send("❌ An error occurred while fetching statistics.", ephemeral=True)

    @app_commands.command(name="reset_stats", description="Reset download counters and clear logs (Admin only)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def reset_stats(self, interaction: discord.Interaction):
        """Reset per-file download counters and clear logs/rate limits.
        This does not delete files; it only clears analytics.
        """
        if not self.is_admin(interaction):
            await interaction.response.send_message("❌ Admin permissions required!", ephemeral=True)
            return

        # Acknowledge quickly and keep response private
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        try:
            async with aiosqlite.connect(BotConfig.DATABASE_NAME) as db:
                # Reset counters in files table
                await db.execute("UPDATE files SET download_count = 0, last_downloaded = NULL")
                # Clear logs
                await db.execute("DELETE FROM download_logs")
                await db.execute("DELETE FROM admin_logs")
                # Clear rate limit buckets
                await db.execute("DELETE FROM rate_limits")
                await db.commit()

            await self.log_admin_action(
                interaction.user.id,
                interaction.user.name,
                "RESET_STATS",
                None,
                "Cleared download counters, logs, and rate limits"
            )

            embed = discord.Embed(
                title="🧹 Stats Reset",
                color=discord.Color.green(),
                description="Download counters set to 0 and logs cleared."
            )
            embed.set_footer(text=f"Action performed by {interaction.user.name}")

            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"Admin {interaction.user} reset statistics and cleared logs")

        except Exception as e:
            logger.error(f"Reset stats error by admin {interaction.user}: {e}")
            await interaction.followup.send("❌ Failed to reset stats.", ephemeral=True)

# Add admin commands to bot
async def setup_admin_commands():
    # Remove any existing admin group to avoid duplicates when reloading
    try:
        existing = bot.get_cog("admin")
        if existing:
            await bot.remove_cog("admin")
    except Exception:
        pass

    await bot.add_cog(AdminCommands(bot))
    # Ensure newly added group commands are registered
    try:
        # Prefer per-guild sync for faster propagation
        if bot.guilds:
            for guild in bot.guilds:
                await bot.tree.sync(guild=guild)
                logger.info(f"Synced admin commands for guild {guild.name} ({guild.id})")
        else:
            await bot.tree.sync()
            logger.info("Synced command tree globally after registering admin commands")
    except Exception as e:
        logger.error(f"Failed to sync command tree: {e}")

# Enhanced help command
@bot.tree.command(name="help", description="Show help information")
async def help_command(interaction: discord.Interaction):
    # Send immediately (no defer) to avoid Unknown interaction timeouts
    embed = discord.Embed(
        title="🤖 Ironini Ringatoni Help",
        color=discord.Color.red(),
        description="Wagwan gang I am Ironini Ringatoni a bot with secure PDF watermarking, course reviews and shi"
    )

    embed.add_field(
        name="📤 Upload Notes",
        value="`/upload` - Upload a PDF note file\n**Requires:** file, course_code, lecture_number, note_taker\n**Example:** `/upload file:notes.pdf course_code:SYSC2006 lecture_number:L1 note_taker:alice99`",
        inline=False
    )

    embed.add_field(
        name="🔍 Browse & Search",
        value="`/browse` - Browse all notes (with filters)\n`/search` - Search by keyword\n**Optional filters:** course_code, note_taker\n`/course` - Show info about an engineering course",
        inline=False
    )

    embed.add_field(
        name="📥 Download Notes",
        value="`/download` - Download a watermarked note\n**Requires:** file_id (first 8 characters)\n**Example:** `/download file_id:a1b2c3d4`",
        inline=False
    )

    # Migrated utility/fun commands
    embed.add_field(
        name="🎉 Dope/fun commands",
        value="`/advice` `/kanye` `/hi` `/activatefreakmode`",
        inline=False
    )

    if interaction.user.guild_permissions.administrator:
        embed.add_field(
            name="🔧 Admin Commands",
            value="`/admin delete` - Delete a file\n`/admin logs` - View download logs\n`/admin stats` - View bot statistics\n`/admin reset_stats` - Clear counters and logs",
            inline=False
        )

    embed.add_field(
        name="ℹ️ File Requirements",
        value=f"• **Format:** PDF only\n• **Max Size:** {BotConfig.MAX_FILE_SIZE / (1024*1024):.0f}MB",
        inline=False
    )

    try:
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception:
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception:
            pass

# ===== Migrated fun/utility commands (slash versions) =====
@bot.tree.command(name="advice", description="Get a random piece of advice")
async def advice_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    import requests
    try:
        resp = requests.get("https://api.adviceslip.com/advice", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            advice = data.get("slip", {}).get("advice", "No advice found.")
            await interaction.followup.send(f"🤓 Advice: {advice}")
        else:
            await interaction.followup.send("Failed to fetch advice. Please try again later.")
    except Exception:
        await interaction.followup.send("Failed to fetch advice. Please try again later.")

@bot.tree.command(name="kanye", description="Get a random Kanye West quote")
async def kanye_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    import requests
    try:
        resp = requests.get("https://api.kanye.rest/", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            quote = data.get("quote", "No quote found.")
            embed = discord.Embed(
                title="Kanye West Quote",
                description=f"\"{quote}\"",
                color=discord.Color.gold()
            )
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("Failed to fetch a Kanye West quote. Please try again later.")
    except Exception:
        await interaction.followup.send("Failed to fetch a Kanye West quote. Please try again later.")

@bot.tree.command(name="hi", description="Say hi with an embed")
async def hi_cmd(interaction: discord.Interaction):
    kshawty_photo = "https://i.imgur.com/lyVAVQm.png"
    embed = discord.Embed(
        title="Wasgood",
        description="I am kshawtybot",
        color=discord.Color.yellow()
    )
    embed.set_image(url=kshawty_photo)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="activatefreakmode", description="Activate freak mode with a GIF")
async def activatefreakmode_cmd(interaction: discord.Interaction):
    gif_url = "https://media.tenor.com/fBUCaV_A6zEAAAAM/tony-stark-jarvis.gif"
    embed = discord.Embed(
        title="FREAK MODE ACTIVATED!🗣️🔥",
        description="JARVIS LESGET FREAKYY😱",
        color=discord.Color.red()
    )
    embed.set_image(url=gif_url)
    await interaction.response.send_message(embed=embed)



@bot.tree.command(name="course", description="Show info about an engineering course")
@app_commands.describe(course_code="Course code (e.g., ECOR1048)")
async def course_cmd(interaction: discord.Interaction, course_code: str):
    await interaction.response.defer()
    try:
        # Load JSON data from local file
        with open('courses.json', 'r') as f:
            courses = json.load(f)

        key = course_code.lower()
        if key not in courses:
            await interaction.followup.send("Course not found (or not added yet).")
            return

        course = courses[key]
        embed = discord.Embed(
            title=f"{course_code.upper()}: {course['name']}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Year", value=course.get('year', '-'), inline=False)
        embed.add_field(name="Rating", value=course.get('review', '-'), inline=False)
        embed.add_field(name="Notes", value=course.get('notes', '-'), inline=False)
        await interaction.followup.send(embed=embed)
    except Exception:
        await interaction.followup.send("Failed to load course info. Please try again later.")

# Bot events
@bot.event
async def on_ready():
    print(f'🤖 {bot.user} has connected to Discord!')
    print(f'📊 Bot is active in {len(bot.guilds)} guild(s)')
    await setup_admin_commands()
    # Perform a hard resync to ensure commands are up to date
    try:
        await hard_resync_commands()
    except Exception as e:
        logger.error(f"Hard resync failed: {e}")
    # Log registered command names to verify presence of help/admin/etc.
    try:
        command_names = [cmd.name for cmd in bot.tree.get_commands()]
        logger.info(f"Registered global commands: {command_names}")
        for guild in bot.guilds:
            guild_cmds = [cmd.name for cmd in bot.tree.get_commands(guild=guild)]
            logger.info(f"Registered commands for guild {guild.name} ({guild.id}): {guild_cmds}")
    except Exception as e:
        logger.error(f"Failed listing registered commands: {e}")
    logger.info(f"Bot ready: {bot.user} in {len(bot.guilds)} guilds")

async def hard_resync_commands():
    """Clear and re-sync app commands globally and per-guild.
    This helps when command definitions changed or permissions/groups didn't propagate.
    """
    # Do NOT clear local tree; just sync to Discord so decorated commands register
    try:
        synced = await bot.tree.sync()
        logger.info(f"Hard resync: synced {len(synced)} global command(s)")
    except Exception as e:
        logger.error(f"Hard resync (global) failed: {e}")

    for guild in bot.guilds:
        try:
            synced_guild = await bot.tree.sync(guild=guild)
            logger.info(f"Hard resync: synced {len(synced_guild)} command(s) for guild {guild.name} ({guild.id})")
        except Exception as e:
            logger.error(f"Hard resync failed for guild {guild.name} ({guild.id}): {e}")

@bot.event
async def on_command_error(ctx, error):
    logger.error(f"Command error in {ctx.guild}: {error}")

@bot.event
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    logger.error(f"Slash command error: {error}")
    if not interaction.response.is_done():
        await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)

# Run bot
if __name__ == "__main__":
    try:
        bot.run(BotConfig.TOKEN)
    except Exception as e:
        logger.critical(f"Failed to start bot: {e}")
        print(f"❌ Failed to start bot: {e}")
        print("Please check your configuration and token.")