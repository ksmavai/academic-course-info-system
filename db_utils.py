import sqlite3
from datetime import datetime

#Adding course reviews function
def add_course_review(course_code, user_id, review):
    conn = sqlite3.connect('discord_bot.db')
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        cursor.execute('''
        INSERT INTO course_reviews (course_code, user_id, review, timestamp)
        VALUES (?, ?, ?, ?)
        ''', (course_code.lower(), user_id, review, timestamp))
        conn.commit()
        return "Your course review's been added successfully! :D"
    except sqlite3.IntegrityError:
        return "You already submitted a review for this course!"
    finally:
        conn.close()

# Fetching course reviews function
def fetch_course_reviews(course_code):
    conn = sqlite3.connect('discord_bot.db')
    cursor = conn.cursor()

    cursor.execute('''
    SELECT review, timestamp FROM course_reviews WHERE course_code = ?
    ''', (course_code.lower(),))
    reviews = cursor.fetchall()
    conn.close()

    return reviews

# Adding elective suggestions function
def add_elective_suggestion(category, suggestion):
    conn = sqlite3.connect('discord_bot.db')
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute('''
    INSERT INTO elective_suggestions (category, suggestion, timestamp)
    VALUES (?, ?, ?)
    ''', (category.lower(), suggestion, timestamp))
    conn.commit()
    conn.close()

    return "Elective suggestion has been added successfully!"

# Fetching elective suggestions function
def fetch_elective_suggestions(category):
    conn = sqlite3.connect('discord_bot.db')
    cursor = conn.cursor()

    cursor.execute('''
    SELECT suggestion, timestamp FROM elective_suggestions WHERE category = ?
    ''', (category.lower(),))
    suggestions = cursor.fetchall()
    conn.close()

    return suggestions