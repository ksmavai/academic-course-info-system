import discord
from discord.ext import commands
import json
import os
import requests
from dotenv import load_dotenv
import sqlite3
from datetime import datetime
from db_utils import add_course_review
from db_utils import add_elective_suggestion
from db_utils import fetch_elective_suggestions
import db_utils
from discord.ext import menus

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
WEATHERSTACK_API_KEY = os.getenv('WEATHERSTACK_API_KEY') # weatherstack api key

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='k!', intents=intents)

class ReviewsMenu(menus.ListPageSource):
    def __init__(self, data):
        super().__init__(data, per_page=1)

    async def format_page(self, menu, entry):
        embed = discord.Embed(
            title=f"Reviews for {entry['course_code'].upper()}",
            description=f'"{entry["review"]}"',
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Submitted on {entry['timestamp']}")
        return embed

class CustomMenuPages(menus.MenuPages):
    def __init__(self, source):
        super().__init__(source, clear_reactions_after=True)
    
class ElectivesMenu(menus.ListPageSource):
    def __init__(self, data):
        super().__init__(data, per_page=1)

    async def format_page(self, menu, entry):
        embed = discord.Embed(
            title=f"Suggestions for {entry['category']} Electives",
            description=f'"{entry["suggestion"]}"',
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Submitted on {entry['timestamp']}")
        return embed

@bot.check
async def restrict_from_general(ctx):
    general_channel_id = 1016303298145435658 
    bots_channel_id = 1235018088261353563

    if ctx.channel.id == general_channel_id:
        await ctx.send(f"Sorry, I cannot speak in this channel. Please choose another channel, such as the <#{1235018088261353563}> channel")
        return False
    return True

def load_courses():
    with open('courses.json', 'r') as f:
        return json.load(f)

courses = load_courses()

@bot.event
async def on_ready():
    print(f'{bot.user} is now running!')

@bot.command()
async def course(ctx, course_code: str):
    # Convert course code to lowercase for consistency
    course_code = course_code.lower()

    # Check if the course exists in the JSON data
    if course_code in courses:
        course = courses[course_code]
        
        # Create a Discord embed with the course info
        embed = discord.Embed(
            title=f"{course_code.upper()}: {course['name']}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Year", value=course['year'], inline=False)
        embed.add_field(name="Rating", value=course['review'], inline=False)
        embed.add_field(name="Notes", value=course['notes'], inline=False)
        
        await ctx.send(embed=embed)
    else:
        await ctx.send("Course not found (or I haven't added it yet oops)! Please check the course code.")

@bot.command(name="commands")
async def khelp(ctx):
    # Custom help command to list available commands
    embed = discord.Embed(
        title="Bot's commands!",
        description="Here are the available commands:",
        color=discord.Color.green()
    )

    embed.add_field(
        name="k!course [course_code]",
        value="Shows information about a specific course 👍🏽\nExample: k!course ecor1048",
        inline=False
    )
    embed.add_field(
        name="k!commands",
        value="You just typed this but anyway it lists all the commands this bot can do 🤖",
        inline=False
    )
    embed.add_field(
        name="k!elective <category> <recommendation>",
        value='Submit your recommendation for an elective (Science, Complementary, or Engineering)\n For "category" use either s, c, or eng\nExample: k!elective s "BIOL1902 is amazing!"',
        inline=False
    )
    embed.add_field(
        name="k!electives <category>",
        value='Shows recommendations for Science, Complementary, or Engineering electives\n For "category" use either s, c, or eng\nExample: "k!electives s" will display a list of science electives',
        inline=False
    )
    embed.add_field(
        name='k!review <course_code> "<review>"',
        value='Submit your review for any course you want\n Example: k!review ECOR1048 "Pretty hard course"',
        inline=False
    )
    embed.add_field(
        name="k!reviews <course_code>",
        value='Read reviews on any course you want (if there exist any)\n Example: k!reviews ECOR1056',
        inline=False
    )
    embed.add_field(
        name="k!weather",
        value="Find out about the weather in Ottawa!\n For another place just write k!weather [place_name]\nExample: k!weather Toronto",
        inline=False
    )
    
    await ctx.send(embed=embed)

# Function to fetch weather data from Weatherstack API
def get_weather(location):
    url = f"http://api.weatherstack.com/current?access_key={WEATHERSTACK_API_KEY}&query={location}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if "error" in data:
            return None, data["error"]["info"]
        return data, None
    else:
        return None, "Failed to fetch weather data. Please try again later."

@bot.command()
async def weather(ctx, *, location: str = "Ottawa"):
    """
    Fetch and display weather information for a given location.
    Defaults to Ottawa if no location is specified.
    """
    weather_data, error = get_weather(location)
    
    if error:
        await ctx.send(f"Error: {error}")
        return
    
    # Extract relevant weather information
    location_name = weather_data["location"]["name"]
    country = weather_data["location"]["country"]
    local_time = weather_data["location"]["localtime"]
    temperature = weather_data["current"]["temperature"]
    feels_like = weather_data["current"]["feelslike"]
    description = ", ".join(weather_data["current"]["weather_descriptions"])
    weather_icon = weather_data["current"]["weather_icons"][0]  # Get the first icon URL

    # Create an embed for the weather information
    embed = discord.Embed(
        title=f"Weather RIGHT NOW in {location_name}, {country}",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=weather_icon)  # Add the weather icon as a thumbnail
    embed.add_field(name="Time", value=local_time, inline=True)
    embed.add_field(name="Temperature", value=f"{temperature}°C", inline=True)
    embed.add_field(name="Feels Like", value=f"{feels_like}°C", inline=True)
    embed.add_field(name="Condition", value=description, inline=False)
    
    await ctx.send(embed=embed)

@bot.command()
async def review(ctx, course_code: str = None, *, review: str = None):

    if not course_code or not review:
        await ctx.send("Usage: `k!review <course_code> \"<your review>\"`")
        return

    user_id = str(ctx.author.id)
    result = add_course_review(course_code, user_id, review)
    
    await ctx.send(result)


@bot.command()
async def reviews(ctx, course_code: str = None):

    if not course_code:
        await ctx.send("Usage: `k!reviews <course_code>`")
        return

    conn = sqlite3.connect('discord_bot.db')
    cursor = conn.cursor()

    # Fetch all reviews for the given course code
    cursor.execute('SELECT review, timestamp FROM course_reviews WHERE course_code = ?', (course_code.lower(),))
    reviews = cursor.fetchall()
    conn.close()

    if not reviews:
        await ctx.send(f"No reviews found for `{course_code.upper()}`.")
        return

    # Format data for pagination
    review_data = [{"course_code": course_code.upper(), "review": r[0], "timestamp": r[1]} for r in reviews]

    # Create and start the pagination menu
    pages = ReviewsMenu(review_data)
    menu = CustomMenuPages(source=pages)
    
    await menu.start(ctx)

@bot.command()
async def elective(ctx, category: str = None, *, suggestion: str = None):

    if not category or not suggestion:
        await ctx.send("Usage: `k!elective <category> <recommendation>`\nCategories: `s` (Science), `c` (Complementary), or `eng` (Engineering).")
        return

    # Map shorthand to full names for display
    category_map = {"s": "Science", "c": "Complementary", "eng": "Engineering"}

    if category.lower() not in category_map:
        await ctx.send("Invalid category! Use one of the following: `s` (Science), `c` (Complementary), or `eng` (Engineering).")
        return

    # Insert the suggestion into the database
    conn = sqlite3.connect('discord_bot.db')
    cursor = conn.cursor()
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
    INSERT INTO elective_suggestions (category, suggestion, timestamp)
    VALUES (?, ?, ?)
    ''', (category.lower(), suggestion, timestamp))
    
    conn.commit()
    conn.close()

    # Respond with the full form of the category
    await ctx.send(f"Your suggestion has been submitted under `{category_map[category.lower()]}`!")

@bot.command()
async def electives(ctx, category: str = None):

    if not category:
        await ctx.send("Usage: `k!electives <category>`\nCategories: `s`, `c`, or `eng`.")
        return

    # Map shorthand to full names
    category_map = {"s": "Science", "c": "Complementary", "eng": "Engineering"}

    if category.lower() not in category_map:
        await ctx.send("Invalid category! Use one of the following: `s`, `c`, or `eng`.")
        return

    conn = sqlite3.connect('discord_bot.db')
    cursor = conn.cursor()

    # Fetch suggestions for the given category
    cursor.execute('SELECT suggestion, timestamp FROM elective_suggestions WHERE category = ?', (category.lower(),))
    suggestions = cursor.fetchall()
    
    conn.close()

    if not suggestions:
        await ctx.send(f"No suggestions found for `{category_map[category.lower()]}` electives.")
        return

    # Format data for pagination
    suggestion_data = [{"category": category_map[category.lower()], "suggestion": s[0], "timestamp": s[1]} for s in suggestions]

    # Create and start the pagination menu
    pages = ElectivesMenu(suggestion_data)
    menu = CustomMenuPages(source=pages)
    
    await menu.start(ctx)


# Run the bot
bot.run(TOKEN)