# academic course info system

you've probably seen how a lot of people share notes on studocu to get access to other notes. i have a carleton engineering server with thousands of students, and had the idea for students to share notes with one another seamlessly. however, i wanted to prevent students from using other students' notes for their own personal gain off websites like studocu.

so i made a discord bot for academic communities that helps students share notes securely with watermarking, get course information, and additionally chat with an AI that matches your vibe. built for carleton university but is adaptable to any school.

## 🚀 key features

*   **watermarked note sharing**: upload PDFs and share them with automatic watermarks containing the downloader's username and timestamp for accountability.
*   **course information**: browse and search course details from your university's catalog.
*   **ai chat**: an AI assistant that can match your texting style and personality. configure it however you want.
*   **smart web search**: automatically routes questions needing real-time info (weather, news, etc.) to web search.
*   **privacy-first**: all watermarking and processing happens locally.

## 🛠️ technologies

*   **python 3.8+**
*   **discord.py**
*   **pypdf / reportlab** (pdf watermarking)
*   **deepseek api** (ai chat)
*   **perplexity api** (web search)
*   **sqlite** (database)

## 🏃‍♂️ how to run

1. **clone the repo**
   ```bash
   git clone <your-repo-url>
   cd academic-student-system
   ```

2. **run setup**
   ```bash
   python3 setup.py
   ```
   or use the quick start:
   ```bash
   chmod +x quick_start.sh
   ./quick_start.sh
   ```

3. **configure your bot**
   - copy `.env.template` to `.env`
   - add your discord bot token
   - add your deepseek api key (required for ai chat)
   - optionally add perplexity api key for web search

4. **customize the ai personality** (optional)
   - create `personality_prompt.txt` with personality rules
   - create `style_prompt.txt` with vocabulary/slang preferences
   - the bot will load these automatically on startup

5. **start the bot**
   ```bash
   python3 run.py
   ```

## 📖 commands

there's a lot of silly other commands but below are the main ones

| command | description |
|---------|-------------|
| `/upload` | upload a pdf to share with the community |
| `/browse` | browse available notes by course |
| `/download` | download notes (automatically watermarked) |
| `/courses` | view course information |
| `@bot` | mention the bot to chat with the ai |

## 🎨 ai personality customization

create these files to customize how the ai responds:

**`personality_prompt.txt`** - define the vibe (example):
```
CRITICAL RULES:
1. Keep responses SHORT (5-20 words)
2. Refrain from using emojis
3. Be polite and chill, not overly formal
```

**`style_prompt.txt`** - define vocabulary (example):
```
SLANG & ABBREVIATIONS:
- use: u, bro, nah, fr, idk, lmao
SIGNATURE RESPONSES:
- real, true, W, same, bet
```

## 🔒 privacy & security

*   all pdf processing happens locally
*   watermarks include username + timestamp for accountability
*   no note content is sent to external servers
*   ai chat uses your configured api keys only

## 📄 license

MIT
