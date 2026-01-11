import os
import re
from dotenv import load_dotenv
from typing import List, Optional

# Load environment variables
load_dotenv()

class BotConfig:
    """Bot configuration settings with comprehensive validation"""

    # ==============================================
    # DISCORD SETTINGS
    # ==============================================
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')

    # ==============================================
    # FILE SETTINGS
    # ==============================================
    MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE_MB', 10)) * 1024 * 1024  # Convert MB to bytes
    ALLOWED_EXTENSIONS = ['.pdf']
    MAX_FILES_PER_USER = int(os.getenv('MAX_FILES_PER_USER', 100))

    # ==============================================
    # STORAGE DIRECTORIES
    # ==============================================
    FILES_DIR = 'files'
    WATERMARKED_DIR = 'watermarked'
    LOGS_DIR = 'logs'
    BACKUP_DIR = 'backups'

    # ==============================================
    # WATERMARK SETTINGS
    # ==============================================
    WATERMARK_OPACITY = float(os.getenv('WATERMARK_OPACITY', 0.3))
    WATERMARK_FONT_SIZE = int(os.getenv('WATERMARK_FONT_SIZE', 24))
    WATERMARK_SMALL_FONT_SIZE = int(os.getenv('WATERMARK_SMALL_FONT_SIZE', 12))
    WATERMARK_COLOR_RED = float(os.getenv('WATERMARK_COLOR_RED', 0.7))
    WATERMARK_COLOR_GREEN = float(os.getenv('WATERMARK_COLOR_GREEN', 0.7))
    WATERMARK_COLOR_BLUE = float(os.getenv('WATERMARK_COLOR_BLUE', 0.7))

    # ==============================================
    # DATABASE SETTINGS
    # ==============================================
    DATABASE_NAME = 'notes_database.db'
    DATABASE_BACKUP_INTERVAL_HOURS = int(os.getenv('DATABASE_BACKUP_INTERVAL_HOURS', 24))
    DATABASE_CLEANUP_DAYS = int(os.getenv('DATABASE_CLEANUP_DAYS', 90))

    # ==============================================
    # RATE LIMITING SETTINGS
    # ==============================================
    MAX_UPLOADS_PER_HOUR = int(os.getenv('MAX_UPLOADS_PER_HOUR', 20))
    MAX_DOWNLOADS_PER_HOUR = int(os.getenv('MAX_DOWNLOADS_PER_HOUR', 50))
    ENABLE_RATE_LIMITING = os.getenv('ENABLE_RATE_LIMITING', 'true').lower() == 'true'

    # ==============================================
    # SECURITY SETTINGS
    # ==============================================
    ENABLE_IP_LOGGING = os.getenv('ENABLE_IP_LOGGING', 'false').lower() == 'true'
    CLEANUP_TEMP_FILES = os.getenv('CLEANUP_TEMP_FILES', 'true').lower() == 'true'

    # ==============================================
    # ADMIN SETTINGS
    # ==============================================
    ADMIN_ROLE_NAME = os.getenv('ADMIN_ROLE_NAME', 'Admin')
    MODERATOR_ROLE_NAME = os.getenv('MODERATOR_ROLE_NAME', 'Moderator')

    # ==============================================
    # FEATURE FLAGS
    # ==============================================
    ENABLE_SEARCH = os.getenv('ENABLE_SEARCH', 'true').lower() == 'true'
    ENABLE_BULK_OPERATIONS = os.getenv('ENABLE_BULK_OPERATIONS', 'true').lower() == 'true'
    ENABLE_STATISTICS = os.getenv('ENABLE_STATISTICS', 'true').lower() == 'true'

    # ==============================================
    # PERFORMANCE SETTINGS
    # ==============================================
    CACHE_SIZE_MB = int(os.getenv('CACHE_SIZE_MB', 100))
    MAX_CONCURRENT_UPLOADS = int(os.getenv('MAX_CONCURRENT_UPLOADS', 5))
    MAX_CONCURRENT_DOWNLOADS = int(os.getenv('MAX_CONCURRENT_DOWNLOADS', 10))

    # ==============================================
    # LOGGING SETTINGS
    # ==============================================
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    ENABLE_METRICS = os.getenv('ENABLE_METRICS', 'true').lower() == 'true'
    LOG_RETENTION_DAYS = int(os.getenv('LOG_RETENTION_DAYS', 30))

    # ==============================================
    # VALIDATION PATTERNS
    # ==============================================
    COURSE_CODE_PATTERN = re.compile(r'^[A-Z]{3,4}[0-9]{4}$')
    LECTURE_NUMBER_PATTERN = re.compile(r'^[A-Za-z0-9\-_]{1,10}$')
    NOTE_TAKER_PATTERN = re.compile(r'^[A-Za-z0-9\-_]{1,30}$')
    FILE_ID_PATTERN = re.compile(r'^[a-f0-9\-]{8,36}$')

    @classmethod
    def validate_all(cls) -> List[str]:
        """Comprehensive configuration validation"""
        errors = []

        # Required settings
        if not cls.TOKEN:
            errors.append("DISCORD_BOT_TOKEN environment variable is required")
        elif not cls.TOKEN.startswith(('MT', 'OD', 'Nz')):
            errors.append("DISCORD_BOT_TOKEN appears to be invalid (should start with MT, OD, or Nz)")

        # File size validation
        if cls.MAX_FILE_SIZE <= 1024 * 1024:  # 1MB minimum
            errors.append("MAX_FILE_SIZE_MB must be at least 1MB")
        if cls.MAX_FILE_SIZE > 100 * 1024 * 1024:  # 100MB maximum
            errors.append("MAX_FILE_SIZE_MB cannot exceed 100MB")

        # Watermark settings validation
        if not 0 < cls.WATERMARK_OPACITY < 1:
            errors.append("WATERMARK_OPACITY must be between 0 and 1")
        
        if cls.WATERMARK_FONT_SIZE < 8 or cls.WATERMARK_FONT_SIZE > 72:
            errors.append("WATERMARK_FONT_SIZE must be between 8 and 72")
        
        if cls.WATERMARK_SMALL_FONT_SIZE < 6 or cls.WATERMARK_SMALL_FONT_SIZE > 24:
            errors.append("WATERMARK_SMALL_FONT_SIZE must be between 6 and 24")

        # Color validation
        for color_name, color_value in [('RED', cls.WATERMARK_COLOR_RED), 
                                       ('GREEN', cls.WATERMARK_COLOR_GREEN), 
                                       ('BLUE', cls.WATERMARK_COLOR_BLUE)]:
            if not 0 <= color_value <= 1:
                errors.append(f"WATERMARK_COLOR_{color_name} must be between 0 and 1")

        # Rate limiting validation
        if cls.MAX_UPLOADS_PER_HOUR < 1 or cls.MAX_UPLOADS_PER_HOUR > 1000:
            errors.append("MAX_UPLOADS_PER_HOUR must be between 1 and 1000")
        
        if cls.MAX_DOWNLOADS_PER_HOUR < 1 or cls.MAX_DOWNLOADS_PER_HOUR > 1000:
            errors.append("MAX_DOWNLOADS_PER_HOUR must be between 1 and 1000")

        # Database settings validation
        if cls.DATABASE_BACKUP_INTERVAL_HOURS < 1 or cls.DATABASE_BACKUP_INTERVAL_HOURS > 168:  # Max 1 week
            errors.append("DATABASE_BACKUP_INTERVAL_HOURS must be between 1 and 168")
        
        if cls.DATABASE_CLEANUP_DAYS < 1 or cls.DATABASE_CLEANUP_DAYS > 365:
            errors.append("DATABASE_CLEANUP_DAYS must be between 1 and 365")

        # Performance settings validation
        if cls.MAX_CONCURRENT_UPLOADS < 1 or cls.MAX_CONCURRENT_UPLOADS > 20:
            errors.append("MAX_CONCURRENT_UPLOADS must be between 1 and 20")
        
        if cls.MAX_CONCURRENT_DOWNLOADS < 1 or cls.MAX_CONCURRENT_DOWNLOADS > 50:
            errors.append("MAX_CONCURRENT_DOWNLOADS must be between 1 and 50")

        # Log retention validation
        if cls.LOG_RETENTION_DAYS < 1 or cls.LOG_RETENTION_DAYS > 365:
            errors.append("LOG_RETENTION_DAYS must be between 1 and 365")

        return errors

    @classmethod
    def validate(cls):
        """Legacy validation method for backward compatibility"""
        errors = cls.validate_all()
        if errors:
            raise ValueError("Configuration validation failed:\n" + "\n".join(f"- {error}" for error in errors))

    @classmethod
    def get_watermark_color(cls) -> tuple:
        """Get watermark color as RGB tuple"""
        return (cls.WATERMARK_COLOR_RED, cls.WATERMARK_COLOR_GREEN, cls.WATERMARK_COLOR_BLUE)

    @classmethod
    def validate_input(cls, field: str, value: str) -> bool:
        """Validate user input against patterns"""
        if field == 'course_code':
            return bool(cls.COURSE_CODE_PATTERN.match(value))
        elif field == 'lecture_number':
            return bool(cls.LECTURE_NUMBER_PATTERN.match(value))
        elif field == 'note_taker':
            return bool(cls.NOTE_TAKER_PATTERN.match(value))
        elif field == 'file_id':
            return bool(cls.FILE_ID_PATTERN.match(value))
        return False