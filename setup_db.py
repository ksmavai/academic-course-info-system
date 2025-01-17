import sqlite3

conn = sqlite3.connect('discord_bot.db')
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS course_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_code TEXT NOT NULL,
    user_id TEXT NOT NULL,
    review TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    UNIQUE(course_code, user_id) -- Ensure one review per user per course
);
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS elective_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    suggestion TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
''')

conn.commit()
conn.close()

print("Database and tables are created successfully!")
