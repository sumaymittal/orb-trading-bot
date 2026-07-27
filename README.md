# Multi-Stock ORB Trading Bot

An automated trading bot that implements an Opening Range Breakout (ORB) strategy across multiple stocks. 

## Setup

1. **Install Dependencies**
   Make sure you have Python 3 installed. Then, install the required packages:
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Variables**
   This project uses environment variables to securely load credentials.
   - Copy `.env.example` to `.env`
   - Fill in your Telegram credentials in the `.env` file:
     ```
     TELEGRAM_BOT_TOKEN=your_bot_token_here
     TELEGRAM_CHAT_ID=your_chat_id_here
     ```
   
   *(Note: The `.env` file is included in `.gitignore` so your secrets will not be committed to Git.)*

3. **Access Token**
   The bot requires an access token to authenticate. You must place your token in a file named `access_token.txt` in the root of the project directory.

## Running the Bot

To start the bot, simply execute the main script:
```bash
python proto8.py
```
