import traceback
from flask import Flask, request, jsonify
from pymongo import MongoClient
import torch
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone
import pandas as pd
import numpy as np
import bcrypt
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pdfminer.high_level import extract_text
import re
import random
import string
from io import BytesIO
from flask_cors import CORS
from urllib.parse import quote_plus
from google import genai
import os

GOOGLE_API_KEY = 'AIzaSyC8xdLGqLiXKPA_tmcf7c0G7DF4WmyF_HU'

# Configure API KEY
clientAI = genai.Client(api_key=GOOGLE_API_KEY)


app = Flask(__name__)

CORS(app, methods=['POST'])

# MongoDB connection
#client = MongoClient("mongodb://localhost:27017")
# MongoDB Atlas connection

cluster_uri = f"mongodb+srv://Shreevm:Shrvm@cluster0.8hoa4jz.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

client = MongoClient(cluster_uri)

db = client["blooms"]
students_collection = db['students']
faculty_collection = db['faculty']

# SMTP configuration
smtp_server = 'smtp.gmail.com'  # SMTP server address
smtp_port = 587  # SMTP server port
smtp_username = 'nadheedha31@gmail.com'  # SMTP server username
smtp_password = 'ewdh vlcl yqrf qmht'  # SMTP server password

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    name = data.get('name')
    user_id = data.get('id')
    userType = data.get('userType')
    print(userType)
    # Check if email already exists
    if userType == 'student':
        if students_collection.find_one({"email": email}):
            return jsonify({'error': 'Email already registered'}), 400
    elif userType == 'faculty':
        if faculty_collection.find_one({"email": email}):
            return jsonify({'error': 'Email already registered'}), 400
    else:
        return jsonify({'error': 'Invalid user type'}), 400

    # Generate OTP
    otp = generate_otp()

    # Store user data in MongoDB
    user = {
        'email': email,
        'password': hash_password(password),
        'name': name,
        'id': user_id,
        'otp': otp,
        'verified': False
    }
    
    if userType == 'student':
        students_collection.insert_one(user)
    elif userType == 'faculty':
        faculty_collection.insert_one(user)
    else:
        return jsonify({'error': 'Invalid user type'}), 400

    # Send OTP to user's email
    send_verification_email(email, otp)

    return jsonify({'message': 'User registered. OTP sent to your email'}), 200

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    userType = data.get('userType')

    if userType == 'student':
        user = students_collection.find_one({"email": email})
    elif userType == 'faculty':
        user = faculty_collection.find_one({"email": email})
    else:
        return jsonify({'error': 'Invalid user type'}), 400

    if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
        return jsonify({'message': 'Login successful'}), 200
    else:
        return jsonify({'error': 'Invalid email or password'}), 401

@app.route('/verify-otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    email = data.get('email')
    otp = data.get('otp')
    userType = data.get('userType')

    if userType == 'student':
        user = students_collection.find_one({"email": email})
    elif userType == 'faculty':
        user = faculty_collection.find_one({"email": email})
    else:
        return jsonify({'error': 'Invalid user type'}), 400

    if user and user['otp'] == otp:
        if userType == 'student':
            students_collection.update_one({"email": email}, {"$set": {"verified": True}})
        elif userType == 'faculty':
            faculty_collection.update_one({"email": email}, {"$set": {"verified": True}})
        return jsonify({'message': 'OTP verification successful', 'redirect': '/login'}), 200
    else:
        # If OTP verification fails, delete the created user data
        if userType == 'student' and user:
            students_collection.delete_one({"email": email})
        elif userType == 'faculty' and user:
            faculty_collection.delete_one({"email": email})
        
        return jsonify({'error': 'Invalid OTP', 'deleteData': True}), 400
    




def hash_password(password):
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed_password

def generate_otp(length=6):
    return ''.join(random.choices(string.digits, k=length))

def send_verification_email(email, otp):
    global smtp_server, smtp_port, smtp_username, smtp_password
    try:
        smtp_server = smtplib.SMTP(smtp_server, smtp_port)
        smtp_server.starttls()
        smtp_server.login(smtp_username, smtp_password)

        message = MIMEMultipart()
        message['From'] = smtp_username
        message['To'] = email
        message['Subject'] = 'Email Verification'
        body = f'Your OTP for verification is: {otp}'
        message.attach(MIMEText(body, 'plain'))

        smtp_server.sendmail(smtp_username, email, message.as_string())
        smtp_server.quit()
    except Exception as e:
        print("Error occurred while sending email:", e)


class SessionState:
    def __init__(self, **kwargs):
        for key, val in kwargs.items():
            setattr(self, key, val)

def get_session_state():
    if not hasattr(app, '_session_state'):
        app._session_state = SessionState()
    return app._session_state

def extract_text_from_pdf(pdf_file):
    pdf_bytes = pdf_file.read()  # Read the file contents as bytes
    memory_file = BytesIO(pdf_bytes)  # Create a BytesIO object from the bytes
    text = extract_text(memory_file)  # Extract text from the BytesIO object
    return text   

def extract_questions_and_marks(text):
    prompt = """
    Extract all questions, including question numbers, options (for question 11 to 16), question texts, and marks. Format each question as follows:
    
    (1. Calculate the total RF power delivered. (2 marks)) or (1.(a) Calculate the total RF power delivered. (2 marks))
    
    Ensure that each question is formatted with the following components:
    - Question number followed by a period (.)
    - Options in parentheses (for question 11 to 16)   
    - Question text
    - Marks in parentheses
    
    Example:
    1. Calculate the total RF power delivered. (2 marks)
    1.(a) Calculate the total RF power delivered. (2 marks)
    
    {text}
    """.format(text=text)

    response = client.models.generate_content(
        model="gemini-1.0-pro",
        contents=prompt
    )
    result = response.text.strip().splitlines()
    
    return result

@app.route('/process-responses', methods=['POST'])
def process_responses():
    data = request.get_json()
    editedLines = data.get('editedLines')

    questions = []
    options = []
    marks = []
    question_numbers = []
    last_question_number = None
    
    for line in editedLines.split('\n'):
        match_question = re.match(r'^(\d+)\.?\s*(?:\((\w+)\))?\s*(.+)\s*\((\d+)\s*marks\)$', line)

        if match_question:
            question_numbers.append(match_question.group(1))
            options.append(match_question.group(2))
            questions.append(match_question.group(3))
            marks.append(match_question.group(4))
            last_question_number = match_question.group(1)
        elif last_question_number:
            # If an option (b) is found without a question number, assign it the last question number encountered
            match_option_b = re.match(r'^\((b)\)\s*(.+)\s*\((\d+)\s*marks\)$', line)
            if match_option_b:
                question_numbers.append(last_question_number)
                options.append(match_option_b.group(1))
                questions.append(match_option_b.group(2))
                marks.append(match_option_b.group(3))
    
    return jsonify({
        'questionNumbers': question_numbers,
        'questions': questions,
        'options': options,
        'marks': marks
    })


@app.route('/store-in-mongodb', methods=['POST'])
def store_in_mongodb():
    data = request.get_json()
    question_numbers = data.get('questionNumbers')
    questions = data.get('questions')
    options = data.get('options')
    marks = data.get('marks')
    questionpaper_code = data.get('questionPaperCode')

    client = MongoClient(cluster_uri)
    db = client["blooms"]
    collection = db["qnpaper2"]
    
    question_data = []
    for q_num, q, opts, m in zip(question_numbers, questions, options, marks):
        question_data.append({
            "question_number": q_num,
            "question": q,
            "options": opts,
            "mark": m
        })
    
    collection.insert_one({"questionpaper_code": questionpaper_code, "questions": question_data})
    
    client.close()

    return jsonify({'message': 'Questions stored in MongoDB successfully'}), 200


@app.route('/upload-qspaper', methods=['POST'])
def upload_qspaper():
    questionpaper_code = request.form['questionPaperCode']
    file = request.files['file']
    print("Enteredd")
    text = extract_text_from_pdf(file)
    print("Text extracted")
    responses = extract_questions_and_marks(text)
    print("Question and mark extracted")
    if not responses:
        return jsonify({'error': 'No questions or marks extracted from the PDF'}), 400

    return jsonify({'message': 'Question paper uploaded successfully', 'responses': responses}), 200

Api_key = "a1a07892-456f-45b1-9694-e13027dc6a8a"
pc = Pinecone(api_key=Api_key)

collection = db['qnpaper2']
# Initialize Retriever
device = 'cuda' if torch.cuda.is_available() else 'cpu'
retriever = SentenceTransformer("flax-sentence-embeddings/all_datasets_v3_mpnet-base", device=device)
index_name = "cognitive-levels-3"
index = pc.Index(index_name)

def query_pinecone(query, top_k):
    xq = retriever.encode([query]).tolist()
    xc = index.query(vector=xq, top_k=top_k, include_metadata=True)
    return xc

def classify_questions(questionpaper_code):
    results = []

    questions_cursor = collection.find({"questionpaper_code": questionpaper_code})
    for document in questions_cursor:
        for q in document.get("questions", []):
            question_number = q.get("question_number", "")
            question = q.get("question", "")
            options = q.get("options", "")
            mark = q.get("mark", "")

            if question:
                context = query_pinecone(question, top_k=1)
                if context and "matches" in context:
                    label = context['matches'][0]['metadata'].get("Label", "Not classified")
                else:
                    label = "Not classified"
            else:
                label = "Not classified"

            # Store the Bloom's Taxonomy level in the database
            collection.update_many(
                {"questionpaper_code": questionpaper_code, "questions": {"$elemMatch": {"question_number": question_number, "options": options}}},
                {"$set": {"questions.$.bt_level": label}}
            )


            results.append((question_number, options, question, mark, label))

    return results


def analyze_marks(results):
    bt_level_marks = {}
    total_marks = sum([int(result[-2]) for result in results])  # Total marks
    for result in results:
        bt_level = result[-1]  # Last element is the BT_Level
        mark = int(result[-2])  # Second last element is the mark
        if bt_level in bt_level_marks:
            bt_level_marks[bt_level] += mark
        else:
            bt_level_marks[bt_level] = mark
    
    # Convert marks to percentages
    bt_level_percentages = {bt_level: (marks / total_marks) * 100 for bt_level, marks in bt_level_marks.items()}
    return bt_level_percentages

@app.route('/classify_questions', methods=['POST'])
def classify_questions_route():
    questionpaper_code = request.json['questionpaper_code']
    results = classify_questions(questionpaper_code)
    return jsonify(results)

@app.route('/analyze_marks', methods=['POST'])
def analyze_marks_route():
    results = request.json['results']
    bt_level_percentages = analyze_marks(results)
    return jsonify(bt_level_percentages)

@app.route('/question_data/<questionpaper_code>', methods=['GET'])
def get_question_data(questionpaper_code):
    # Retrieve question data from MongoDB based on the question paper code
    question_data = list(collection.find({"questionpaper_code": questionpaper_code}, {"_id": 0}))
    return jsonify(question_data)

@app.route('/question_paper_codes', methods=['GET'])
def get_question_paper_codes():
    # Retrieve question paper codes from MongoDB
    question_paper_cursor = collection.distinct("questionpaper_code")
    question_paper_codes = list(question_paper_cursor)
    return jsonify(question_paper_codes)

marks_collection = db["student_database"]
questions_collection = db["qnpaper2"]

@app.route("/questionpaper", methods=["POST"])
def manage_questionpaper():
    data = request.json
    action = data.get("action", "")

    if action == "retrieve_questions":
        return retrieve_questions(data)
    elif action == "submit_marks":
        print("submit")
        return submit_marks(data)
    else:
        return jsonify({"error": "Invalid action"}), 400

def retrieve_questions(data):
    questionpaper_code = data.get("questionpaper_code", "")
    
    query = {"questionpaper_code": questionpaper_code}
    projection = {"_id": 0, "questions": 1}
    questions_cursor = questions_collection.find(query, projection)
    
    questions = []
    for document in questions_cursor:
        for q in document.get("questions", []):
            question_number = q.get("question_number", "")
            question = q.get("question", "")
            options = q.get("options", [])
            bt_level = q.get("bt_level", "")
            mark=q.get("mark","")
            
            questions.append({
                "QuestionNumber": question_number,
                "Question": question,
                "Options": options,
                "btlevel": bt_level,
                "mark":mark,
                
            })
    print(questions)
    return jsonify(questions)

def submit_marks(data):
    try:
        questionpaper_code = data.get("questionpaper_code", "")
        student_name = data.get("student_name", "")
        print("student_name:", student_name )
        student_regno = data.get("student_reg", "")
        print("student_regno:", student_regno)
        marks_data = data.get("data", [])
        print("marks_data:", marks_data) # Print marks_data received from the frontend
        
         # Calculate total score for each Bloom's Taxonomy level
      # Assuming you have already initialized your MongoDB client and selected the appropriate database
        questions_collection = db["qnpaper2"]

# Then you pass this collection to the calculate_performance function along with other required arguments
        performance = calculate_performance(marks_data)


        # Create a structure for storing the data
        marks_entry = {
            "questionpaper_code": questionpaper_code,
            "student_name": student_name,   
            "student_regno": student_regno,
            "questions": [],
            "performance": performance
        }
        
        # Iterate over the submitted marks and add them to the structure
        for mark in marks_data:
            question_number = mark.get("question_number", "")
            question = mark.get("question", "")
            options = mark.get("options", [])
            bt_level = mark.get("bt_level", "")
            score = mark.get("score", "")
            marks = mark.get("marks", "")
            marks_entry["questions"].append(
                {
                    "question_number": question_number,
                    "option": options, 
                    "question": question,
                    "marks": marks,
                    "Maxmark": score,
                    "bt_level": bt_level
                }
            )
        
        print("marks_entry:", marks_entry) # Print marks_entry before inserting into the database
        
        # Insert the data into MongoDB
        marks_collection.insert_one(marks_entry)
        
        return jsonify({"message": "Marks submitted successfully!"})
    except Exception as e:
        # Log the exception traceback
        traceback.print_exc()
        # Return an error response
        return jsonify({"error": str(e)}), 500
    

def calculate_performance(marks_data):
    # Initialize dictionary to store total marks scored and total marks available for each BT level
    performance = {}
    
    # Calculate total score for each Bloom's Taxonomy level
    for row in marks_data:
        bt_level = row.get("bt_level", "")
        scored_mark = int(row.get("marks", 0)) if row.get("marks", "") else 0
        total_mark = int(row.get("score", 0)) if row.get("score", "") else 0
        if bt_level not in performance:
            performance[bt_level] = {"total_scored_mark": 0, "Maximum_total_mark": 0}
        performance[bt_level]["total_scored_mark"] += scored_mark
        performance[bt_level]["Maximum_total_mark"] += total_mark

    return performance


student_collection = db["student_database"]

@app.route('/performance', methods=['POST'])
def get_performance():
    data = request.json
    student_name = data.get('student_name')
    questionpaper_code = data.get('questionpaper_code')

    query = {
        "student_name": student_name,
        "questionpaper_code": questionpaper_code
    }
    mark_data = student_collection.find_one(query)

    if mark_data:
        calculated_performance = mark_data.get("performance")
        if calculated_performance:
            print(calculated_performance)
            return jsonify(calculated_performance)
        else:
            return jsonify({"error": "No performance data found for this student."}), 404
    else:
        return jsonify({"error": "No data found for the specified student and question paper code."}), 404

# @app.route('/performance', methods=['POST'])
# def calculate_performance():
#     # Retrieve student name and question paper code from the request
#     student_name = request.json.get('student_name')
#     questionpaper_code = request.json.get('questionpaper_code')

#     # Placeholder logic for calculating performance
#     # Replace this with your actual implementation
#     performance_data = {
#         'K1': {'total_scored_mark': 80, 'total_total_mark': 100},
#         'K2': {'total_scored_mark': 75, 'total_total_mark': 100},
#         'K3': {'total_scored_mark': 90, 'total_total_mark': 100},
#     }

#     return jsonify(performance_data)

@app.route('/api/query', methods=['POST'])
def query():
    data = request.get_json()
    query = data.get('query')
    context = query_pinecone(query, top_k=1)
    if context and "matches" in context:
        label = context['matches'][0]['metadata'].get("Label", "Not classified")
    else:
        label = "Not classified"
    return jsonify(label)

@app.route('/students', methods=['GET'])
def get_students():
    try:
        # Access the MongoDB collection
        students_collection = db['student_database']  # Replace 'students' with your actual collection name

        # Query the students collection to fetch student names
        student_names = students_collection.distinct("student_name")
     # Replace 'subjects' with your actual collection name
        subject_codes = students_collection.distinct("questionpaper_code")

        # Assemble data into dictionary
        data = {
            'studentNames': student_names,
            'subjectCodes': subject_codes
        }

        # Return data as JSON response
        return jsonify(data)

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  
    app.run(host="0.0.0.0", port=port)
