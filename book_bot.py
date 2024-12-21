# Book Bot
# Requirements - openai, pynytimes, python-telegram-bot, asyncpraw

# TODO
# Add GPT with list of books you like to filter the books
# Add more sources, like reddit books, goodreads?, amazon etc.
# Maybe add a file with already viewed books
# Check available subjects in openlibrary, maybe filter on that (subject, subject_facet, subject_key fields)

import os
import re
import html
import requests
import asyncio
import asyncpraw
from datetime import datetime
from aiohttp import ClientSession
from telegram import Bot, InputMediaPhoto
from telegram.ext import Application
from pynytimes import NYTAPI
from dotenv import load_dotenv
from openai import OpenAI, AsyncOpenAI
from bs4 import BeautifulSoup

project_folder = os.path.expanduser('~')
load_dotenv(os.path.join(project_folder, '.env'))

NYT_API_KEY = os.environ['NYT_API_KEY']
BOOK_BOT_TOKEN = os.environ['BOOK_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

tele_app = Application.builder().token(BOOK_BOT_TOKEN).read_timeout(15).build()
telegram_bot = tele_app.bot

proxies = {
  "http": "http://proxy.server:3128"
}

# openai_client = AsyncOpenAI(
#     api_key=os.environ.get("OPENAI_API_KEY"),
# )

MY_BOOKS = "Shift By Howey Hugh, Heat 2 by Michael Mann, Legends and Lattes by Travis Baldree, Going Postal by Terry Pratchett"



def get_nyt_bestsellers():
	print("Getting New York Times best sellers")
	book_categories = ["combined-print-and-e-book-nonfiction", "combined-print-and-e-book-fiction", "hardcover-graphic-books", "combined-print-fiction", "celebrities"]
	nyt = NYTAPI(NYT_API_KEY, parse_dates=True)
	all_books = []

	for book_category in book_categories:
		# print("Finding books in: ", book_category)
		best_sellers = nyt.best_sellers_list(name=book_category, date=None)
		books = [{
					"title": book["title"],
					"author": book["author"],
					"book_image": book["book_image"],
					"amazon_product_url": book["amazon_product_url"],
					"weeks_on_list": book["weeks_on_list"],
					"description": book["description"],
					"isbn": book["primary_isbn10"]
					} for book in best_sellers]
		all_books += books
	print(f"Got {len(all_books)} books")
	return all_books

def split_string_into_chunks(input_string, chunk_size):
    chunks = []
    current_position = 0

    while current_position < len(input_string):
        # Determine the end of the current chunk
        end_position = current_position + chunk_size

        # Find the closest line break before the end position
        line_break_position = input_string.rfind('\n', current_position, end_position)

        if line_break_position == -1:
            # If no line break is found, take the rest of the string
            chunks.append(input_string[current_position:])
            break
        else:
            # If a line break is found, take the substring up to that point
            chunks.append(input_string[current_position:line_break_position + 1])  # Include the line break
            current_position = line_break_position + 1  # Move past the line break

    return chunks

def format_message(collections):
	messages = []
	for best_seller in collections:
		message = f'{best_seller["author"]}\n \
					{best_seller["title"]}\n\n \
					{best_seller["description"]}\n \
					{best_seller["amazon_product_url"]}\n\n \
					{best_seller["book_image"]}\n'
		messages.append(message)
	final_message = str("\n".join(messages))
	# print (final_message)
	return final_message

def escape_selected_characters(input_string, characters_to_escape):
    # Create a regex pattern to match any of the characters to escape
    pattern = f"[{re.escape(characters_to_escape)}]"

    # Replace each matched character with its escaped version
    escaped_string = re.sub(pattern, lambda x: f"\\{x.group(0)}", input_string)

    return escaped_string

def format_message_markdown(collections):
	messages = []
	for best_seller in collections:
		message = f"*{best_seller['title']}*\n" \
                  f"{best_seller['author']}\n" \
                  f"[View on Goodreads](https://www.goodreads.com/search?q={best_seller['title']})\n\n"
                  # f"{best_seller['description']}\n\n" \
                  # f"[View on Amazon]({best_seller['amazon_product_url']})\n\n" \
                  # f"[]({best_seller['book_image']})Some text.\n"
		messages.append(message)
	final_message = str("\n".join(messages))
	characters = "#-"
	return escape_selected_characters(final_message, characters)

def format_message_html(collections):
	messages = []
	for best_seller in collections:
		message = f"<a href={best_seller['book_image']}>&#8205;</a>"
				  # f"<b>{best_seller['title']}</b>\n" \
                  # f"<b>{best_seller['author']}</b>\n\n" \
                  # f"<b>Description:</b> {best_seller['description']}\n\n" \
                  # f"[View on Amazon]({best_seller['amazon_product_url']})\n\n" \
                  # f"![Book Image]({best_seller['book_image']})\n"
		messages.append(message)
	final_message = str("\n".join(messages))
	return html.escape(final_message)

def download_image(url):
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        return response.raw
    else:
        raise Exception("Image couldn't be retrieved")

def send_telegram_message(data, format=None):
	match format:
		case "HTML":
			formatted_message = format_message_html(data)
		case "Markdown":
			formatted_message = format_message_markdown(data)
		case _:
			formatted_message = format_message(data)

	messages = split_string_into_chunks(formatted_message, 4090)

	for message in messages:
		url = f"https://api.telegram.org/bot{BOOK_BOT_TOKEN}/sendMessage"
		payload = {
		    "chat_id": CHAT_ID,
		    "text": message,
		    "parse_mode": format
		}
		response = requests.post(url, data=payload)

		if response.status_code != 200:
			print("Failed to send message.")
			print(response.reason)
			print(response.text)

def split_into_chunks(array, chunk_size):
    if chunk_size <= 0:
        raise ValueError("Chunk size must be a positive integer.")
    return [array[i:i + chunk_size] for i in range(0, len(array), chunk_size)]

async def send_book_images(best_sellers, download=True):
	print("Sending book images")
	images=[]
	if download:
		for best_seller in best_sellers:
			if best_seller.get("book_image") is not None:
				image_stream = await asyncio.get_running_loop().run_in_executor(None, download_image, best_seller['book_image'])
				media = InputMediaPhoto(media=image_stream, caption=f"https://www.goodreads.com/search?q={best_seller['isbn']}")
				images.append(media)

		images_in_chunks = split_into_chunks(images, 10)
		for images_chunk in images_in_chunks:
			await telegram_bot.send_media_group(chat_id=CHAT_ID, media=images_chunk)
	else:
		for best_seller in best_sellers:
			if best_seller.get("book_image") is not None:
				media=InputMediaPhoto(media=best_seller['book_image'], caption=f"https://www.goodreads.com/search?q={best_seller['isbn']}")
				images.append(media)

		images_in_chunks = split_into_chunks(images, 5)
		for images_chunk in images_in_chunks:
			try:
				await telegram_bot.send_media_group(chat_id=CHAT_ID, media=images_chunk)
				await asyncio.sleep(3)
			except Exception as e:
				print(e)
				print("Error sending book images")

async def filter_books_using_chatgpt(books):
	book_string = ""

	for book in books:
		book_string += f'{book["title"]} by {book["author"]} ID: {book["isbn"]},'

	# prompt = f"Based on the following book preferences: {MY_BOOKS}, filter the following books: {book_string}"
	prompt = f"Based on the following user preferences: {MY_BOOKS}, please recommend book IDs from the provided list that match these preferences. Return the recommended book IDs as a comma-separated string."
	response = await openai_client.chat.completions.create(
	    messages=[
	        {"role": "system", "content": "You are a helpful assistant that specializes in books."},
	        {"role": "user", "content": prompt},
	        {"role": "user", "content": str(book_string)}
	    ],
	    model="gpt-3.5-turbo",
	)
	print(response)
	response_content = response.choices[0].message.content
	print(response_content)
	return response_content

async def find_book_on_openlibrary(title):
	try:
		url = f'https://openlibrary.org/search.json?title={title.replace(" ", "+")}'
		response = requests.get(url)
		results = response.json()
		if results["numFoundExact"] and results["numFound"] > 0:
			book = results["docs"][0]
			if book.get("cover_i") != None and book.get("isbn") != None:
				book_obj = {"book_image": f'https://covers.openlibrary.org/b/id/{book["cover_i"]}-L.jpg',
							"isbn":  book["isbn"][0]}
				# print(f"Found book {title} on openlibrary:", book_obj)
				return book_obj
		return {}
	except:
		return {}

def deEmojify(text):
    regrex_pattern = re.compile(pattern = "["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
                           "]+", flags = re.UNICODE)
    return regrex_pattern.sub(r'',text)

def parse_reddit_comment(comment):
	book = {}
	lines = comment.split("\n")
	for line in lines:
		if "by" in line and len(line) < 50:
			line = line.lower().strip()
			symbols = ['started', 'finished', ':', 'reading', '\\', '*']
			for symbol in symbols:
				line = line.replace(symbol, '')
			book_arr = line.split("by")
			if len(book_arr) > 1:
				book_title = book_arr[0].strip()
				book_author = book_arr[1].strip()
				book = {"title": book_title,
						"author": deEmojify(book_author)}
	return book

async def find_books_on_reddit(thread_id, limit=10):
	print("Getting books from Reddit")
	if thread_id:
		session = ClientSession(trust_env=True)
		reddit = asyncpraw.Reddit(
		    client_id=os.environ['REDDIT_CLIENT_ID'],
		    client_secret=os.environ['REDDIT_CLIENT_SECRET'],
		    requestor_kwargs={"session": session},
		    user_agent="python:bookbot:v1.0.0 (by u/Boris_Abramovich)"
		)
		submission = await reddit.submission(thread_id)
		books = []
		await submission.comments.replace_more(limit=limit)
		comments = submission.comments.list()
		comments.reverse()
		for comment in comments:
			book = parse_reddit_comment(comment.body)
			if book.get("title") is not None:
				book_openlib = await find_book_on_openlibrary(book["title"])
				book.update(book_openlib)
			if book:
				books.append(book)
				if len(books) == 30:
					break

		await reddit.close()
		return books

def scrape_reddit_books():
	url = "https://www.reddit.com/r/books/"  # Replace with your target URL
	response = requests.get(url, proxies=proxies)
	print(response)
	html_content = response.text
	soup = BeautifulSoup(html_content, 'html.parser')
	elements = soup.find_all('faceplate-tracker', {'source': 'community_menu'})
	for element in elements:
		if element.text.strip() == "What We're Reading":
			a = element.find('a')
			return a['href'].split('/')[-1]

async def main():
	dt = datetime.now()
	weekday = dt.weekday()
	if weekday == 6:
		nyt_best_sellers = get_nyt_bestsellers()
		await send_book_images(nyt_best_sellers, download=False)
	elif weekday in [0,2,4,5]:
		reddit_thread_id = scrape_reddit_books()
		print("Reddit thread id:", reddit_thread_id)
		reddit_books = await find_books_on_reddit(reddit_thread_id, limit=100)
		await send_book_images(reddit_books, download=False)
	else:
		print(f"Doing nothing, weekday is {weekday}")


if __name__ == '__main__':
	asyncio.run(main())