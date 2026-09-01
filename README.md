# 🎓 StudySphere AI

StudySphere AI is an AI-powered study platform that helps students learn smarter from their notes.

Users can upload PDF study material and use AI to generate structured study guides, practice quizzes, and ask questions directly from their uploaded notes.

---

## ✨ Features

- 🔐 User Signup and Login
- 📄 Secure PDF Upload
- 🧠 AI-Generated Study Guides
- 📝 AI-Generated Practice Quizzes
- 💬 Chat with Your Notes
- 📚 Personal Document Library
- 🗑️ Document Management
- 📊 User Dashboard with Study Statistics
- 🔒 Account-based document access
- 📱 Responsive User Interface

---

## 🚀 How It Works

1. Create an account or log in.
2. Upload your study notes in PDF format.
3. StudySphere AI extracts the text from the PDF.
4. AI generates a structured study guide.
5. Generate practice quizzes from your notes.
6. Ask questions and chat directly with your study material.

---

## 🛠️ Tech Stack

### Frontend
- HTML5
- CSS3
- Jinja Templates

### Backend
- Python
- Flask

### Database
- SQLite

### AI Integration
- Groq API
- Large Language Models

### Libraries
- PyPDF
- Python Markdown
- Python Dotenv
- Werkzeug

---
## ⚙️ Installation

### Clone the repository:

git clone https://github.com/oorjitasharmaa/StudySphere-AI 

### Move into the project folder:

cd StudySphere-AI

### Create a virtual environment:

python -m venv venv

### Activate the virtual environment:

Windows

venv\Scripts\activate

### Install the required dependencies:

pip install -r requirements.txt

## 📂 Project Structure

```text
StudySphere-AI/
│
├── app.py
├── database.db
├── requirements.txt
├── .env
│
├── uploads/
│
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── signup.html
│   ├── login.html
│   ├── dashboard.html
│   ├── upload.html
│   ├── summary.html
│   ├── quiz.html
│   └── chat.html
│
└── static/
    └── style.css
