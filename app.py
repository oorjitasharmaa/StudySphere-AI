import os
import sqlite3
import uuid
from functools import wraps
from pathlib import Path

import markdown
from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from groq import Groq
from pypdf import PdfReader
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


# --------------------------------------------------
# BASIC CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

DATABASE = BASE_DIR / "database.db"
UPLOAD_DIR = BASE_DIR / "uploads"

UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf"}
MAX_FILE_SIZE = 15 * 1024 * 1024


# Load variables from .env file
load_dotenv()


# --------------------------------------------------
# FLASK APP
# --------------------------------------------------

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-in-production"
)

app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE


# --------------------------------------------------
# GROQ AI CONFIGURATION
# --------------------------------------------------

api_key = os.environ.get("GROQ_API_KEY")

# You can change this model from your .env file
AI_MODEL = os.environ.get(
    "AI_MODEL",
    "groq/compound-mini"
)

client = Groq(api_key=api_key) if api_key else None


# --------------------------------------------------
# DATABASE FUNCTIONS
# --------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")

    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)

    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)

    db.execute("PRAGMA foreign_keys = ON")

    db.executescript("""
    
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );


    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        original_filename TEXT NOT NULL,
        stored_filename TEXT NOT NULL UNIQUE,
        extracted_text TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY(user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
    );


    CREATE TABLE IF NOT EXISTS summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        document_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY(user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

        FOREIGN KEY(document_id)
        REFERENCES documents(id)
        ON DELETE CASCADE
    );


    CREATE TABLE IF NOT EXISTS quizzes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        document_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY(user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

        FOREIGN KEY(document_id)
        REFERENCES documents(id)
        ON DELETE CASCADE
    );


    CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        document_id INTEGER NOT NULL,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY(user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

        FOREIGN KEY(document_id)
        REFERENCES documents(id)
        ON DELETE CASCADE
    );

    """)

    db.commit()
    db.close()


# --------------------------------------------------
# LOGIN REQUIRED
# --------------------------------------------------

def login_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if "user_id" not in session:

            flash(
                "Please log in to continue.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        return view(*args, **kwargs)

    return wrapped


# --------------------------------------------------
# CURRENT USER
# --------------------------------------------------

def current_user():

    if "user_id" not in session:
        return None

    user = get_db().execute(
        """
        SELECT id, username
        FROM users
        WHERE id = ?
        """,
        (session["user_id"],)
    ).fetchone()

    return user


@app.context_processor
def inject_user():

    return {
        "current_user": current_user()
    }


# --------------------------------------------------
# FILE HELPERS
# --------------------------------------------------

def allowed_file(filename):

    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


def extract_pdf_text(path):

    try:
        reader = PdfReader(str(path))

    except Exception as exc:

        raise ValueError(
            "This file could not be read as a valid PDF."
        ) from exc


    extracted_pages = []


    for page in reader.pages:

        try:

            text = page.extract_text() or ""

            if text.strip():
                extracted_pages.append(
                    text.strip()
                )

        except Exception:
            continue


    full_text = "\n\n".join(
        extracted_pages
    ).strip()


    if len(full_text) < 50:

        raise ValueError(
            "No readable text was found. "
            "This may be a scanned or image-only PDF."
        )


    return full_text


# --------------------------------------------------
# MARKDOWN RENDERING
# --------------------------------------------------

def render_markdown(text):

    return markdown.markdown(
        text,
        extensions=[
            "tables",
            "fenced_code",
            "nl2br"
        ]
    )


# --------------------------------------------------
# AI FUNCTION
# --------------------------------------------------

def ask_ai(prompt, max_tokens=1500):

    if client is None:

        raise RuntimeError(
            "GROQ_API_KEY is missing. "
            "Add it to your environment variables."
        )


    completion = client.chat.completions.create(

        model=AI_MODEL,

        messages=[

            {
                "role": "system",

                "content": (
                    "You are StudySphere AI, a helpful academic assistant. "
                    "Answer clearly and accurately. "
                    "Use simple student-friendly language. "
                    "Format responses neatly using Markdown when appropriate."
                )
            },

            {
                "role": "user",
                "content": prompt
            }

        ],

        temperature=0.4,

        max_tokens=max_tokens

    )


    return completion.choices[0].message.content.strip()


# --------------------------------------------------
# DOCUMENT ACCESS
# --------------------------------------------------

def get_user_document(document_id):

    document = get_db().execute(
        """
        SELECT *
        FROM documents
        WHERE id = ?
        AND user_id = ?
        """,
        (
            document_id,
            session["user_id"]
        )
    ).fetchone()


    return document


# --------------------------------------------------
# ERROR HANDLER
# --------------------------------------------------

@app.errorhandler(413)
def file_too_large(error):

    flash(
        "File is too large. Maximum allowed size is 15 MB.",
        "danger"
    )

    return redirect(
        url_for("upload")
    )


# --------------------------------------------------
# HOME
# --------------------------------------------------

@app.route("/")
def home():

    if "user_id" in session:

        return redirect(
            url_for("dashboard")
        )


    return render_template(
        "index.html"
    )


# --------------------------------------------------
# SIGNUP
# --------------------------------------------------

@app.route(
    "/signup",
    methods=["GET", "POST"]
)
def signup():

    if "user_id" in session:

        return redirect(
            url_for("dashboard")
        )


    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )


        if len(username) < 3:

            flash(
                "Username must be at least 3 characters.",
                "danger"
            )


        elif len(password) < 6:

            flash(
                "Password must be at least 6 characters.",
                "danger"
            )


        else:

            db = get_db()


            existing_user = db.execute(
                """
                SELECT id
                FROM users
                WHERE username = ?
                """,
                (username,)
            ).fetchone()


            if existing_user:

                flash(
                    "This username is already taken.",
                    "danger"
                )


            else:

                db.execute(
                    """
                    INSERT INTO users
                    (username, password_hash)

                    VALUES (?, ?)
                    """,

                    (
                        username,
                        generate_password_hash(password)
                    )
                )


                db.commit()


                flash(
                    "Account created successfully. Please log in!",
                    "success"
                )


                return redirect(
                    url_for("login")
                )


    return render_template(
        "signup.html"
    )


# --------------------------------------------------
# LOGIN
# --------------------------------------------------

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if "user_id" in session:

        return redirect(
            url_for("dashboard")
        )


    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )


        user = get_db().execute(
            """
            SELECT *
            FROM users
            WHERE username = ?
            """,
            (username,)
        ).fetchone()


        if user and check_password_hash(
            user["password_hash"],
            password
        ):

            session.clear()

            session["user_id"] = user["id"]

            session["username"] = user["username"]


            flash(
                f"Welcome back, {user['username']}!",
                "success"
            )


            return redirect(
                url_for("dashboard")
            )


        flash(
            "Invalid username or password.",
            "danger"
        )


    return render_template(
        "login.html"
    )


# --------------------------------------------------
# LOGOUT
# --------------------------------------------------

@app.route("/logout")
def logout():

    session.clear()


    flash(
        "You have been logged out.",
        "success"
    )


    return redirect(
        url_for("home")
    )


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():

    db = get_db()

    user_id = session["user_id"]


    documents = db.execute(
        """
        SELECT
            id,
            original_filename,
            created_at

        FROM documents

        WHERE user_id = ?

        ORDER BY created_at DESC
        """,

        (user_id,)
    ).fetchall()


    notes_count = db.execute(
        """
        SELECT COUNT(*)
        FROM documents
        WHERE user_id = ?
        """,

        (user_id,)
    ).fetchone()[0]


    quiz_count = db.execute(
        """
        SELECT COUNT(*)
        FROM quizzes
        WHERE user_id = ?
        """,

        (user_id,)
    ).fetchone()[0]


    chat_count = db.execute(
        """
        SELECT COUNT(*)
        FROM chats
        WHERE user_id = ?
        """,

        (user_id,)
    ).fetchone()[0]


    return render_template(

        "dashboard.html",

        documents=documents,

        notes_count=notes_count,

        quiz_count=quiz_count,

        chat_count=chat_count

    )


# --------------------------------------------------
# UPLOAD PDF
# --------------------------------------------------

@app.route(
    "/upload",
    methods=["GET", "POST"]
)
@login_required
def upload():

    if request.method == "POST":

        if "notes" not in request.files:

            flash(
                "Please choose a PDF file.",
                "danger"
            )

            return redirect(
                url_for("upload")
            )


        file = request.files["notes"]


        if not file or file.filename == "":

            flash(
                "Please choose a PDF file.",
                "danger"
            )

            return redirect(
                url_for("upload")
            )


        if not allowed_file(file.filename):

            flash(
                "Only PDF files are supported.",
                "danger"
            )

            return redirect(
                url_for("upload")
            )


        original_filename = secure_filename(
            file.filename
        )


        stored_filename = (
            f"{uuid.uuid4().hex}.pdf"
        )


        filepath = (
            UPLOAD_DIR / stored_filename
        )


        try:

            file.save(filepath)


            extracted_text = extract_pdf_text(
                filepath
            )


            db = get_db()


            cursor = db.execute(
                """
                INSERT INTO documents

                (
                    user_id,
                    original_filename,
                    stored_filename,
                    extracted_text
                )

                VALUES (?, ?, ?, ?)
                """,

                (
                    session["user_id"],
                    original_filename,
                    stored_filename,
                    extracted_text
                )
            )


            db.commit()


            document_id = cursor.lastrowid


            flash(
                "PDF uploaded successfully. Generating your AI study guide...",
                "success"
            )


            return redirect(
                url_for(
                    "generate_summary",
                    document_id=document_id
                )
            )


        except ValueError as exc:

            if filepath.exists():
                filepath.unlink()


            flash(
                str(exc),
                "danger"
            )


            return redirect(
                url_for("upload")
            )


        except Exception:

            if filepath.exists():
                filepath.unlink()


            app.logger.exception(
                "Upload failed"
            )


            flash(
                "Upload failed unexpectedly. Please try again.",
                "danger"
            )


            return redirect(
                url_for("upload")
            )


    return render_template(
        "upload.html"
    )


# --------------------------------------------------
# GENERATE SUMMARY
# --------------------------------------------------

@app.route(
    "/summary/<int:document_id>"
)
@login_required
def generate_summary(document_id):

    doc = get_user_document(
        document_id
    )


    if not doc:

        flash(
            "Document not found.",
            "danger"
        )


        return redirect(
            url_for("dashboard")
        )


    existing_summary = get_db().execute(
        """
        SELECT content

        FROM summaries

        WHERE user_id = ?
        AND document_id = ?

        ORDER BY created_at DESC

        LIMIT 1
        """,

        (
            session["user_id"],
            document_id
        )
    ).fetchone()


    # Show existing summary if already generated
    if existing_summary:

        summary_html = render_markdown(
            existing_summary["content"]
        )


        return render_template(

            "summary.html",

            summary=summary_html,

            document=doc

        )


    prompt = f"""
Create a structured study guide from the following notes.

Use exactly these sections:

# Chapter Overview

# Detailed Explanation

# Key Concepts

# Important Definitions

# Exam-Focused Points

# Frequently Asked Questions

# Final Revision Checklist

Rules:

- Use simple and student-friendly language.
- Use headings and bullet points.
- Keep explanations clear.
- Do not invent information.
- Use tables only when they improve understanding.
- Focus on important exam concepts.

STUDY NOTES:

{doc["extracted_text"][:12000]}
"""


    try:

        summary = ask_ai(
            prompt,
            max_tokens=2200
        )


        db = get_db()


        db.execute(
            """
            INSERT INTO summaries

            (
                user_id,
                document_id,
                content
            )

            VALUES (?, ?, ?)
            """,

            (
                session["user_id"],
                document_id,
                summary
            )
        )


        db.commit()


        summary_html = render_markdown(
            summary
        )


        return render_template(

            "summary.html",

            summary=summary_html,

            document=doc

        )


    except Exception as exc:

        app.logger.exception(
            "Summary generation failed"
        )


        flash(
            f"AI summary could not be generated: {exc}",
            "danger"
        )


        return redirect(
            url_for("dashboard")
        )


# --------------------------------------------------
# GENERATE QUIZ
# --------------------------------------------------

@app.route(
    "/quiz/<int:document_id>"
)
@login_required
def quiz(document_id):

    doc = get_user_document(
        document_id
    )


    if not doc:

        flash(
            "Document not found.",
            "danger"
        )


        return redirect(
            url_for("dashboard")
        )


    prompt = f"""
Create exactly 10 multiple-choice questions from the notes.

Use this format:

## Question 1

Question text

A. Option one

B. Option two

C. Option three

D. Option four

**Correct Answer:** A

**Explanation:** Short explanation.

---

Repeat this format for all 10 questions.

Rules:

- Only use information from the notes.
- Questions should be exam-focused.
- Make the questions clear.
- Do not combine all questions into one paragraph.
- Keep explanations short.

STUDY NOTES:

{doc["extracted_text"][:9000]}
"""


    try:

        quiz_data = ask_ai(
            prompt,
            max_tokens=1800
        )


        db = get_db()


        db.execute(
            """
            INSERT INTO quizzes

            (
                user_id,
                document_id,
                content
            )

            VALUES (?, ?, ?)
            """,

            (
                session["user_id"],
                document_id,
                quiz_data
            )
        )


        db.commit()


        quiz_html = render_markdown(
            quiz_data
        )


        return render_template(

            "quiz.html",

            quiz=quiz_html,

            document=doc

        )


    except Exception as exc:

        app.logger.exception(
            "Quiz generation failed"
        )


        flash(
            f"Quiz could not be generated: {exc}",
            "danger"
        )


        return redirect(
            url_for("dashboard")
        )


# --------------------------------------------------
# CHAT WITH NOTES
# --------------------------------------------------

@app.route(
    "/chat/<int:document_id>",
    methods=["GET", "POST"]
)
@login_required
def chat(document_id):

    doc = get_user_document(
        document_id
    )


    if not doc:

        flash(
            "Document not found.",
            "danger"
        )


        return redirect(
            url_for("dashboard")
        )


    if request.method == "POST":

        question = request.form.get(
            "question",
            ""
        ).strip()


        if not question:

            flash(
                "Please enter a question.",
                "danger"
            )


            return redirect(
                url_for(
                    "chat",
                    document_id=document_id
                )
            )


        prompt = f"""
Answer the student's question using ONLY the study notes below.

Rules:

- Be concise and helpful.
- Use simple language.
- Do not invent information.
- If the answer is not available in the notes, clearly say so.
- Keep the answer focused.

STUDY NOTES:

{doc["extracted_text"][:8000]}

STUDENT QUESTION:

{question}
"""


        try:

            answer = ask_ai(
                prompt,
                max_tokens=700
            )


            db = get_db()


            db.execute(
                """
                INSERT INTO chats

                (
                    user_id,
                    document_id,
                    question,
                    answer
                )

                VALUES (?, ?, ?, ?)
                """,

                (
                    session["user_id"],
                    document_id,
                    question,
                    answer
                )
            )


            db.commit()


            return redirect(
                url_for(
                    "chat",
                    document_id=document_id
                )
            )


        except Exception as exc:

            app.logger.exception(
                "Chat AI failed"
            )


            flash(
                f"AI could not answer right now: {exc}",
                "danger"
            )


    history = get_db().execute(
        """
        SELECT
            question,
            answer,
            created_at

        FROM chats

        WHERE user_id = ?
        AND document_id = ?

        ORDER BY created_at ASC
        """,

        (
            session["user_id"],
            document_id
        )
    ).fetchall()


    return render_template(

        "chat.html",

        document=doc,

        history=history

    )


# --------------------------------------------------
# DELETE DOCUMENT
# --------------------------------------------------

@app.route(
    "/document/<int:document_id>/delete",
    methods=["POST"]
)
@login_required
def delete_document(document_id):

    doc = get_user_document(
        document_id
    )


    if not doc:

        flash(
            "Document not found.",
            "danger"
        )


        return redirect(
            url_for("dashboard")
        )


    db = get_db()


    db.execute(
        """
        DELETE FROM documents

        WHERE id = ?
        AND user_id = ?
        """,

        (
            document_id,
            session["user_id"]
        )
    )


    db.commit()


    file_path = (
        UPLOAD_DIR /
        doc["stored_filename"]
    )


    if file_path.exists():

        file_path.unlink()


    flash(
        "Document deleted successfully.",
        "success"
    )


    return redirect(
        url_for("dashboard")
    )


# --------------------------------------------------
# START APPLICATION
# --------------------------------------------------

if __name__ == "__main__":

    init_db()

    app.run(

        host="0.0.0.0",

        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),

        debug=True

    )


else:

    init_db()