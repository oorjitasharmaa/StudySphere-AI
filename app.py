from flask import Flask, render_template, request, redirect
import os
import sqlite3
from groq import Groq
from PyPDF2 import PdfReader

app = Flask(__name__)
conn = sqlite3.connect('database.db')
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT
)
''')

conn.commit()
conn.close()

#GROQ
client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

#HOME
@app.route('/')
def home():
    return render_template('index.html')

#LOGIN
@app.route('/login', methods=['GET','POST'])
def login():

    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username,password)
        )

        user = cursor.fetchone()

        conn.close()

        if user:
            return redirect('/dashboard')

        else:
            return "Invalid Username or Password"

    return render_template('login.html')

#DASHBOARD
import sqlite3

@app.route('/dashboard')
def dashboard():

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM notes")
    notes_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM quizzes")
    quiz_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM chats")
    chat_count = cursor.fetchone()[0]

    conn.close()

    return render_template(
        "dashboard.html",
        notes_count=notes_count,
        quiz_count=quiz_count,
        chat_count=chat_count
    )

#SIGNUP
@app.route('/signup', methods=['GET','POST'])
def signup():

    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        try:

            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()

            cursor.execute(
                "INSERT INTO users(username,password) VALUES(?,?)",
                (username,password)
            )

            conn.commit()
            conn.close()

            return redirect('/login')

        except:

            return "Username already exists"

    return render_template('signup.html')


#UPLOAD+SUMMARY
@app.route('/upload', methods=['GET', 'POST'])
def upload():

    if request.method == 'POST':

        file = request.files['notes']

        filepath = os.path.join('uploads', file.filename)

        file.save(filepath)

        # Save uploaded note in database
        import sqlite3

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO notes(filename) VALUES(?)",
            (file.filename,)
        )

        conn.commit()
        conn.close()

        # Read PDF
        pdf = PdfReader(filepath)

        text = ""

        for page in pdf.pages:

            extracted = page.extract_text()

            if extracted:
                text += extracted

        # Save notes text for quiz/chat
        with open("notes.txt", "w", encoding="utf-8") as f:
            f.write(text)

        try:

            chat_completion = client.chat.completions.create(

                messages=[
                    {
                        "role": "user",
                        "content": f"""
Analyze these study notes carefully and create a complete study guide.

Format:

📌 Chapter Overview

(Brief introduction of the topic)

📖 Detailed Summary

(Explain all important topics in simple language)

🧠 Important Concepts

• Concept 1
• Concept 2
• Concept 3

⭐ Exam Important Points

• Point 1
• Point 2
• Point 3

❓ Frequently Asked Questions

Q1. Question

Answer

Q2. Question

Answer

📋 Final Revision Notes

• Quick revision point 1
• Quick revision point 2
• Quick revision point 3

Make the response well-structured, detailed, neat, and student-friendly.

Study Notes:

{text[:20000]}
"""
                    }
                ],

                model="llama-3.3-70b-versatile"

            )

            summary = chat_completion.choices[0].message.content

        except Exception as e:

            summary = f"AI Error: {e}"

        return render_template(
            'summary.html',
            summary=summary
        )

    return render_template('upload.html')

#QUIZ
@app.route('/quiz')
def quiz():

    try:

        with open("notes.txt", "r", encoding="utf-8") as f:
            notes = f.read()

        chat_completion = client.chat.completions.create(

            messages=[
                {
                    "role": "user",
                    "content": f"""
Generate 10 MCQs from these notes.

Format:

Q1. Question

A)
B)
C)
D)

Answer: Correct Option

Notes:

{notes[:4000]}
"""
                }
            ],

            model="llama-3.3-70b-versatile"

        )

        quiz_data = chat_completion.choices[0].message.content

        # Save quiz count
        import sqlite3

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO quizzes DEFAULT VALUES"
        )

        conn.commit()
        conn.close()

        return render_template(
            "quiz.html",
            quiz=quiz_data
        )

    except Exception as e:

        return f"Error: {e}"

#CHATAI
@app.route('/chat', methods=['GET', 'POST'])
def chat():

    answer = ""

    if request.method == 'POST':

        question = request.form['question']

        try:

            with open("notes.txt", "r", encoding="utf-8") as f:
                notes = f.read()

            chat_completion = client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": f"""
Answer ONLY from these study notes.

NOTES:

{notes[:4000]}

QUESTION:

{question}
"""
                    }
                ],
                model="llama-3.3-70b-versatile"
            )

            answer = chat_completion.choices[0].message.content

        except Exception as e:

            answer = f"Error: {e}"

    return render_template(
        'chat.html',
        answer=answer
    )

#APP RUN
if __name__ == '__main__':
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )