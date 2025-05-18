from flask import render_template
from flask import Flask, request, jsonify
import re
import time
import ast
import praw
import google.generativeai as genai
from googlesearch import search

app = Flask(__name__)

# === API KEYS ===
REDDIT_CLIENT_ID = "40lNygl8KpqURd2BamNZWA"
REDDIT_CLIENT_SECRET = "MV9p8tYC3wVfC5t5-Vw5LBITjxA5zQ"
REDDIT_USER_AGENT = "PSAI"
GEMINI_API_KEY = "AIzaSyA6YAkXN72DlDsFyXLGwdGyfWcx0ifMHCg"

reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    user_agent=REDDIT_USER_AGENT
)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

def extract_keywords(question):
    prompt = f"""
Extract 3 to 4 keyword phrases (2-5 words each) that best describe the intent of the following question.
Avoid single numbers or currency names like "inr" or "usd".
Focus on useful search terms for Reddit.

Question: "{question}"

Example:
Question: "best gaming laptop under $1000"
Keywords: ["gaming laptop under 1000", "best gaming laptop", "budget gaming laptop"]

Now extract keywords for this question as a Python list of strings:
"""
    try:
        response = model.generate_content(prompt)
        keywords_text = response.text.strip()
        keywords_text = re.sub(r"```[a-z]*\n|```", "", keywords_text).strip()
        if keywords_text.lower().startswith("keywords ="):
            keywords_text = keywords_text.split("=", 1)[1].strip()
        keywords = ast.literal_eval(keywords_text)
        if not isinstance(keywords, list):
            return []
        keywords = [kw for kw in keywords if isinstance(kw, str) and len(kw.strip()) >= 3]
        return keywords
    except:
        return []

def google_search_reddit_urls(keywords, num_results=10):
    query = " ".join(keywords) + " site:reddit.com"
    urls = []
    try:
        for url in search(query, num_results=num_results, lang="en"):
            if "reddit.com" not in url.lower():
                continue
            if url not in urls:
                urls.append(url)
    except:
        pass
    return urls

def extract_post_id_from_url(url):
    match = re.search(r"comments/([a-z0-9]{6,})", url)
    if match:
        return match.group(1)
    return None

def fetch_reddit_posts_from_urls(urls):
    posts_data = []
    seen_ids = set()
    for url in urls:
        post_id = extract_post_id_from_url(url)
        if not post_id or post_id in seen_ids:
            continue
        try:
            post = reddit.submission(id=post_id)
            post.comments.replace_more(limit=0)
            top_comments = [c.body for c in post.comments[:5]]
            posts_data.append({
                "title": post.title,
                "url": url,
                "comments": top_comments
            })
            seen_ids.add(post_id)
            time.sleep(0.3)
        except:
            pass
    return posts_data

def generate_answer(user_question, posts_data, style_instructions=None):
    context = ""
    for post in posts_data:
        context += f"\n### Post: {post['title']}\n"
        for comment in post['comments']:
            context += f"- {comment}\n"
    style_text = ""
    if style_instructions:
        style_text = f"\nAdditional instructions on style/length: {style_instructions}\n"
    prompt = f"""
You are a helpful AI assistant. Based on the Reddit posts and comments below, answer the user's question clearly and directly.

User Question: {user_question}

Reddit context:
{context}

Instructions:
- Provide an accurate and balanced answer based on Reddit opinions.
- Use paragraphs, lists, or other formats as suitable.
- Mention differences in opinions if any.
- Avoid irrelevant info, sales listings, or spam.
- Be concise but informative.
{style_text}
"""
    response = model.generate_content(prompt)
    return response.text.strip()

@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")
    
@app.route("/ask", methods=["POST"])
def ask():
    data = request.json
    question = data.get("question")
    if not question:
        return jsonify({"error": "Missing 'question' field"}), 400

    keywords = extract_keywords(question)
    if not keywords:
        return jsonify({"error": "Could not extract keywords"}), 400

    reddit_urls = google_search_reddit_urls(keywords)
    if not reddit_urls:
        return jsonify({"error": "No Reddit URLs found"}), 404

    posts_data = fetch_reddit_posts_from_urls(reddit_urls)
    if not posts_data:
        return jsonify({"error": "Could not fetch Reddit posts"}), 404

    answer = generate_answer(question, posts_data)

    return jsonify({
        "question": question,
        "answer": answer,
        "keywords": keywords,
        "reddit_urls": reddit_urls,
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
