import re
import discord
from discord.ext import commands, tasks
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import asyncio
from datetime import datetime
import time
import os
import json

# Configuration
WHATSAPP_GROUP_NAME = "Your Group Name"  # Change this to your exact WhatsApp group name
DISCORD_BOT_TOKEN = "YOUR_DISCORD_BOT_TOKEN"  # Your Discord bot token
DISCORD_CHANNEL_ID = 123456789012345678  # Your Discord channel ID (as integer)

# Regular expression to find URLs
URL_PATTERN = re.compile(
    r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
)

# Track processed messages and sent links
processed_messages = set()
sent_links_history = set()  # Track ALL links ever sent to prevent duplicates
LINKS_HISTORY_FILE = "sent_links_history.json"

def load_link_history():
    """Load previously sent links from file"""
    global sent_links_history
    try:
        if os.path.exists(LINKS_HISTORY_FILE):
            with open(LINKS_HISTORY_FILE, 'r') as f:
                sent_links_history = set(json.load(f))
            print(f"📚 Loaded {len(sent_links_history)} previously sent links from history")
    except Exception as e:
        print(f"⚠️  Could not load link history: {e}")
        sent_links_history = set()

def save_link_history():
    """Save sent links to file"""
    try:
        with open(LINKS_HISTORY_FILE, 'w') as f:
            json.dump(list(sent_links_history), f)
    except Exception as e:
        print(f"⚠️  Could not save link history: {e}")

class WhatsAppMonitor:
    def __init__(self):
        self.driver = None
        self.is_logged_in = False
        
    def setup_driver(self):
        """Setup Chrome driver for WhatsApp Web"""
        chrome_options = Options()
        chrome_options.add_argument("--user-data-dir=./User_Data")  # Save session
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        # Remove headless mode so you can scan QR code
        # chrome_options.add_argument("--headless")
        
        print("Setting up Chrome driver...")
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )
        
    def login_whatsapp(self):
        """Open WhatsApp Web and wait for login"""
        print("Opening WhatsApp Web...")
        self.driver.get("https://web.whatsapp.com")
        
        print("\n" + "="*60)
        print("PLEASE SCAN THE QR CODE WITH YOUR PHONE")
        print("Waiting for WhatsApp Web to load...")
        print("="*60 + "\n")
        
        try:
            # Wait for the main chat list to appear (means we're logged in)
            WebDriverWait(self.driver, 120).until(
                EC.presence_of_element_located((By.XPATH, '//div[@id="pane-side"]'))
            )
            self.is_logged_in = True
            print("✅ Successfully logged into WhatsApp Web!")
            time.sleep(3)  # Give it a moment to fully load
            return True
        except Exception as e:
            print(f"❌ Failed to login: {e}")
            return False
    
    def open_group_chat(self):
        """Open the specific WhatsApp group"""
        try:
            print(f"Searching for group: {WHATSAPP_GROUP_NAME}")
            
            # Click on search box
            search_box = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]'))
            )
            search_box.click()
            time.sleep(1)
            search_box.send_keys(WHATSAPP_GROUP_NAME)
            time.sleep(2)
            
            # Click on the group from search results
            group = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, f'//span[@title="{WHATSAPP_GROUP_NAME}"]'))
            )
            group.click()
            time.sleep(2)
            print(f"✅ Opened group: {WHATSAPP_GROUP_NAME}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to open group: {e}")
            return False
    
    def get_recent_messages(self):
        """Get recent messages from the chat"""
        try:
            # Try multiple selectors for message containers (WhatsApp changes these often)
            messages = []
            
            # Try different selector strategies
            selectors = [
                '//div[contains(@class, "message-")]',
                '//div[@data-id]//div[contains(@class, "copyable-text")]/..',
                '//div[@role="row"]',
            ]
            
            for selector in selectors:
                try:
                    messages = self.driver.find_elements(By.XPATH, selector)
                    if len(messages) > 0:
                        print(f"Found {len(messages)} message elements using selector")
                        break
                except:
                    continue
            
            if not messages:
                print("⚠️ Could not find any message elements")
                return []
            
            recent_messages = []
            
            # Get last 10 messages
            for msg in messages[-10:]:
                try:
                    # Try multiple ways to get message text
                    text = ""
                    text_selectors = [
                        './/span[contains(@class, "selectable-text")]',
                        './/div[contains(@class, "copyable-text")]',
                        './/span[@dir="ltr"]',
                    ]
                    
                    for text_selector in text_selectors:
                        try:
                            text_elem = msg.find_element(By.XPATH, text_selector)
                            text = text_elem.text
                            if text:
                                break
                        except:
                            continue
                    
                    if not text:
                        continue
                    
                    # Get sender name
                    sender = "Unknown"
                    try:
                        # Try to get sender from data attribute
                        sender_elem = msg.find_element(By.XPATH, './/*[@data-pre-plain-text]')
                        sender_data = sender_elem.get_attribute('data-pre-plain-text')
                        if ']' in sender_data:
                            sender = sender_data.split(']')[1].strip()
                    except:
                        try:
                            # Try to get sender from span
                            sender_elem = msg.find_element(By.XPATH, './/span[@dir="auto"]')
                            sender = sender_elem.text
                        except:
                            # Check if it's an outgoing message
                            try:
                                if 'message-out' in msg.get_attribute('class'):
                                    sender = "You"
                            except:
                                sender = "You"
                    
                    # Get timestamp
                    timestamp = "Unknown"
                    try:
                        time_selectors = [
                            './/span[@data-testid="msg-time"]',
                            './/span[contains(@class, "msg-time")]',
                            './/div[@data-testid="msg-meta"]//span',
                        ]
                        for time_selector in time_selectors:
                            try:
                                time_elem = msg.find_element(By.XPATH, time_selector)
                                timestamp = time_elem.text
                                if timestamp:
                                    break
                            except:
                                continue
                    except:
                        pass
                    
                    # Create message ID based on text + sender to avoid duplicates
                    message_id = f"{sender}_{text[:50]}"
                    
                    recent_messages.append({
                        'id': message_id,
                        'sender': sender,
                        'text': text,
                        'timestamp': timestamp
                    })
                    
                    print(f"  📝 Message from {sender}: {text[:50]}...")
                    
                except Exception as e:
                    continue
            
            print(f"✅ Extracted {len(recent_messages)} messages")
            return recent_messages
            
        except Exception as e:
            print(f"❌ Error getting messages: {e}")
            return []
    
    def close(self):
        """Close the browser"""
        if self.driver:
            self.driver.quit()

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# WhatsApp monitor instance
wa_monitor = None

@bot.event
async def on_ready():
    print(f'\n✅ Discord bot logged in as {bot.user}')
    print(f'Ready to forward links to channel ID: {DISCORD_CHANNEL_ID}\n')
    
    # Load previously sent links
    load_link_history()
    
    # Scan last 10 messages on startup
    await scan_initial_messages()
    
    # Start the monitoring task
    if not monitor_whatsapp.is_running():
        monitor_whatsapp.start()

async def scan_initial_messages():
    """Scan and forward links from the last 10 messages on startup"""
    global wa_monitor, processed_messages, sent_links_history
    
    if wa_monitor is None or not wa_monitor.is_logged_in:
        return
    
    print("🔍 Scanning last 10 messages for links...")
    
    try:
        messages = wa_monitor.get_recent_messages()
        links_found = 0
        
        for message in messages:
            # Extract URLs from message
            urls = URL_PATTERN.findall(message['text'])
            
            if urls:
                print(f"📎 Found {len(urls)} link(s) from {message['sender']}")
                
                # Send to Discord
                channel = bot.get_channel(DISCORD_CHANNEL_ID)
                if channel:
                    for url in urls:
                        # Skip if this link was EVER sent before
                        if url in sent_links_history:
                            print(f"⏭️  Skipping duplicate link (already sent before): {url}")
                            continue
                        
                        # Send just the link, no embed
                        await channel.send(url)
                        print(f"✅ Forwarded to Discord: {url}")
                        
                        # Mark this link as sent forever
                        sent_links_history.add(url)
                        links_found += 1
                        
                        # Save history after each link
                        save_link_history()
                        
                        # Small delay to avoid rate limits
                        await asyncio.sleep(0.5)
            
            # Mark message as processed so we don't send again
            processed_messages.add(message['id'])
        
        if links_found > 0:
            print(f"✨ Initial scan complete! Found and forwarded {links_found} unique link(s)\n")
        else:
            print("✨ Initial scan complete! No new links found\n")
    
    except Exception as e:
        print(f"❌ Error in initial scan: {e}\n")

@tasks.loop(seconds=10)
async def monitor_whatsapp():
    """Periodically check WhatsApp for new messages with links"""
    global wa_monitor, processed_messages, sent_links_history
    
    if wa_monitor is None or not wa_monitor.is_logged_in:
        return
    
    try:
        messages = wa_monitor.get_recent_messages()
        
        for message in messages:
            # Skip if already processed
            if message['id'] in processed_messages:
                continue
            
            # Extract URLs from message
            urls = URL_PATTERN.findall(message['text'])
            
            if urls:
                print(f"\n🔗 Found {len(urls)} link(s) from {message['sender']}")
                
                # Send to Discord
                channel = bot.get_channel(DISCORD_CHANNEL_ID)
                if channel:
                    for url in urls:
                        # Skip if this link was EVER sent before
                        if url in sent_links_history:
                            print(f"⏭️  Skipping duplicate link (already sent before): {url}")
                            continue
                        
                        # Send just the link, no embed
                        await channel.send(url)
                        print(f"✅ Forwarded to Discord: {url}")
                        
                        # Mark this link as sent forever
                        sent_links_history.add(url)
                        
                        # Save history after each link
                        save_link_history()
                
                # Mark as processed
                processed_messages.add(message['id'])
                
                # Keep only last 100 message IDs in memory
                if len(processed_messages) > 100:
                    processed_messages = set(list(processed_messages)[-100:])
    
    except Exception as e:
        print(f"❌ Error in monitoring loop: {e}")

@bot.command()
async def status(ctx):
    """Check bot status"""
    if wa_monitor and wa_monitor.is_logged_in:
        await ctx.send("✅ Bot is running and monitoring WhatsApp!")
    else:
        await ctx.send("❌ WhatsApp not connected!")

@bot.command()
async def ping(ctx):
    """Check bot latency"""
    await ctx.send(f'🏓 Pong! Latency: {round(bot.latency * 1000)}ms')

@bot.command()
@commands.has_permissions(administrator=True)
async def stop(ctx):
    """Stop the bot (admin only)"""
    await ctx.send("🛑 Stopping bot...")
    if wa_monitor:
        wa_monitor.close()
    await bot.close()

# Main execution
def main():
    global wa_monitor
    
    print("\n" + "="*60)
    print("WhatsApp to Discord Link Forwarder")
    print("="*60 + "\n")
    
    # Setup WhatsApp monitor
    wa_monitor = WhatsAppMonitor()
    wa_monitor.setup_driver()
    
    if wa_monitor.login_whatsapp():
        if wa_monitor.open_group_chat():
            print("\n✅ WhatsApp setup complete!")
            print("Starting Discord bot...\n")
            
            # Run Discord bot
            try:
                bot.run(DISCORD_BOT_TOKEN)
            except KeyboardInterrupt:
                print("\n\n🛑 Shutting down...")
            finally:
                if wa_monitor:
                    wa_monitor.close()
        else:
            print("❌ Failed to open group chat")
            wa_monitor.close()
    else:
        print("❌ Failed to login to WhatsApp")
        wa_monitor.close()

if __name__ == "__main__":
    main()
