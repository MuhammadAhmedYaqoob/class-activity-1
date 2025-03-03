from flask import Flask, send_from_directory
import os

app = Flask(__name__)

# Get the current directory path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.route('/')
def home():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/about')
def about():
    return send_from_directory(BASE_DIR, 'about.html')

@app.route('/blogs')
def blogs():
    return send_from_directory(BASE_DIR, 'blogs.html')

@app.route('/contact')
def contact():
    return send_from_directory(BASE_DIR, 'contact.html')

@app.route('/rag-chatbot')
def rag_chatbot():
    return send_from_directory(BASE_DIR, 'Creating a Rag-Based Chatbot.html')

@app.route('/prompt-engineering')
def prompt_engineering():
    return send_from_directory(BASE_DIR, 'prompt engineering.html')

@app.route('/deep-drive')
def deep_drive():
    return send_from_directory(BASE_DIR, 'A deep drive.html')

if __name__ == '__main__':
    app.run(debug=True)
