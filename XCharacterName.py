###############################################
#           START BLOCK 1 - Imports           #
###############################################
import json
import discord
from discord.ext import commands
import asyncio
import os
import logging
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime
from logging.handlers import RotatingFileHandler
import hashlib
from discord.utils import escape_markdown
import time
import aiohttp
import emoji
import re

"""
# Imports necessary libraries and modules for the bot's functionality.
# These include libraries for:
# - Handling JSON data (json)
# - Interacting with the Discord API (discord, discord.ext.commands)
# - Asynchronous operations (asyncio)
# - Interacting with the operating system (os)
# - Logging events and errors (logging, RotatingFileHandler)
# - Loading environment variables (dotenv)
# - Interacting with the Gemini API (google.generativeai)
# - Working with dates and times (datetime)
# - Downloading files asynchronously (aiohttp)
# - Handling emojis (emoji)
# - Regular expressions (re)
###############################################
#           END BLOCK 1 - Imports             #
###############################################
"""

###############################################
#        START BLOCK 2 - Logging Setup        #
###############################################
# Load environment variables
load_dotenv()

# Define the profile name to load from the Markdown configuration file
profile_name = "<CharacterName>"

# Set up logging
# Define the log file name with the current date
log_filename = f"./logs/{datetime.now().strftime('%Y-%m-%d')}{profile_name}.log"

# Configure basic logging settings
logging.basicConfig(
    level=logging.DEBUG,  # Set the logging level to DEBUG (logs all messages)
    format="%(asctime)s - <CharacterName> - %(levelname)s - %(message)s",  # Define the log message format
    datefmt="%Y-%m-%d %H:%M:%S",  # Define the date and time format in log messages
)

# Create a RotatingFileHandler to manage log file rotation
file_handler = RotatingFileHandler(
    filename=log_filename,  # Log file name
    maxBytes=10 * 1024 * 1024,  # Maximum file size (10 MB)
    backupCount=5,  # Keep 5 backup log files
    encoding="utf-8",  # File encoding
)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - <CharacterName> - %(levelname)s - %(message)s")
)  # Set the message format for the file handler

# Get the Discord logger and set its level to DEBUG
logger = logging.getLogger("discord")
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)  # Add the file handler to the Discord logger

# Create a separate logger for our bot's custom messages
bot_logger = logging.getLogger("ichain_bot")
bot_logger.setLevel(logging.DEBUG)
bot_logger.addHandler(file_handler)  # Add the file handler to the bot logger

###############################################
#         END BLOCK 2 - Logging Setup         #
###############################################

###############################################
#      START BLOCK 3 - Bot Configuration      #
###############################################

from google.generativeai.types import HarmCategory, HarmBlockThreshold


# Load profile configuration from the Markdown file
PROFILE_FILE = os.path.join(os.path.dirname(__file__), f"./XProfile{profile_name}.md")


def extract_json_from_md(file_path):
    """
    Extracts JSON content from a Markdown file.

    Args:
        file_path (str): The path to the Markdown file.

    Returns:
        dict: The extracted JSON content as a dictionary.
    """
    with open(file_path, "r", encoding="utf-8") as file:
        content = file.read()

    # Assuming the JSON content is enclosed in triple backticks (```json ... ```)
    json_start = content.find("```json")
    json_end = content.find("```", json_start + 7)

    if json_start == -1 or json_end == -1:
        raise ValueError("No JSON content found in the Markdown file.")

    json_content = content[json_start + 7 : json_end].strip()

    return json.loads(json_content)


profile = extract_json_from_md(PROFILE_FILE)
print(f"Profile Loaded: {profile}")

# Load environment variables from the .env file
load_dotenv()

# Load bot token and API keys from environment variables
DISCORD_TOKEN = os.getenv(f"{profile_name.upper()}_BOT_TOKEN")
gemini_api_key = os.getenv(f"{profile_name.upper()}_GEMINI_API_KEY")
anthropic_api_key = os.getenv(f"{profile_name.upper()}_ANTHROPIC_API_KEY")
togetherai_api_key = os.getenv(f"{profile_name.upper()}_TOGETHERAI_API_KEY")

# Check if the Gemini API key is set
if not gemini_api_key:
    raise ValueError(
        f"{profile_name.upper()}_GEMINI_API_KEY environment variable not set"
    )

# Configure the Gemini API client with the API key
genai.configure(api_key=gemini_api_key)

# Model configuration for Gemini
generation_config = {
    "temperature": 1,  # Controls the randomness of the generated text (higher = more random)
    "top_p": 0.95,  # Controls the diversity of the generated text
    "top_k": 64,  # Limits the vocabulary used by the model
    "max_output_tokens": 8192,  # Maximum number of tokens in the generated response
    "response_mime_type": "text/plain",  # Response format
}

# Safety settings for Gemini (currently set to allow all content)
safety_settings = {
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

# Create a Gemini model instance with the specified configuration
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",  # Model name
    generation_config=generation_config,  # Generation configuration
)

# Track the time of the last API call to implement rate limiting
last_api_call = None
api_call_interval = 1  # Minimum interval between API calls in seconds

# Create the bot instance with the command prefix "X" and all intents enabled
bot = commands.Bot(command_prefix="X", intents=discord.Intents.all())

###############################################
#     END BLOCK 3 - Bot Configuration       #
###############################################

###############################################
#    START BLOCK 4 - Gemini API Functions     #
###############################################


def run_gemini(prompt, system_prompt="", channel_context="", profile=""):
    """
    Sends a prompt to the Gemini API and returns the response.

    Args:
        prompt (str): The user's question or prompt to send to Gemini.
        system_prompt (str, optional): An optional system prompt to set the context for the model. Defaults to "".
        channel_context (dict, optional): Channel context information to provide additional context. Defaults to an empty dictionary.
        profile (str, optional): Profile configuration to set the context for the model. Defaults to "".

    Returns:
        dict: A dictionary containing the model's response or an error message.
               The dictionary has the following keys:
               - "model" (str): The name of the model used (always "gemini-1.5-flash").
               - "response" (str): The model's response text (if successful).
               - "error" (str): The error message (if an error occurred).
    """
    full_prompt = (
        f"Profile Configuration: {profile}\n\n{system_prompt}\n\nChannel Name: {channel_context.get('name')}\nChannel Topic: {channel_context.get('topic')}\nPinned Messages: {channel_context.get('pinned_messages')}\nRecent Messages: {channel_context.get('recent_messages')}\n\nUser Question: {prompt}"
        if system_prompt
        else f"Profile Configuration: {profile}\n\nChannel Name: {channel_context.get('name')}\nChannel Topic: {channel_context.get('topic')}\nPinned Messages: {channel_context.get('pinned_messages')}\nRecent Messages: {channel_context.get('recent_messages')}\n\nUser Question: {prompt}"
    )
    logger.info(f"Sending prompt to Gemini: {full_prompt}")

    try:
        chat_session = model.start_chat(history=[])
        response = chat_session.send_message(
            full_prompt, safety_settings=safety_settings
        )
        logger.info(f"Received response from Gemini: {response.text}")
        logger.debug(f"Full Gemini response object: {response}")

        return {
            "model": "gemini-1.5-flash",
            "response": response.text,
        }
    except Exception as e:
        error_message = (
            "🚨 WHOA, GLITCH ALERT! 🚨\n\n"
            "👀 You've stumbled upon a wild ERROR! But don't panic, space cadet!\n\n"
            "🧠💡 This is your chance to flex those big brain muscles!\n\n"
            "🔍 Crack this code conundrum and you could be swimming in 1000 SGC! 🤑💰\n\n"
            "🚀 First one to squash this bug gets the bounty AND eternal iChain glory!\n\n"
            "💪 You got this, future tech titan! May the code be with you!\n\n"
            "#BugHunterLife #iChainChallenge #ErrorsAreJustSneakyTreasures"
        )
        logger.error(f"Failed to get response from Gemini API: {e}")
        logger.exception("Full exception traceback:")
        return {"model": "gemini-1.5-flash", "error": f"{str(e)}\n\n{error_message}"}


async def handle_file(url):
    """
    Downloads a file from a given URL asynchronously and returns its content.

    Args:
        url (str): The URL of the file to download.

    Returns:
        str or None: The content of the downloaded file as a string, or None if the download fails.
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.text()
            else:
                return None


###############################################
#    END BLOCK 4 - Gemini API Functions       #
###############################################

###############################################
#    START BLOCK 5 - Utility Functions        #
###############################################


def generate_file_name(user_id, content):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    shortened_hash = content_hash[:4] + content_hash[-4:]
    return f"{timestamp}_{user_id}_{shortened_hash}.md"


def format_mentions(text, bot):
    for guild in bot.guilds:
        for member in guild.members:
            mention_str = f"@{member.name}"
            if mention_str in text:
                text = text.replace(mention_str, member.mention)
    return text


async def get_channel_context(channel: discord.TextChannel):
    """
    Retrieves the context of a Discord channel, including its topic, pinned messages, channel name, and recent messages.
    If the channel is a thread, it retrieves relevant information for threads instead.

    Args:
        channel (discord.TextChannel or discord.Thread): The Discord channel or thread to retrieve context from.

    Returns:
        dict: A dictionary containing the channel or thread context:
              - "name" (str): The name of the channel or thread.
              - "topic" (str): The topic of the channel or a default message for threads.
              - "pinned_messages" (list): A list of dictionaries representing pinned messages.
              - "recent_messages" (str): A JSON-formatted string representing the recent messages in the channel or thread.
              - "recent_message_list" (list): A list of recent message objects for further processing.
    """
    topic = (
        getattr(channel, "topic", "No topic set.")
        if isinstance(channel, discord.TextChannel)
        else "Threads do not have topics."
    )
    pinned_messages = await get_pinned_messages(channel)
    channel_name = channel.name
    recent_messages, recent_message_list = await get_channel_history(channel)
    print(
        f"Channel Context: {channel_name}, {topic}, {pinned_messages}, {recent_messages}"
    )
    return {
        "name": channel_name,
        "topic": topic,
        "pinned_messages": pinned_messages,
        "recent_messages": recent_messages,
        "recent_message_list": recent_message_list,
    }


def save_response_to_txt(
    response,
    question,
    user_name,
    message_link,
    system_prompt,
    temperature,
    version_context,
    context,
    channel_history,
):
    """
    Saves the Gemini response, question, and additional context to a text file.

    Args:
        response (dict): The response dictionary from the Gemini model.
        question (str): The user's question.
        user_name (str): The name of the user asking the question.
        message_link (str): The link to the message containing the question.
        system_prompt (str): The system prompt used for the model.
        temperature (float): The temperature setting used for the model.
        version_context (str): The version or context of the file.
        context (dict): Additional context including channel topic and pinned messages.
        channel_history (list): Recent messages from the channel.

    Returns:
        str: The path to the saved file.
    """
    # Construct the content of the text file
    content = f"Profile Configuration: {json.dumps(profile, indent=2)}\n\n"
    content += f"Question: {question}\n\n"
    content += f"User: {user_name}\n"
    content += f"Message Link: {message_link}\n\n"
    content += f"System Prompt: {system_prompt}\n"
    content += f"Temperature: {temperature}\n"
    content += f"Version Context: {version_context}\n\n"
    content += f"Model: {response['model']}\n"
    if "response" in response:
        content += f"Response: {response['response']}\n\n"
    if "error" in response:
        content += f"Error: {response['error']}\n\n"

    content += "Channel Context:\n"
    content += f"Name: {context['name']}\n"
    content += f"Topic: {context['topic']}\n\n"

    content += "Pinned Messages:\n"
    for pin in context["pinned_messages"]:
        content += f"{pin['author']}: {escape_markdown(pin['content'])}\n"
    content += "\n"

    content += "Recent Messages:\n"
    for msg in channel_history:
        author_name = f"{msg.author.name}#{msg.author.discriminator}"
        timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        content += f"{author_name} at {timestamp}: {escape_markdown(msg.content)}\n"

    content += "\nUser Feedback: [To be filled by user]\n"

    # Generate a unique file name
    file_name = generate_file_name(user_name, content)
    file_path = os.path.join("responses", file_name)

    # Create the "responses" directory if it doesn't exist
    os.makedirs("responses", exist_ok=True)

    # Save the content to the text file
    with open(file_path, "w", encoding="utf-8") as file:
        file.write(content)

    print(f"Response saved to {file_path}")
    return file_path


async def get_channel_history(channel: discord.TextChannel, limit=100):
    """
    Fetches recent messages from the channel and formats them as a string and a list of message objects.

    Args:
        channel (discord.TextChannel): The Discord channel to fetch messages from.
        limit (int, optional): The maximum number of messages to retrieve. Defaults to 100.

    Returns:
        tuple: A tuple containing:
            - str: A JSON-formatted string representing the channel history.
            - list: A list of `discord.Message` objects representing the retrieved messages.
    """
    messages = []
    async for message in channel.history(limit=limit):
        messages.append(message)
    messages.reverse()  # Reverse to get oldest first

    history_json = []
    for msg in messages:
        author = msg.author
        entity = {
            "id": str(author.id),
            "username": f"{author.name}#{author.discriminator}",
            "display_name": author.display_name,
        }
        is_you = entity["id"] == str(bot.user.id)
        timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        history_json.append(
            {
                "entity": entity,
                "is_you": is_you,
                "message_timestamp": timestamp,
                "content": escape_markdown(msg.content),
            }
        )

    print(f"Channel History: {history_json}")
    return json.dumps(history_json, indent=2), messages


async def get_pinned_messages(channel: discord.TextChannel):
    """
    Fetches pinned messages from the specified Discord channel.

    Args:
        channel (discord.TextChannel): The Discord channel to retrieve pinned messages from.

    Returns:
        list: A list of dictionaries, where each dictionary represents a pinned message and contains:
              - "author" (str): The author of the pinned message in the format "username#discriminator".
              - "content" (str): The content of the pinned message.
    """
    pins = await channel.pins()
    pinned_messages = [
        {
            "author": f"{pin.author.name}#{pin.author.discriminator}",
            "content": pin.content,
        }
        for pin in pins
    ]
    return pinned_messages


async def get_channel_context(channel: discord.TextChannel):
    """
    Retrieves the context of a Discord channel, including its topic, pinned messages, channel name, and recent messages.

    Args:
        channel (discord.TextChannel): The Discord channel to retrieve context from.

    Returns:
        dict: A dictionary containing the channel context:
              - "name" (str): The name of the channel.
              - "topic" (str): The topic of the channel.
              - "pinned_messages" (list): A list of dictionaries representing pinned messages.
              - "recent_messages" (str): A JSON-formatted string representing the recent messages in the channel.
              - "recent_message_list" (list): A list of recent message objects for further processing.
    """
    topic = (
        getattr(channel, "topic", "No topic set.")
        if isinstance(channel, discord.TextChannel)
        else "Threads do not have topics."
    )
    pinned_messages = await get_pinned_messages(channel)
    channel_name = channel.name
    recent_messages, recent_message_list = await get_channel_history(channel)
    print(
        f"Channel Context: {channel_name}, {topic}, {pinned_messages}, {recent_messages}"
    )
    return {
        "name": channel_name,
        "topic": topic,
        "pinned_messages": pinned_messages,
        "recent_messages": recent_messages,
        "recent_message_list": recent_message_list,
    }


async def upload_file(thread, file_path):
    """
    Uploads a file to a Discord thread and then deletes the file from the local system.

    Args:
        thread (discord.Thread): The Discord thread to send the file to.
        file_path (str): The path to the file to be uploaded.
    """
    await thread.send(file=discord.File(file_path))
    os.remove(file_path)


###############################################
#    END BLOCK 5 - Utility Functions          #
###############################################

###############################################
#    START BLOCK 6 - Bot Event Handlers       #
###############################################


@bot.event
async def on_ready():
    """
    Event handler that runs when the bot has successfully connected to Discord.

    This function logs a message indicating that the bot is online and sends a "Hello world!"
    message to a specific Discord channel (ID: 1253969687436464190).
    """
    logger.info(f"{bot.user} has connected to Discord!")
    print(f"{bot.user} has connected to Discord!")
    # Send a hello world message to the specified channel
    channel = bot.get_channel(1253969687436464190)
    if channel:
        await channel.send("Hello world! Gemini is now online and functional.")


@bot.event
async def on_message(message):
    """
    Event handler that is triggered for every message received on the server.

    This handler listens for mentions of the bot and processes questions directed at it.
    It also logs all received messages and their content.

    Args:
        message (discord.Message): The message object representing the received message.
    """
    # Log the received message and its author
    logger.debug(f"Received message from {message.author.name}: {message.content}")
    print(f"Received message from {message.author.name}: {message.content}")

    # Ignore messages from the bot itself
    if message.author == bot.user:
        logger.debug("Ignoring message from self.")
        print("Ignoring message from self.")
        return

    # Check if the bot is mentioned in the message
    if bot.user.mentioned_in(message):
        # Log that the bot was mentioned
        logger.debug(f"{bot.user.name} was mentioned in a message.")
        print(f"{bot.user.name} was mentioned in a message.")

        # Remove the bot mention from the message content
        content = message.content.replace(f"<@{bot.user.id}>", "").strip()

        # Check if the message has content or attachments
        if content or message.attachments:
            # Process the message as a question
            logger.debug("Processing question.")
            print("Processing question.")
            await process_question(message, content)
        else:
            # If no content or attachments, send a greeting message
            logger.debug("No content found to process.")
            print("No content found to process.")
            await message.channel.send("Hello! How can I assist you today?")
    else:
        # Log that the bot was not mentioned
        logger.debug(f"{bot.user.name} was not mentioned.")
        print(f"{bot.user.name} was not mentioned.")

    # Process commands in the message
    await bot.process_commands(message)


###############################################
#    END BLOCK 6 - Bot Event Handlers         #
###############################################

###############################################
#    START BLOCK 7 - Question Processing Logic  #
###############################################


async def process_question(message: discord.Message, question: str):
    """
    Processes a user's question, sends it to the Gemini model, and handles the response.

    This function orchestrates the entire process of answering a user's question, including:
    1. Retrieving relevant information (system prompt, channel history, attachments).
    2. Managing API call rate limiting.
    3. Sending the question to the Gemini model.
    4. Handling the model's response (or error).
    5. Formatting and sending the response back to the Discord channel.
    6. Creating a private thread for detailed response and logging.

    Args:
        message (discord.Message): The Discord message object containing the question.
        question (str): The user's question extracted from the message.
    """
    global last_api_call

    # Retrieve the system prompt, temperature, and version context from the bot's configuration
    system_prompt = profile["system"]
    temperature = 0.7  # You can adjust this or make it configurable
    version_context = "v1.0"  # You can update this as needed

    # Get the channel context (name, topic, pinned messages, recent messages)
    context = await get_channel_context(message.channel)

    # Handle attachments in the message
    if message.attachments:
        attachment = message.attachments[0]
        # Check if the attachment is a supported file type
        if attachment.filename.lower().endswith(
            (
                "png",
                "jpg",
                "jpeg",
                "gif",
                "txt",
                "pdf",
                "doc",
                "docx",
                "py",
                "js",
                "java",
                "cpp",
                "c",
                "html",
                "css",
                "sh",
                "bat",
            )
        ):
            # Download and append the file content to the question
            file_content = await handle_file(attachment.url)
            if file_content:
                question += f"\n{file_content}"

    # Implement rate limiting to avoid exceeding API call limits
    current_time = time.time()
    if last_api_call and current_time - last_api_call < api_call_interval:
        await asyncio.sleep(api_call_interval - (current_time - last_api_call))
    last_api_call = time.time()

    # Send the question to the Gemini model using the run_gemini function
    response = await asyncio.to_thread(
        run_gemini, question, system_prompt, context, json.dumps(profile)
    )

    # Handle errors returned by the Gemini model
    if "error" in response:
        await message.channel.send(f"An error occurred: {response['error']}")
        return

    # Convert Unicode emojis in the response to markdown
    final_response = emoji.demojize(response["response"])

    # Format user mentions in the response to ensure proper tagging
    final_response = format_mentions(final_response, bot)

    # Split the response into chunks to avoid exceeding Discord's message length limit
    chunk_size = 1990  # 2000 characters minus some buffer for prefix and formatting
    prefix = ""

    def split_message(message, chunk_size, prefix):
        """
        Splits a message into chunks of a maximum size, preserving paragraph breaks.

        Args:
            message (str): The message to split into chunks.
            chunk_size (int): The maximum size of each chunk in characters.
            prefix (str): A prefix to add to each chunk.

        Returns:
            list: A list of message chunks.
        """
        chunks = []
        while len(message) > chunk_size - len(prefix):
            split_index = message.rfind("\n\n", 0, chunk_size - len(prefix))
            if split_index == -1:
                split_index = chunk_size - len(prefix)
            chunks.append(prefix + message[:split_index])
            message = message[split_index:].strip()
        chunks.append(prefix + message)
        return chunks

    chunks = split_message(final_response, chunk_size, prefix)

    # Reply to the user with the first chunk of the response
    await message.reply(chunks[0])
    await asyncio.sleep(1)  # Small delay to avoid rate limiting

    # Send the remaining chunks to the channel
    for chunk in chunks[1:]:
        await message.channel.send(chunk)
        await asyncio.sleep(1)  # Small delay to avoid rate limiting

    # Log the number of chunks sent
    logger.info(f"Ask response sent to channel in {len(chunks)} chunks")
    print(f"Ask response sent to channel in {len(chunks)} chunks")

    # Create a private thread for the response and logging
    thread = await message.channel.create_thread(
        name=f"{message.author.name}'s Response",
        type=discord.ChannelType.private_thread,
        # auto_archive_duration=1440,  # Archive after 24 hours of inactivity (optional)
    )

    # Send a feedback prompt to the thread
    feedback_prompt = (
        "# 📣 Your voice matters! 🗣️\n"
        "**Drop your feedback below and earn 10 SGC! 💎**\n"
        "**Help shape the future of iChain! 🚀**\n\n"
    )
    await thread.send(feedback_prompt)
    await asyncio.sleep(1)  # Small delay to ensure feedback prompt appears first

    # Send all response chunks to the thread
    for chunk in chunks:
        await thread.send(chunk)
        await asyncio.sleep(1)  # Small delay to avoid rate limiting

    # Save the response to a text file and upload it to the thread
    file_path = await asyncio.to_thread(
        save_response_to_txt,
        response,
        question,
        message.author.name,
        message.jump_url,
        system_prompt,
        temperature,
        version_context,
        context,
        context["recent_message_list"],
    )
    await upload_file(thread, file_path)

    # Log that the response and log file were sent to the thread
    logger.info("Ask response and log file sent to thread")
    print("Ask response and log file sent to thread")


###############################################
#    END BLOCK 7 - Question Processing Logic  #
###############################################

###############################################
#     START BLOCK 8 - Bot Commands            #
###############################################


@bot.command()
async def menu(ctx):
    """
    Displays an interactive menu with a button to ask Gemini a question.

    This command sends a message with a button labeled "Ask Gemini". Clicking this button
    opens a modal dialog where the user can type their question.
    """
    view = discord.ui.View()
    button = discord.ui.Button(label="Ask Gemini", style=discord.ButtonStyle.primary)

    async def button_callback(interaction):
        """
        Callback function for the "Ask Gemini" button.

        This function sends a modal dialog with a text input field for the user's question.
        """
        await interaction.response.send_modal(
            discord.ui.Modal(
                title="Ask Gemini",
                custom_id="ask_gemini_modal",
                children=[
                    discord.ui.TextInput(
                        label="Your question",
                        placeholder="What would you like to ask?",
                        custom_id="question_input",
                        style=discord.TextStyle.paragraph,
                    )
                ],
            )
        )

    button.callback = button_callback
    view.add_item(button)
    await ctx.send("Click the button to ask Gemini a question:", view=view)


@bot.event
async def on_modal_submit(interaction):
    """
    Event handler for processing modal submissions.

    This handler specifically processes the modal submitted when a user clicks the "Ask Gemini"
    button and types their question. It extracts the question from the modal data and calls
    the `process_question` function to handle it.
    """
    if interaction.custom_id == "ask_gemini_modal":
        # Get the user's question from the modal input
        question = interaction.data["components"][0]["components"][0]["value"]

        # Defer the interaction response to allow time for processing
        await interaction.response.defer()

        # Process the question using the existing process_question function
        await process_question(interaction, question)


###############################################
#     END BLOCK 8 - Bot Commands              #
###############################################

###############################################
#     START BLOCK 9 - Main Execution          #
###############################################

if __name__ == "__main__":
    try:
        # Log the start of the bot
        logger.info(f"Starting {profile_name} Discord Bot...")
        print(f"Starting {profile_name} Discord Bot...")

        # Run the bot using the Discord token
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        # Log any critical errors during bot startup
        logger.critical(f"Failed to start the bot: {e}")
        print(f"Failed to start the bot: {e}")
    finally:
        # Log that the bot has shut down
        logger.info("Bot has shut down.")
        print("Bot has shut down.")

"""
# This block is the entry point for the script:
# - It checks if the script is being run directly (not imported)
# - Attempts to start the bot using the Discord token
# - Logs any critical errors that prevent the bot from starting
# - Ensures a shutdown message is logged when the bot stops running
###############################################
#      END BLOCK 9 - Main Execution           #
###############################################
"""
