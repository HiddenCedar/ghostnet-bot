# Telegram Search Bot

A simple Telegram bot that lets users search the web for any topic directly from Telegram. The bot uses DuckDuckGo's HTML search page to fetch results (no API key required) and returns the top few links.

## Features
- Responds to `/start` and `/help` commands.
- Any text message is treated as a search query.
- Returns the top 3 results with titles and URLs.

## Setup
1. **Clone the repository** (or copy the files).
2. **Create a virtual environment** and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate   # on Windows use `venv\Scripts\activate`
   pip install -r requirements.txt
   ```
3. **Create a `.env` file** in the project root with your Telegram bot token:
   ```dotenv
   TELEGRAM_TOKEN=YOUR_TELEGRAM_BOT_TOKEN_HERE
   ```
   You can obtain a token by talking to [@BotFather](https://t.me/BotFather) on Telegram.
4. **Run the bot**:
   ```bash
   python bot.py
   ```
   The bot will start polling for updates.

## Usage
- Send `/start` to see a welcome message.
- Send any text (e.g., `Python web scraping`) and the bot will reply with the top search results.

## How it works
The bot performs a GET request to DuckDuckGo's HTML endpoint (`https://html.duckduckgo.com/html?q=<query>`), parses the returned HTML with BeautifulSoup, extracts the result titles and URLs, and sends them back to the user.

## License
MIT
